"""Importar el consolidado del SaaS sin duplicar lo que ya existe (RF-030 a RF-036).

VisaNow lleva los trámites en otro sistema y lo exporta a Excel. Ese archivo se
vuelve a bajar cada semana, y cada vez trae **las mismas solicitudes** con una
etapa más avanzada. Importarlo sin más duplicaría los trámites cada semana hasta
volver el sistema inservible.

**El número de solicitud es la llave** (RF-032). Es lo único del export que
identifica un trámite de forma estable: el nombre cambia de ortografía y el
pasaporte a veces llega vacío. Si ya hay un caso con ese número, se actualiza;
si no, se crea.

**Se previsualiza antes de aplicar** (RF-033). Importar a ciegas sobre datos de
clientes reales es la clase de operación que no se puede deshacer. Primero se
clasifica fila por fila —nuevo, actualizado, sin cambio, conflicto, rechazado—,
se guarda esa previsualización, y aplicar es confirmar lo que ya se vio.

**Cada campo tiene dueño** (RF-034). El SaaS gobierna sus propios hitos: la
etapa, el DS-160, la búsqueda de citas. VisaNow gobierna lo suyo: el
responsable, la próxima acción, lo comercial y lo financiero. Un export jamás
pisa un campo de VisaNow; cuando no coinciden en un campo del SaaS que alguien
ya corrigió a mano, no se decide por nadie: se levanta un conflicto y lo resuelve
quien sabe. Esa es la diferencia entre sincronizar y sobrescribir.

**Queda el registro de cada corrida** (RF-035), con sus errores y reintentos,
para que la alerta de fuente desactualizada tenga de dónde leer.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.core import homologacion as hom
from app.models.esquema import (Casos, ConflictosSincronizacion, EstadosOperativos,
                                Importaciones, ImportacionesFilas, Sincronizaciones,
                                Solicitantes, Usuarios)
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')
ORIGEN = 'saas'

# Lo que el SaaS gobierna: son sus hitos y él es la fuente de verdad.
CAMPOS_DEL_SAAS = ('etapa_saas', 'estado_id', 'ds160_enviado_en', 'ds160_numero', 'busqueda_citas')
# Lo que VisaNow gobierna. El export no los toca nunca, ni para rellenarlos.
CAMPOS_DE_VISANOW = ('responsable_id', 'proxima_accion', 'proxima_accion_fecha', 'negocio_id',
                     'resultado', 'resultado_fecha')

RESULTADOS = ('nuevo', 'actualizado', 'sin_cambio', 'conflicto', 'rechazado')


def _ahora() -> dt.datetime:
    return dt.datetime.now(BOGOTA)


# ------------------------------------------------------------ normalización

@dataclass
class FilaSaas:
    """Una solicitud del export, ya leída y con sus problemas anotados."""
    numero: int
    id_externo: str | None = None
    solicitante: str | None = None
    pasaporte: str | None = None
    etapa_bruta: str | None = None
    etapa: str | None = None
    fecha_creacion: dt.date | None = None
    ds160_enviado_en: dt.date | None = None
    ds160_numero: str | None = None
    busqueda_citas: bool | None = None
    # Lo que impide procesar la fila. Hoy solo una cosa: no tener llave.
    problemas: list[str] = field(default_factory=list)
    # Lo que se pudo leer a medias. No tumba la fila: se actualiza lo demas y se
    # dice que falto, para que alguien agregue la etapa al diccionario. Si una
    # etapa nueva del SaaS rechazara la fila entera, una palabra cambiada alla
    # congelaria todos esos tramites aca sin que nada fallara.
    avisos: list[str] = field(default_factory=list)

    @property
    def utilizable(self) -> bool:
        return bool(self.id_externo) and not self.problemas


def _fecha(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return dt.date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return None


# `busqueda_citas` es una columna de texto, no un booleano, y el export dice
# «active»/«inactive». Guardar un bool de Python ahi lo convierte en la cadena
# «false», y entonces comparar el bool del export contra el texto guardado da
# distinto SIEMPRE: la importacion decia «actualizado» en cada corrida y la
# idempotencia que pide RF-032 se perdia sin que nada fallara. Los dos lados
# pasan por la misma funcion, que es la unica forma de que la comparacion sea
# estable sin importar que haya guardado antes la migracion.
_SI = ('active', 'activo', 'activa', 'si', 'sí', 'true', 't', '1', 'yes')


def _a_bool(v) -> bool | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in _SI


def _bool_texto(v: bool | None) -> str | None:
    return None if v is None else ('true' if v else 'false')


def _texto(v) -> str | None:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def normalizar(filas: list[dict]) -> list[FilaSaas]:
    """Del export crudo a filas con sentido, diciendo qué no se pudo leer.

    Una fila sin número de solicitud se rechaza en vez de inventarle una llave:
    sin llave no hay forma de reconocerla la próxima semana, y crearía un
    trámite nuevo en cada importación.
    """
    salida = []
    for n, cruda in enumerate(filas, start=1):
        f = FilaSaas(numero=cruda.get('fila') or n)
        f.id_externo = _texto(cruda.get('numero_solicitud'))
        f.solicitante = _texto(cruda.get('solicitante'))
        f.pasaporte = _texto(cruda.get('pasaporte'))
        f.etapa_bruta = _texto(cruda.get('etapa'))
        f.fecha_creacion = _fecha(cruda.get('fecha_creacion'))
        f.ds160_enviado_en = _fecha(cruda.get('ds160_enviado_en'))
        f.ds160_numero = _texto(cruda.get('ds160_numero'))
        f.busqueda_citas = _a_bool(cruda.get('busqueda_citas'))

        if not f.id_externo:
            f.problemas.append('sin número de solicitud: no hay con qué reconocerla después')
        if f.etapa_bruta:
            codigo, problema = hom.estado(f.etapa_bruta)
            f.etapa = codigo
            if problema:
                f.avisos.append(f'la etapa «{f.etapa_bruta}» no está en el diccionario: '
                                f'el trámite se actualiza pero no cambia de estado')
        salida.append(f)
    return salida


# ----------------------------------------------------------- previsualización

def _caso_de(db: Session, id_externo: str) -> Casos | None:
    return db.scalars(select(Casos).where(Casos.id_externo == id_externo)
                      .order_by(Casos.id)).first()


def _estado_id(db: Session, codigo: str | None) -> int | None:
    if not codigo:
        return None
    return db.scalar(select(EstadosOperativos.id)
                     .where(EstadosOperativos.codigo == codigo))


def _comparar(db: Session, caso: Casos, f: FilaSaas) -> tuple[dict, list[dict]]:
    """Qué cambia y qué no se puede decidir solo.

    Un cambio de etapa es normal: para eso se sincroniza. Un número de DS-160
    distinto del que ya está guardado no lo es, porque alguien lo escribió a
    mano mirando el formulario: ahí se levanta conflicto en vez de pisarlo.
    """
    cambios: dict = {}
    conflictos: list[dict] = []

    estado_nuevo = _estado_id(db, f.etapa)
    if estado_nuevo and estado_nuevo != caso.estado_id:
        cambios['estado_id'] = estado_nuevo
    if f.etapa_bruta and f.etapa_bruta != caso.etapa_saas:
        cambios['etapa_saas'] = f.etapa_bruta
    if f.busqueda_citas is not None and f.busqueda_citas != _a_bool(caso.busqueda_citas):
        cambios['busqueda_citas'] = _bool_texto(f.busqueda_citas)
    if f.ds160_enviado_en:
        actual = caso.ds160_enviado_en.date() if caso.ds160_enviado_en else None
        if actual != f.ds160_enviado_en:
            cambios['ds160_enviado_en'] = dt.datetime.combine(
                f.ds160_enviado_en, dt.time(0, 0), tzinfo=BOGOTA)

    if f.ds160_numero:
        indice = seg.indice_ciego(f.ds160_numero)
        if caso.ds160_hash and caso.ds160_hash != indice:
            # Lo escribió alguien mirando el formulario: no se pisa en silencio.
            conflictos.append({'campo': 'ds160_numero', 'valor_visanow': '(ya registrado)',
                               'valor_saas': f.ds160_numero})
        elif not caso.ds160_hash:
            cambios['ds160_numero'] = f.ds160_numero

    return cambios, conflictos


def _huella(filas: list[FilaSaas]) -> str:
    """Identifica el contenido del export, para reconocer el mismo archivo."""
    crudo = '|'.join(f'{f.id_externo}:{f.etapa_bruta}:{f.ds160_numero}:{f.busqueda_citas}'
                     for f in filas)
    return hashlib.sha256(crudo.encode('utf-8')).hexdigest()


def previsualizar(db: Session, actor: Usuarios, filas: list[dict], *,
                  archivo: str | None = None, ip: str | None = None) -> Importaciones:
    """Clasifica el export sin tocar un solo trámite (RF-033).

    Devuelve la importación guardada, con una fila por cada solicitud y su
    veredicto. Nada cambia hasta que alguien aplique.
    """
    leidas = normalizar(filas)
    imp = Importaciones(origen=ORIGEN, archivo_nombre=archivo,
                        archivo_sha256=_huella(leidas), filas_totales=len(leidas),
                        nuevos=0, actualizados=0, sin_cambios=0, conflictos=0, rechazados=0,
                        estado='previsualizada', ejecutada_por=actor.id)
    db.add(imp)
    db.flush()

    vistos: set[str] = set()
    for f in leidas:
        detalle, caso_id, resultado = None, None, 'rechazado'

        if not f.utilizable:
            detalle = '; '.join(f.problemas) or 'fila ilegible'
        elif f.id_externo in vistos:
            # El mismo número dos veces en el archivo: se queda la primera.
            detalle = 'el número de solicitud está repetido en el archivo'
        else:
            vistos.add(f.id_externo)
            caso = _caso_de(db, f.id_externo)
            if caso is None:
                resultado = 'nuevo'
                detalle = 'no hay trámite con ese número de solicitud'
            else:
                caso_id = caso.id
                cambios, conflictos = _comparar(db, caso, f)
                if conflictos:
                    resultado = 'conflicto'
                    detalle = '; '.join(f'{c["campo"]}: el SaaS dice «{c["valor_saas"]}»'
                                        for c in conflictos)
                elif cambios:
                    resultado = 'actualizado'
                    detalle = 'cambia: ' + ', '.join(sorted(cambios))
                else:
                    resultado = 'sin_cambio'
                    detalle = 'ya está igual'
                if f.avisos:
                    detalle = f'{detalle}. ' + '; '.join(f.avisos)

        db.add(ImportacionesFilas(
            importacion_id=imp.id, fila_numero=f.numero, id_externo=f.id_externo,
            datos=json.loads(json.dumps({
                'solicitante': f.solicitante, 'pasaporte': f.pasaporte,
                'etapa': f.etapa_bruta, 'etapa_codigo': f.etapa,
                'fecha_creacion': f.fecha_creacion.isoformat() if f.fecha_creacion else None,
                'ds160_enviado_en': (f.ds160_enviado_en.isoformat()
                                     if f.ds160_enviado_en else None),
                'ds160_numero': f.ds160_numero, 'busqueda_citas': f.busqueda_citas})),
            resultado=resultado, caso_id=caso_id, detalle=detalle))
        campo = {'nuevo': 'nuevos', 'actualizado': 'actualizados', 'sin_cambio': 'sin_cambios',
                 'conflicto': 'conflictos', 'rechazado': 'rechazados'}[resultado]
        setattr(imp, campo, getattr(imp, campo) + 1)

    db.flush()
    auditar(db, operacion='insert', entidad='importaciones', usuario_id=actor.id,
            entidad_id=imp.id, despues=instantanea(imp), ip=ip)
    db.commit()
    return imp


# -------------------------------------------------------------------- aplicar

def _aplicar_a_caso(db: Session, caso: Casos, f: FilaSaas, imp_id: int) -> list[str]:
    """Escribe solo los campos que el SaaS gobierna (RF-034)."""
    cambios, conflictos = _comparar(db, caso, f)
    for c in conflictos:
        ya = db.scalar(select(ConflictosSincronizacion.id).where(
            ConflictosSincronizacion.caso_id == caso.id,
            ConflictosSincronizacion.campo == c['campo'],
            ConflictosSincronizacion.estado == 'abierto'))
        if not ya:
            db.add(ConflictosSincronizacion(
                importacion_id=imp_id, caso_id=caso.id, campo=c['campo'],
                valor_visanow=c['valor_visanow'], valor_saas=c['valor_saas'],
                estado='abierto'))

    for campo, valor in cambios.items():
        if campo == 'ds160_numero':
            caso.ds160_numero_cifrado = seg.cifrar(valor)
            caso.ds160_hash = seg.indice_ciego(valor)
        else:
            setattr(caso, campo, valor)
    caso.sincronizado_en = _ahora()
    if cambios:
        caso.ultima_actividad_en = _ahora()
    return sorted(cambios)


def aplicar(db: Session, actor: Usuarios, importacion_id: int, *,
            ip: str | None = None) -> dict:
    """Ejecuta una previsualización ya vista (RF-032).

    Idempotente por el número de solicitud: volver a aplicar el mismo archivo no
    crea nada, porque los trámites ya existen y quedan en «sin cambio».

    Las filas marcadas «nuevo» no crean el trámite solas: hace falta decir de qué
    persona es, y eso el export no lo dice de forma confiable —el nombre viene
    escrito distinto cada vez—. Se dejan para vincular a mano (RF-036), que es
    más lento y no se equivoca de cliente.
    """
    imp = db.get(Importaciones, importacion_id)
    if imp is None:
        raise NoEncontrado('La importación no existe.')
    if imp.estado != 'previsualizada':
        raise Conflicto(f'Esa importación está «{imp.estado}»: solo se aplica una '
                        f'previsualización.', codigo='estado_invalido')

    filas = list(db.scalars(select(ImportacionesFilas)
                            .where(ImportacionesFilas.importacion_id == importacion_id)
                            .order_by(ImportacionesFilas.fila_numero)))
    actualizados, conflictos, saltados = 0, 0, 0
    for fila in filas:
        if fila.resultado not in ('actualizado', 'conflicto') or not fila.caso_id:
            saltados += 1
            continue
        caso = db.get(Casos, fila.caso_id)
        if caso is None:
            saltados += 1
            continue
        d = fila.datos or {}
        f = FilaSaas(numero=fila.fila_numero, id_externo=fila.id_externo,
                     etapa_bruta=d.get('etapa'), etapa=d.get('etapa_codigo'),
                     ds160_enviado_en=_fecha(d.get('ds160_enviado_en')),
                     ds160_numero=d.get('ds160_numero'),
                     busqueda_citas=_a_bool(d.get('busqueda_citas')))
        hechos = _aplicar_a_caso(db, caso, f, imp.id)
        if hechos:
            actualizados += 1
        if fila.resultado == 'conflicto':
            conflictos += 1

    imp.estado = 'aplicada'
    imp.aplicada_en = _ahora()
    db.flush()
    auditar(db, operacion='update', entidad='importaciones', usuario_id=actor.id,
            entidad_id=imp.id,
            despues={'estado': 'aplicada', 'actualizados': actualizados,
                     'conflictos': conflictos}, ip=ip)
    registrar(db, resultado='ok',
              detalle=f'Importación #{imp.id}: {actualizados} trámites actualizados, '
                      f'{conflictos} con conflicto, {imp.nuevos} por vincular a mano.')
    db.commit()
    return {'importacion_id': imp.id, 'actualizados': actualizados,
            'conflictos': conflictos, 'por_vincular': imp.nuevos, 'saltados': saltados}


def descartar(db: Session, actor: Usuarios, importacion_id: int, *,
              ip: str | None = None) -> Importaciones:
    imp = db.get(Importaciones, importacion_id)
    if imp is None:
        raise NoEncontrado('La importación no existe.')
    if imp.estado != 'previsualizada':
        raise Conflicto(f'Esa importación está «{imp.estado}».', codigo='estado_invalido')
    imp.estado = 'descartada'
    db.flush()
    auditar(db, operacion='update', entidad='importaciones', usuario_id=actor.id,
            entidad_id=imp.id, despues={'estado': 'descartada'}, ip=ip)
    db.commit()
    return imp


# ------------------------------------------------------- vinculación manual

def vincular(db: Session, actor: Usuarios, caso_id: int, id_externo: str, *,
             ip: str | None = None) -> Casos:
    """Le pone a un trámite existente su número de solicitud del SaaS (RF-036).

    Es el camino para las filas «nuevo»: una persona reconoce de quién es y lo
    amarra. A partir de ahí las importaciones siguientes lo actualizan solas.
    """
    caso = db.get(Casos, caso_id)
    if caso is None:
        raise NoEncontrado('El trámite no existe.')
    id_externo = (id_externo or '').strip()
    if not id_externo:
        raise Invalido('Escriba el número de solicitud del SaaS.', codigo='falta_numero')

    otro = db.scalars(select(Casos).where(Casos.id_externo == id_externo,
                                          Casos.id != caso_id)).first()
    if otro is not None:
        raise Conflicto(f'El número de solicitud ya es del trámite #{otro.id}. '
                        f'Una solicitud del SaaS no puede ser de dos trámites.',
                        codigo='solicitud_ya_vinculada')

    antes = instantanea(caso)
    caso.id_externo = id_externo
    caso.fuente = 'saas'
    caso.sincronizado_en = _ahora()
    db.flush()
    auditar(db, operacion='update', entidad='casos', usuario_id=actor.id, entidad_id=caso.id,
            antes=antes, despues=instantanea(caso), ip=ip)
    db.commit()
    return caso


def candidatos(db: Session, id_externo: str, nombre: str | None = None,
               limite: int = 10) -> list[dict]:
    """Trámites que podrían ser esa solicitud, para no buscar a ciegas.

    Se sugiere por nombre del solicitante, que es lo único que trae el export,
    pero sin decidir nada: quien vincula es una persona.
    """
    consulta = (select(Casos.id, Solicitantes.nombre, Casos.fuente)
                .join(Solicitantes, Solicitantes.id == Casos.solicitante_id)
                .where(Casos.id_externo.is_(None)))
    if nombre:
        consulta = consulta.where(Solicitantes.nombre.ilike(f'%{nombre.strip()}%'))
    return [{'caso_id': i, 'solicitante': n, 'fuente': f}
            for i, n, f in db.execute(consulta.order_by(Casos.id.desc()).limit(limite))]


# ----------------------------------------------- registro de sincronización

def registrar(db: Session, *, resultado: str, detalle: str | None = None,
              origen: str = ORIGEN) -> Sincronizaciones:
    """Deja constancia de la corrida (RF-035).

    Los intentos se acumulan sobre el último error: si el SaaS lleva tres días
    fallando, interesa que sean tres intentos de lo mismo y no tres líneas
    sueltas que nadie relaciona.
    """
    if resultado not in ('ok', 'error'):
        raise Invalido('El resultado de una sincronización es «ok» o «error».')
    ultimo = db.scalars(select(Sincronizaciones)
                        .where(Sincronizaciones.origen == origen)
                        .order_by(Sincronizaciones.ocurrido_en.desc())).first()
    if (resultado == 'error' and ultimo is not None and ultimo.resultado == 'error'
            and ultimo.detalle == detalle):
        ultimo.intentos = (ultimo.intentos or 1) + 1
        ultimo.ocurrido_en = _ahora()
        db.flush()
        return ultimo
    s = Sincronizaciones(origen=origen, resultado=resultado, detalle=detalle, intentos=1)
    db.add(s)
    db.flush()
    return s


def estado(db: Session, origen: str = ORIGEN) -> dict:
    """Cuándo fue la última vez que esto funcionó, y hace cuánto.

    De acá lee la alerta de fuente desactualizada: sin este registro, que el
    SaaS lleve una semana sin sincronizar no se nota hasta que alguien pregunta
    por un trámite que no se movió.
    """
    ultimo = db.scalars(select(Sincronizaciones).where(Sincronizaciones.origen == origen)
                        .order_by(Sincronizaciones.ocurrido_en.desc())).first()
    ultimo_ok = db.scalars(select(Sincronizaciones)
                           .where(Sincronizaciones.origen == origen,
                                  Sincronizaciones.resultado == 'ok')
                           .order_by(Sincronizaciones.ocurrido_en.desc())).first()
    horas = None
    if ultimo_ok is not None:
        horas = round((_ahora() - ultimo_ok.ocurrido_en).total_seconds() / 3600, 1)
    return {
        'origen': origen,
        'ultima': ultimo.ocurrido_en if ultimo else None,
        'resultado': ultimo.resultado if ultimo else None,
        'detalle': ultimo.detalle if ultimo else None,
        'intentos': ultimo.intentos if ultimo else 0,
        'ultima_exitosa': ultimo_ok.ocurrido_en if ultimo_ok else None,
        'horas_desde_la_ultima_exitosa': horas,
    }


def importaciones(db: Session, limite: int = 20) -> list[Importaciones]:
    return list(db.scalars(select(Importaciones).where(Importaciones.origen == ORIGEN)
                           .order_by(Importaciones.iniciada_en.desc()).limit(limite)))


def filas_de(db: Session, importacion_id: int,
             resultado: str | None = None) -> list[ImportacionesFilas]:
    consulta = select(ImportacionesFilas).where(
        ImportacionesFilas.importacion_id == importacion_id)
    if resultado:
        if resultado not in RESULTADOS:
            raise Invalido(f'Resultado inválido. Opciones: {", ".join(RESULTADOS)}.')
        consulta = consulta.where(ImportacionesFilas.resultado == resultado)
    return list(db.scalars(consulta.order_by(ImportacionesFilas.fila_numero)))


def conflictos_abiertos(db: Session) -> list[ConflictosSincronizacion]:
    return list(db.scalars(select(ConflictosSincronizacion)
                           .where(ConflictosSincronizacion.estado == 'abierto')
                           .order_by(ConflictosSincronizacion.detectado_en.desc())))


def resolver_conflicto(db: Session, actor: Usuarios, conflicto_id: int, decision: str, *,
                       ip: str | None = None) -> ConflictosSincronizacion:
    """Quién gana: lo de VisaNow, lo del SaaS, o se ignora.

    Si gana el SaaS se escribe el valor; si gana VisaNow no se toca nada y lo que
    queda es la constancia de que se miró y se decidió.
    """
    validas = ('resuelto_visanow', 'resuelto_saas', 'ignorado')
    if decision not in validas:
        raise Invalido(f'Decisión inválida. Opciones: {", ".join(validas)}.')
    c = db.get(ConflictosSincronizacion, conflicto_id)
    if c is None:
        raise NoEncontrado('El conflicto no existe.')
    if c.estado != 'abierto':
        raise Conflicto(f'Ese conflicto ya está «{c.estado}».', codigo='ya_resuelto')

    if decision == 'resuelto_saas' and c.campo == 'ds160_numero':
        caso = db.get(Casos, c.caso_id)
        caso.ds160_numero_cifrado = seg.cifrar(c.valor_saas)
        caso.ds160_hash = seg.indice_ciego(c.valor_saas)
        caso.ultima_actividad_en = _ahora()
    c.estado = decision
    c.resuelto_por = actor.id
    c.resuelto_en = _ahora()
    db.flush()
    auditar(db, operacion='update', entidad='conflictos_sincronizacion', usuario_id=actor.id,
            entidad_id=c.id, despues={'estado': decision, 'campo': c.campo}, ip=ip)
    db.commit()
    return c
