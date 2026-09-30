"""Actividad 6.2: escribir de verdad lo que la previsualización planeó.

Todo pasa dentro de **una sola transacción**. Si la fila 1.300 falla, no queda
media migración cargada: no queda nada, se corrige y se vuelve a correr. Es la
única red que hay, porque la alternativa —borrar a mano lo que alcanzó a
entrar— es peor que empezar de nuevo.

Lo que se escribe respeta las reglas del sistema, no las esquiva:

- El saldo **no se migra**. Se escriben las ventas y los pagos y el saldo sale
  de la vista, como en el resto del sistema (RN-01). Si la cartera migrada no
  coincide con la del Excel, es que algo está mal, y eso es justamente lo que
  se quiere poder ver.
- Los abonos entran como **filas** de la tabla de pagos, no como columnas
  (RN-02). Es lo que resuelve que seis ventas ya hubieran llenado las tres
  columnas de abono del Excel.
- Ninguna fecha entra sin zona horaria (RN-10).

Correr esto dos veces no duplica: cada fila de Excel queda registrada con su
huella en `migracion_filas`, y la segunda corrida la reconoce y la salta.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.migracion import fuentes
from app.migracion.fuentes import Aporte, Hoja
from app.migracion.identidad import Persona
from app.migracion.lectura import BOGOTA, Fila
from app.migracion.motor import Excepcion, Migracion, Plan
from app.services.auditoria import auditar
from app.models.esquema import (Canales, Casos, Citas, Clientes, EstadosOperativos, MigracionCorridas,
                                MigracionFilas, Negocios, Pagos, Paises, Sedes, Servicios,
                                Solicitantes, Tarifas)

# El negocio es una agencia de visas a Estados Unidos: es el destino de la
# inmensa mayoría de los trámites y el único que aparece en la lista de precios
# con servicios propios. Cuando el archivo no dice el país de la visa, se asume
# este y la fila queda marcada, en vez de dejar 359 trámites sin cargar.
PAIS_POR_DEFECTO = 'US'
ESTADO_POR_DEFECTO = 'registrado'


@dataclass
class Resultado:
    corrida_id: int = 0
    clientes: int = 0
    solicitantes: int = 0
    casos: int = 0
    citas: int = 0
    negocios: int = 0
    pagos: int = 0
    omitidas: int = 0
    excepciones: list[Excepcion] = field(default_factory=list)


class Carga(Migracion):
    """Escribe el plan. Hereda la lectura y la resolución de identidad del motor
    de previsualización para que las dos vean exactamente lo mismo."""

    def __init__(self, db: Session, *, incluir_ventas_sin_cobro: bool = False):
        super().__init__(db)
        self.incluir_ventas_sin_cobro = incluir_ventas_sin_cobro
        self.por_persona: dict[int, tuple[int, int]] = {}    # id(Persona) -> (cliente_id, solicitante_id)
        self.pasaporte_de: dict[str, str] = {}
        self.ds160_de: dict[str, str] = {}
        self.negocio_de_fila: dict[tuple, int] = {}
        self._catalogos_de_carga()

    def _catalogos_de_carga(self) -> None:
        self.estados = {c: i for i, c in
                        self.db.execute(select(EstadosOperativos.id, EstadosOperativos.codigo))}
        self.sedes_nombre = {}
        for sid, pid in self.db.execute(select(Sedes.id, Sedes.pais_id)):
            self.sedes_nombre.setdefault(pid, sid)
        self.canales = {c: i for i, c in self.db.execute(select(Canales.id, Canales.codigo))}
        self.pais_defecto = self.db.scalar(select(Paises.id).where(Paises.iso2 == PAIS_POR_DEFECTO))
        self.tarifas: dict[int, float] = {}
        for sid, valor in self.db.execute(
                select(Tarifas.servicio_id, Tarifas.valor).order_by(Tarifas.personas)):
            self.tarifas.setdefault(sid, float(valor))

    # ------------------------------------------------------------ idempotencia

    def _personas_ya_cargadas(self) -> dict[str, tuple[int, int]]:
        """Los clientes que una corrida anterior ya creó, por nombre normalizado.

        La resolución de identidad es determinista: la misma persona produce
        siempre la misma clave, así que basta comparar por ahí para reconocerla
        sin volver a crearla. Sin esto, la segunda corrida duplica los 852
        clientes aunque no duplique ni un trámite.
        """
        from app.migracion.normalizacion import clave_nombre
        filas = self.db.execute(
            select(Clientes.id, Clientes.nombre, Solicitantes.id)
            .join(Solicitantes, Solicitantes.cliente_id == Clientes.id, isouter=True)
            .where(Clientes.origen_archivo.isnot(None)))
        ya: dict[str, tuple[int, int]] = {}
        for cliente_id, nombre, solicitante_id in filas:
            ya.setdefault(clave_nombre(nombre), (cliente_id, solicitante_id))
        return ya

    def _ya_aplicadas(self) -> dict[tuple, str]:
        """Las filas de Excel que una corrida anterior ya cargó, con su huella.

        La huella permite distinguir «ya la cargué» de «la cargué, pero después
        editaron el Excel»: en el segundo caso se vuelve a mirar en vez de darla
        por hecha.
        """
        aplicadas = select(MigracionCorridas.id).where(MigracionCorridas.modo == 'aplicacion')
        return {(a, h, f): hu for a, h, f, hu in self.db.execute(
            select(MigracionFilas.archivo, MigracionFilas.hoja, MigracionFilas.fila,
                   MigracionFilas.huella)
            .where(MigracionFilas.corrida_id.in_(aplicadas),
                   MigracionFilas.resultado.in_(('creado', 'actualizado'))))}

    # ------------------------------------------------------------------ escribir

    def aplicar(self, *, usuario_id: int | None = None) -> Resultado:
        # El pasaporte no viene en la misma hoja que el trámite: vive en [DS-160]
        # y en el export del SaaS, y se enlaza por nombre.
        # La hoja [DS-160] no describe un trámite —no trae estado ni citas—, así
        # que sus filas no crean casos: traen el pasaporte y el número de
        # formulario de una persona que aparece en otra hoja. Se indexan por
        # nombre y se pegan al trámite que sí existe.
        for _, _, aporte in self.leido:
            if not aporte.persona:
                continue
            clave = aporte.persona.strip().upper()
            if aporte.pasaporte:
                self.pasaporte_de.setdefault(clave, aporte.pasaporte)
            if aporte.ds160:
                self.ds160_de.setdefault(clave, aporte.ds160)

        plan = self.planear()
        r = Resultado(excepciones=list(plan.excepciones))
        ya = self._ya_aplicadas()

        corrida = MigracionCorridas(modo='aplicacion', ejecutada_por=usuario_id, resumen={})
        self.db.add(corrida)
        self.db.flush()
        r.corrida_id = corrida.id

        # 1. Las personas primero: todo lo demás cuelga de ellas.
        from app.migracion.normalizacion import clave_nombre
        conocidas = self._personas_ya_cargadas()
        for persona in plan.personas:
            existente = conocidas.get(clave_nombre(persona.nombre))
            if existente:
                self.por_persona[id(persona)] = existente
                continue
            cliente_id, solicitante_id = self._escribir_persona(persona)
            self.por_persona[id(persona)] = (cliente_id, solicitante_id)
            r.clientes += 1
            r.solicitantes += 1

        # 2. Las filas, en el orden en que se leyeron.
        for hoja, fila, aporte in self.leido:
            if not aporte.persona:
                continue
            huella = fila.huella()
            if ya.get(fila.origen) == huella:
                r.omitidas += 1
                self._registrar(corrida.id, fila, huella, 'sin_cambios',
                                'ya estaba cargada y el Excel no cambió')
                continue

            persona = self.resolvedor.buscar(aporte.persona)
            if persona is None or id(persona) not in self.por_persona:
                self._registrar(corrida.id, fila, huella, 'excepcion',
                                'no se pudo resolver a qué cliente pertenece')
                continue
            cliente_id, solicitante_id = self.por_persona[id(persona)]

            creado = False
            if hoja.trae in ('operacion', 'ambos', 'saas'):
                creado |= self._escribir_operacion(r, fila, aporte, solicitante_id)
            if hoja.trae in ('dinero', 'ambos'):
                creado |= self._escribir_dinero(r, fila, aporte, cliente_id)
            self._registrar(corrida.id, fila, huella, 'creado' if creado else 'omitido',
                            None if creado else 'la fila no aportaba trámite ni venta',
                            cliente_id=cliente_id, solicitante_id=solicitante_id)

        corrida.terminada_en = dt.datetime.now(BOGOTA)
        corrida.resumen = {'clientes': r.clientes, 'solicitantes': r.solicitantes,
                           'casos': r.casos, 'citas': r.citas, 'negocios': r.negocios,
                           'pagos': r.pagos, 'omitidas': r.omitidas,
                           'excepciones': len(r.excepciones)}

        # RNF-05: cargar miles de registros es el cambio más grande que va a
        # recibir este sistema y tiene que dejar rastro en la auditoría, que es
        # la tabla que un trigger hace inalterable. Se registra la corrida, no
        # cada fila: el detalle fila por fila vive en `migracion_filas`, y 4.000
        # entradas de auditoría iguales taparían lo que sí hay que poder leer.
        auditar(self.db, operacion='migracion', entidad='migracion_corridas',
                usuario_id=usuario_id, entidad_id=corrida.id, despues=corrida.resumen)
        self.db.commit()
        return r

    def _registrar(self, corrida_id: int, fila: Fila, huella: str, resultado: str,
                   motivo: str | None, **ids) -> None:
        self.db.add(MigracionFilas(corrida_id=corrida_id, archivo=fila.archivo, hoja=fila.hoja,
                                   fila=fila.numero_fila, huella=huella, resultado=resultado,
                                   motivo=motivo, **ids))

    def _escribir_persona(self, p: Persona) -> tuple[int, int]:
        archivo, hoja, numero = p.menciones[0].origen
        cliente = Clientes(nombre=p.nombre, telefono=p.telefono, email=p.correo,
                           consentimiento=False, archivado=False,
                           observaciones=self._observacion(p),
                           origen_archivo=archivo, origen_hoja=hoja, origen_fila=numero)
        self.db.add(cliente)
        self.db.flush()
        # Quien contrata casi siempre también viaja. Se crea su ficha de
        # solicitante para poder colgarle los trámites; si resulta que no viaja,
        # queda una ficha sin trámites, que no estorba.
        solicitante = Solicitantes(cliente_id=cliente.id, nombre=p.nombre, telefono=p.telefono,
                                   relacion_con_cliente='titular',
                                   origen_archivo=archivo, origen_hoja=hoja, origen_fila=numero)
        # El pasaporte entra cifrado y con su índice ciego, igual que cuando lo
        # escribe una persona desde la aplicación (RNF-04, RF-029). Sale de la
        # hoja DS-160 y del export del SaaS.
        pasaporte = self.pasaporte_de.get(p.nombre.strip().upper())
        if pasaporte:
            limpio = pasaporte.strip().upper()
            solicitante.pasaporte = seg.cifrar(limpio)
            solicitante.pasaporte_indice = seg.indice_ciego(limpio)
        self.db.add(solicitante)
        self.db.flush()
        return cliente.id, solicitante.id

    @staticmethod
    def _observacion(p: Persona) -> str | None:
        partes = []
        if len(p.claves) > 1:
            partes.append(f'Aparecía escrito de {len(p.claves)} formas distintas en los archivos.')
        if p.conflictos:
            partes.append('Al migrar: ' + '; '.join(p.conflictos[:3]) + '.')
        hojas = sorted({m.origen[1] for m in p.menciones})
        if hojas:
            partes.append('Viene de: ' + ', '.join(hojas) + '.')
        return ' '.join(partes) or None

    # ------------------------------------------------------------------ trámites

    def _escribir_operacion(self, r: Resultado, fila: Fila, a: Aporte, solicitante_id: int) -> bool:
        if not (a.estado or a.resultado or a.citas):
            return False

        pais_id = self._pais_de_la_visa(a)
        sede_id = self._sede_de_la_cita(a)
        estado_id = self.estados.get(a.estado or ESTADO_POR_DEFECTO) or self.estados[ESTADO_POR_DEFECTO]
        ultima = max((c for _, c in a.citas), default=None) or dt.datetime.now(BOGOTA)

        caso = Casos(solicitante_id=solicitante_id, pais_id=pais_id, sede_id=sede_id,
                     estado_id=estado_id,
                     # Lo que viene del export del SaaS trae número de solicitud:
                     # esa es la llave con la que después sincroniza (RF-021, RF-032).
                     fuente='saas' if a.id_externo else 'manual', id_externo=a.id_externo,
                     resultado=a.resultado,
                     resultado_nota=a.resultado_nota or a.nota,
                     ultima_actividad_en=ultima,
                     origen_archivo=fila.archivo, origen_hoja=fila.hoja, origen_fila=fila.numero_fila)
        ds160 = a.ds160 or self.ds160_de.pop(a.persona.strip().upper(), None)
        if ds160:
            # Mismo trato que el pasaporte: cifrado y buscable por índice ciego.
            # Se saca del índice al usarlo porque el número es de la persona, no
            # del trámite: si tiene dos trámites, no es el mismo formulario.
            caso.ds160_numero_cifrado = seg.cifrar(ds160.strip())
            caso.ds160_hash = seg.indice_ciego(ds160.strip())
        self.db.add(caso)
        self.db.flush()
        r.casos += 1

        for tipo, cuando in a.citas:
            sin_hora = cuando.hour == 0 and cuando.minute == 0
            self.db.add(Citas(caso_id=caso.id, tipo=tipo, inicia_en=cuando,
                              zona_horaria='America/Bogota',
                              # Sin hora no se puede decir que está programada: se
                              # marca pendiente para que se vea que falta el dato.
                              estado='pendiente' if sin_hora else 'programada',
                              sede_id=sede_id,
                              observaciones='La hora no estaba en el archivo.' if sin_hora else None,
                              origen_archivo=fila.archivo, origen_hoja=fila.hoja,
                              origen_fila=fila.numero_fila))
            r.citas += 1
        return True

    def _pais_de_la_visa(self, a: Aporte) -> int:
        """El país de la visa, que no es el de la cita.

        «País de la Cita» dice dónde queda el consulado —en 337 de 547 trámites,
        Colombia— y eso es la sede. El destino de la visa sale del servicio
        contratado; cuando el archivo no lo dice, se asume Estados Unidos.
        """
        if a.servicio:
            datos = self.servicios.get(a.servicio)
            if datos and datos[1]:
                return datos[1]
        return self.pais_defecto

    def _sede_de_la_cita(self, a: Aporte) -> int | None:
        pais_id = self.paises.get(self._clave(a.pais_cita)) if a.pais_cita else None
        return self.sedes_nombre.get(pais_id) if pais_id else None

    # -------------------------------------------------------------------- dinero

    def _escribir_dinero(self, r: Resultado, fila: Fila, a: Aporte, cliente_id: int) -> bool:
        if not a.servicio or a.servicio not in self.servicios or not a.fecha_venta:
            return False
        if not a.abonos and not self.incluir_ventas_sin_cobro:
            # Una venta sin ningún pago registrado entraría a la cartera como
            # deuda completa. Hasta que VisaNow confirme si se cobró, no se
            # carga: es más fácil agregarla después que quitar una deuda que el
            # sistema ya le está reclamando a un cliente.
            r.excepciones.append(Excepcion(
                *fila.origen, 'Venta sin pagos: no se cargó',
                'Se carga cuando VisaNow confirme si se cobró. Corra la carga con '
                '--incluir-ventas-sin-cobro para incluirla.'))
            return False

        servicio_id = self.servicios[a.servicio][0]
        cantidad = int(a.cantidad) if a.cantidad and a.cantidad >= 1 else 1
        pactado = a.valor_cobrado or 0.0
        lista = self.tarifas.get(servicio_id, pactado) or pactado

        negocio = Negocios(cliente_id=cliente_id, servicio_id=servicio_id,
                           fecha_venta=a.fecha_venta.date(), cantidad_solicitantes=cantidad,
                           valor_lista=lista, descuento=max(0.0, lista - pactado),
                           valor_pactado=pactado, moneda='COP',
                           canal_id=self.canales.get(a.canal) if a.canal else None,
                           observaciones=a.nota,
                           origen_archivo=fila.archivo, origen_hoja=fila.hoja,
                           origen_fila=fila.numero_fila)
        self.db.add(negocio)
        self.db.flush()
        r.negocios += 1

        for i, (cuando, monto) in enumerate(a.abonos):
            self.db.add(Pagos(negocio_id=negocio.id,
                              fecha=(cuando or a.fecha_venta).date(),
                              monto_bruto=monto, costo_medio=0,
                              moneda='COP', estado='confirmado',
                              referencia=f'{fila.hoja} fila {fila.numero_fila} abono {i + 1}',
                              origen_archivo=fila.archivo, origen_hoja=fila.hoja,
                              origen_fila=fila.numero_fila))
            r.pagos += 1
        return True


def aplicar(db: Session, *, incluir_ventas_sin_cobro: bool = False,
            usuario_id: int | None = None) -> Resultado:
    c = Carga(db, incluir_ventas_sin_cobro=incluir_ventas_sin_cobro)
    c.leer()
    return c.aplicar(usuario_id=usuario_id)
