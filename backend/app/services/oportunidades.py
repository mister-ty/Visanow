"""El embudo comercial: del lead a la venta (RF-010 a RF-015).

Hoy esto no existe en ninguna parte. La hoja `pauta` del libro de clientes tiene
145 leads de publicidad con nombre, teléfono, ciudad, interés y «calidad del
lead», pero no hay forma de saber cuáles se convirtieron: la venta aparece en
otro libro, sin decir de dónde salió el cliente. Por eso nadie puede responder
qué campaña trae clientes que compran, que es justo lo que decide dónde se pone
la plata de publicidad.

Dos reglas que vienen de cómo se trabaja de verdad:

- **Una oportunidad abierta siempre tiene próxima acción.** Es la misma regla
  que RN-04 pide para los trámites. Un lead sin próximo paso no está en el
  embudo: está olvidado, y la diferencia entre las dos cosas es la que hace que
  un negocio se caiga sin que nadie se entere.
- **Perder se explica.** Cerrar como perdido exige un motivo del catálogo
  (RF-015). «No respondió» y «precio» llevan a decisiones distintas; «se perdió»
  no lleva a ninguna.
- **El lead llegó el día que llegó.** La fecha se captura, no se asigna. Un lead
  transcrito de la hoja «pauta» o del formulario de Google se digita días
  después, y con la fecha de digitación «cuántos leads trajo la pauta de
  septiembre» se responde mal. Quién lo digitó y cuándo queda en la auditoría,
  que es donde se pregunta eso.

Sobre «fuente» (RF-010) — decisión tomada, no olvido
----------------------------------------------------
El texto del RF-010 pide «canal, campaña/influencer/referido, interés, país,
asesor y fuente». El Anexo A de la especificación v1.0, que es el que lista los
campos mínimos de una oportunidad, NO la menciona: «Fecha, servicio, país,
asesor, canal/campaña, estado, valor estimado, próxima acción, motivo pérdida».
Donde el Anexo A sí dice «fuente» es en el caso, y ahí significa otra cosa: si
el trámite entró por el SaaS, a mano o mezclado (RF-021, `casos.fuente`).

Se decidió NO abrir una segunda columna «fuente» en oportunidades. De dónde
salió un lead se responde con tres datos que ya existen y que son de catálogo:
el **canal** (por dónde llegó), la **campaña** (cuál pauta o influencer) y
**quién lo recomendó** cuando llegó por recomendación, que es el canal que más
vende en los archivos históricos. Dos campos que contestan la misma pregunta
terminan contestando distinto —es lo que pasa hoy entre las hojas PAGOS y REV
PAGOS, donde la misma deuda difiere en 37 millones—, y un «fuente» de texto
libre al lado de un canal de catálogo convierte el informe de publicidad en una
lista de sinónimos: «insta», «Instagram», «ig», «reel».

Lo que sí había que arreglar, y se arregló, es que los tres se puedan registrar
Y leer de vuelta: el referido se guardaba y la API no lo devolvía nunca, y la
campaña de catálogo no se alcanzaba desde ninguna pantalla.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Invalido, NoEncontrado
from app.models.esquema import (
    Campanias,
    Clientes,
    EstadosComerciales,
    MotivosPerdida,
    Oportunidades,
    Usuarios,
)
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')
ESTADO_INICIAL = 'nuevo_lead'

CAMPOS = ('servicio_id', 'pais_id', 'canal_id', 'campania_id', 'campania', 'asesor_id',
          'valor_estimado', 'proxima_accion', 'proxima_accion_fecha', 'referido_por_cliente_id')

#: Ids que apuntan a otra tabla y que, si no existen, revientan contra la llave
#: foránea con un 500: «error del servidor» en la cara de quien digita, sin
#: decirle qué corregir.
REFERENCIAS = (('referido_por_cliente_id', Clientes, 'El cliente que lo recomendó no existe.'),
               ('campania_id', Campanias, 'La campaña no existe.'))


def _ahora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _hoy(ahora: dt.datetime | None = None) -> dt.date:
    """Qué día es hoy en Bogotá, no en el reloj del servidor.

    El contenedor corre con TZ=UTC (Dockerfile) y Colombia está en UTC-5: desde
    las siete de la noche de Bogotá, para el servidor ya es mañana. La agencia
    atiende de noche, así que sin esto un lead registrado hoy a las ocho se
    aceptaría con la fecha de mañana y quedaría escondido de la lista de fríos.

    Recibe el instante para poder probarse: este equipo está en Bogotá, así que
    una prueba que compare contra `date.today()` pasaría sin comprobar nada.
    """
    return (ahora or _ahora()).astimezone(BOGOTA).date()


def _llegada(fecha: dt.date, *, ahora: dt.datetime | None = None) -> dt.datetime:
    """La fecha en que llegó el lead, convertida al instante que se guarda.

    Se guarda el comienzo de ese día en Bogotá para que la fecha que se lee de
    vuelta sea la misma que se escribió: con la hora del servidor, un lead del
    30 de septiembre se leería como del 1.º de octubre y se le cambiaría de mes
    al informe de la pauta.
    """
    if fecha > _hoy(ahora):
        raise Invalido('Un lead no puede haber llegado mañana. Revise la fecha.',
                       codigo='fecha_futura')
    return dt.datetime.combine(fecha, dt.time.min, tzinfo=BOGOTA)


def _valida_referencias(db: Session, datos: dict) -> None:
    for campo, modelo, mensaje in REFERENCIAS:
        valor = datos.get(campo)
        if valor is not None and db.get(modelo, valor) is None:
            raise NoEncontrado(mensaje)


def estado(db: Session, codigo: str) -> EstadosComerciales:
    e = db.scalar(select(EstadosComerciales).where(EstadosComerciales.codigo == codigo))
    if e is None:
        raise NoEncontrado(f'El estado comercial «{codigo}» no existe.')
    return e


#: Lo que la pantalla necesita junto con la oportunidad. El motivo de pérdida y
#: quién la recomendó van aquí porque son nombres, no números: un motivo que
#: sale como «3» no explica nada, y es lo único que queda de un negocio perdido.
ACOMPANAN = ('cliente', 'estado', 'asesor', 'motivo_perdida', 'referido_por_cliente')


def _con_lo_que_acompana() -> list:
    return [selectinload(getattr(Oportunidades, nombre)) for nombre in ACOMPANAN]


def obtener(db: Session, oportunidad_id: int, *, actor: Usuarios | None = None) -> Oportunidades:
    o = db.get(Oportunidades, oportunidad_id, options=_con_lo_que_acompana())
    if o is None:
        raise NoEncontrado('La oportunidad no existe.')
    if actor is not None and not _alcanza(actor, o):
        # Igual que en los trámites: se responde como si no existiera, porque
        # decir «existe pero no es suya» ya revela que es cliente de VisaNow.
        raise NoEncontrado('La oportunidad no existe.')
    return o


def _alcanza(actor: Usuarios, o: Oportunidades) -> bool:
    return actor.alcance == 'todos' or o.asesor_id == actor.id


def crear(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Oportunidades:
    """Un lead nuevo. Nace en «nuevo lead» y con asesor: sin dueño no lo
    trabaja nadie, y es el error que más se repite en los archivos actuales.

    `fecha` es cuándo llegó el lead, no cuándo se digitó: viene vacía desde la
    pantalla cuando el lead es de hoy, y se escribe cuando se está transcribiendo
    la hoja de pauta o el formulario de Google de la semana pasada.
    """
    cliente_id = datos.get('cliente_id')
    if not cliente_id or db.get(Clientes, cliente_id) is None:
        raise NoEncontrado('El cliente no existe.')
    if not datos.get('proxima_accion'):
        raise Invalido('Escriba cuál es la próxima acción. Un lead sin próximo paso se pierde.')
    _valida_referencias(db, datos)

    o = Oportunidades(cliente_id=cliente_id, estado_id=estado(db, ESTADO_INICIAL).id,
                      asesor_id=datos.get('asesor_id') or actor.id,
                      **{k: v for k, v in datos.items() if k in CAMPOS and k != 'asesor_id'})
    if datos.get('fecha') is not None:
        o.creado_en = _llegada(datos['fecha'])
    db.add(o)
    db.flush()
    auditar(db, operacion='insert', entidad='oportunidades', usuario_id=actor.id,
            entidad_id=o.id, despues=instantanea(o), ip=ip)
    db.commit()
    return o


def editar(db: Session, actor: Usuarios, oportunidad_id: int, cambios: dict,
           ip: str | None = None) -> Oportunidades:
    o = obtener(db, oportunidad_id, actor=actor)
    _valida_referencias(db, cambios)
    antes = instantanea(o)
    for campo, valor in cambios.items():
        if campo in CAMPOS:
            setattr(o, campo, valor)
    if cambios.get('fecha') is not None:
        o.creado_en = _llegada(cambios['fecha'])
    db.flush()
    # Lo que se devuelve y lo que se audita salen de la base, no de lo que quedó
    # en memoria: al corregir un id —el del referido, por ejemplo— el nombre que
    # lo acompaña ya no es el de antes, y devolver el viejo hace que quien
    # corrigió crea que no se guardó y lo vuelva a hacer.
    db.expire(o)
    auditar(db, operacion='update', entidad='oportunidades', usuario_id=actor.id,
            entidad_id=o.id, antes=antes, despues=instantanea(o), ip=ip)
    db.commit()
    return o


def mover(db: Session, actor: Usuarios, oportunidad_id: int, *, codigo_destino: str,
          motivo_perdida: str | None = None, nota: str | None = None,
          proxima_accion: str | None = None, ip: str | None = None) -> Oportunidades:
    """Mueve la oportunidad por el embudo.

    A diferencia de los trámites, aquí el orden no se controla: un lead puede
    saltar de «contactado» a «ganado» si el cliente dijo que sí de una. Lo que
    sí se exige es lo que no se puede reconstruir después: el motivo cuando se
    pierde, y la próxima acción mientras siga abierta.
    """
    o = obtener(db, oportunidad_id, actor=actor)
    destino = estado(db, codigo_destino)
    antes = instantanea(o)
    anterior = o.estado.codigo if o.estado else None

    if destino.requiere_motivo:
        if not motivo_perdida:
            raise Invalido('Diga por qué se perdió. «No respondió» y «precio» llevan a '
                           'decisiones distintas; «se perdió» no lleva a ninguna.',
                           codigo='falta_motivo')
        m = db.scalar(select(MotivosPerdida).where(MotivosPerdida.codigo == motivo_perdida))
        if m is None:
            raise Invalido(f'El motivo «{motivo_perdida}» no está en el catálogo.')
        o.motivo_perdida_id, o.motivo_perdida = m.id, m
        o.motivo_perdida_nota = nota

    if not destino.es_cierre:
        siguiente = proxima_accion or o.proxima_accion
        if not siguiente:
            raise Invalido('Escriba cuál es la próxima acción antes de mover la oportunidad.',
                           codigo='falta_proxima_accion')
        o.proxima_accion = siguiente
        o.cerrado_en = None
        # Una oportunidad que se reabre deja de estar perdida. Si el motivo se
        # quedara pegado, la lista mostraría un lead vivo «perdido por precio»:
        # el dato más viejo contradiciendo al más nuevo en la misma fila.
        o.motivo_perdida_id, o.motivo_perdida, o.motivo_perdida_nota = None, None, None
    else:
        o.cerrado_en = _ahora()

    o.estado_id = destino.id
    o.estado = destino
    db.flush()
    auditar(db, operacion='update', entidad='oportunidades', usuario_id=actor.id, entidad_id=o.id,
            antes=antes, despues=instantanea(o) | {'estado_anterior': anterior}, ip=ip)
    db.commit()
    return o


def registrar_contacto(db: Session, actor: Usuarios, oportunidad_id: int, *,
                       proxima_accion: str | None = None,
                       proxima_accion_fecha: dt.date | None = None,
                       ip: str | None = None) -> Oportunidades:
    """RF-012 del lado comercial: queda cuándo fue la última vez que se le habló
    y qué sigue. Es lo que alimenta la lista de «leads fríos»."""
    o = obtener(db, oportunidad_id, actor=actor)
    o.ultimo_contacto_en = _ahora()
    if proxima_accion:
        o.proxima_accion = proxima_accion
    if proxima_accion_fecha is not None:
        o.proxima_accion_fecha = proxima_accion_fecha
    db.flush()
    auditar(db, operacion='contacto', entidad='oportunidades', usuario_id=actor.id,
            entidad_id=o.id, despues={'ultimo_contacto_en': o.ultimo_contacto_en}, ip=ip)
    db.commit()
    return o


# ----------------------------------------------------------------------- listas

def _recortes(*, actor: Usuarios | None = None, asesor_id: int | None = None,
              canal_id: int | None = None, servicio_id: int | None = None,
              campania_id: int | None = None, frias_desde: int | None = None,
              texto: str | None = None) -> list:
    """Los filtros que deciden QUÉ oportunidades se están mirando.

    Están aquí, en un solo lugar, porque la lista y el embudo tienen que
    obedecer los mismos: el tablero muestra el conteo de tarjetas al lado del
    total en pesos de la columna, y cuando cada número salía de una consulta
    distinta la pantalla se contradecía sola —al filtrar por asesor cambiaban
    las tarjetas y el dinero seguía siendo el de toda la agencia—. El número
    equivocado era el que está en grande.

    No incluye el estado ni las cerradas: esos recortan la lista, pero en el
    tablero el estado ES la columna.
    """
    # RNF-03: el alcance se aplica acá, en el servicio, y no en la ruta. Una
    # comprobación que solo esté en la ruta se la salta cualquiera que llame la
    # API directo.
    recortes = []
    if actor is not None and actor.alcance != 'todos':
        recortes.append(Oportunidades.asesor_id == actor.id)
    for columna, valor in ((Oportunidades.asesor_id, asesor_id),
                           (Oportunidades.canal_id, canal_id),
                           (Oportunidades.servicio_id, servicio_id),
                           (Oportunidades.campania_id, campania_id)):
        if valor:
            recortes.append(columna == valor)
    if frias_desde:
        # Sin contacto hace más de N días, contando desde que se creó si nunca
        # se le ha hablado: un lead que nadie tocó es el más frío de todos.
        limite = _ahora() - dt.timedelta(days=frias_desde)
        recortes.append(
            func.coalesce(Oportunidades.ultimo_contacto_en, Oportunidades.creado_en) < limite)
    if texto:
        # El nombre del cliente va por subconsulta y no por JOIN para que el
        # mismo recorte sirva en el embudo, donde la oportunidad entra por un
        # LEFT JOIN y un JOIN más borraría los pasos vacíos.
        patron = func.lower(func.sin_tildes(f'%{texto}%'))
        recortes.append(or_(
            Oportunidades.proxima_accion.ilike(f'%{texto}%'),
            Oportunidades.cliente_id.in_(
                select(Clientes.id).where(Clientes.nombre_busqueda.like(patron)))))
    return recortes


def listar(db: Session, *, actor: Usuarios | None = None, estado_codigo: str | None = None,
           asesor_id: int | None = None, canal_id: int | None = None,
           servicio_id: int | None = None, campania_id: int | None = None,
           incluir_cerradas: bool = False, frias_desde: int | None = None,
           texto: str | None = None, pagina: int = 1,
           tamano: int = 50) -> tuple[int, list[Oportunidades]]:
    """La lista filtrable del embudo (RF-011), paginada.

    `incluir_cerradas` existe para poder leer una oportunidad ganada o perdida:
    sin ella, el motivo por el que se perdió un negocio no se puede consultar en
    ninguna parte, y es lo único que queda de ese negocio.
    """
    consulta: Select = (select(Oportunidades)
                        .join(EstadosComerciales, EstadosComerciales.id == Oportunidades.estado_id)
                        .options(*_con_lo_que_acompana())
                        .where(*_recortes(actor=actor, asesor_id=asesor_id, canal_id=canal_id,
                                          servicio_id=servicio_id, campania_id=campania_id,
                                          frias_desde=frias_desde, texto=texto)))
    if not incluir_cerradas:
        consulta = consulta.where(EstadosComerciales.es_cierre.is_(False))
    if estado_codigo:
        consulta = consulta.where(EstadosComerciales.codigo == estado_codigo)

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    # El id desempata. Varios leads transcritos en la misma tanda quedan con la
    # misma fecha de llegada, y un orden que empata reparte las filas distinto
    # en cada consulta: al pasar de página se repiten unas y se pierden otras.
    filas = list(db.scalars(
        consulta.order_by(EstadosComerciales.orden, Oportunidades.creado_en.desc(),
                          Oportunidades.id.desc())
        .offset((pagina - 1) * tamano).limit(tamano)))
    return total, filas


def embudo(db: Session, *, actor: Usuarios | None = None, asesor_id: int | None = None,
           canal_id: int | None = None, servicio_id: int | None = None,
           campania_id: int | None = None, frias_desde: int | None = None,
           texto: str | None = None) -> list[tuple[EstadosComerciales, int, float]]:
    """Cuántas oportunidades y cuánto dinero hay en cada paso del embudo.

    Es el tablero Kanban en números: dónde se están quedando los clientes.

    Recibe los mismos filtros que la lista y los aplica en la condición del
    LEFT JOIN, no en el WHERE: así un paso que se queda sin oportunidades sale
    en cero en vez de desaparecer. Una columna que no se dibuja es un paso al
    que nadie puede arrastrar una tarjeta.
    """
    condiciones = [Oportunidades.estado_id == EstadosComerciales.id,
                   *_recortes(actor=actor, asesor_id=asesor_id, canal_id=canal_id,
                              servicio_id=servicio_id, campania_id=campania_id,
                              frias_desde=frias_desde, texto=texto)]
    consulta = (select(EstadosComerciales,
                       func.count(Oportunidades.id),
                       func.coalesce(func.sum(Oportunidades.valor_estimado), 0))
                .outerjoin(Oportunidades, and_(*condiciones))
                .where(EstadosComerciales.activo.is_(True))
                .group_by(EstadosComerciales.id)
                .order_by(EstadosComerciales.orden))
    return [(e, n, float(v)) for e, n, v in db.execute(consulta)]


def dias_sin_contacto(o: Oportunidades) -> int:
    referencia = o.ultimo_contacto_en or o.creado_en
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=BOGOTA)
    return (_ahora() - referencia).days
