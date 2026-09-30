"""El motor de la migración: primero previsualizar, después aplicar.

La previsualización lee los tres libros completos, aplica todas las reglas y
arma el plan —cuántos clientes, personas, trámites, citas, ventas y pagos
entrarían, y qué se queda por fuera y por qué— **sin escribir un solo dato de
negocio**. Es la actividad 6.1: se revisa el plan con VisaNow y solo entonces se
aplica.

Se hace en dos pasadas porque la identidad no se puede decidir sobre la marcha:
una mención temprana con el nombre incompleto solo se une bien a otra tardía con
el nombre completo si se miran todas juntas. La primera pasada lee y acumula; la
segunda arma el plan con las personas ya resueltas.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.migracion import fuentes
from app.migracion.fuentes import Aporte, Hoja
from app.migracion.identidad import Persona, Resolvedor
from app.migracion.lectura import Fila
from app.models.esquema import MigracionCorridas, MigracionFilas, Paises, Sedes, Servicios


@dataclass
class Excepcion:
    """Algo que no se puede migrar como está. Cada una lleva de dónde salió para
    poder abrir el Excel en esa fila exacta."""
    archivo: str
    hoja: str
    fila: int
    que: str
    que_hacer: str

    @property
    def motivo(self) -> str:
        """El texto sin los datos de la fila, para poder agrupar. Sin esto,
        «Venta de 1.200.000 sin pago» y «Venta de 600.000 sin pago» cuentan como
        dos motivos distintos y el reporte no dice nada."""
        limpio = re.sub(r'[\d.,]{3,}', 'N', self.que)
        limpio = re.sub(r'«[^»]*»', '«…»', limpio)
        return limpio.split(':')[0].strip()[:70] if ':' in limpio else limpio.strip()[:70]


@dataclass
class Plan:
    """Lo que la migración haría. Los números son el entregable de 6.1."""
    personas: list[Persona] = field(default_factory=list)
    clientes: int = 0
    solicitantes: int = 0
    casos: int = 0
    citas: int = 0
    negocios: int = 0
    pagos: int = 0
    valor_vendido: float = 0.0
    valor_cobrado: float = 0.0
    excepciones: list[Excepcion] = field(default_factory=list)
    por_hoja: Counter = field(default_factory=Counter)
    motivos: Counter = field(default_factory=Counter)
    dinero_por_hoja: dict = field(default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0]))
    filas_leidas: int = 0

    @property
    def cartera(self) -> float:
        """Lo que quedaría por cobrar. Es el número que VisaNow puede comparar
        contra su propia cuenta: si no coincide, la migración está mal."""
        return self.valor_vendido - self.valor_cobrado

    def anotar(self, e: Excepcion) -> None:
        self.excepciones.append(e)
        self.motivos[e.motivo] += 1


class Migracion:
    def __init__(self, db: Session):
        self.db = db
        self.resolvedor = Resolvedor()
        self.leido: list[tuple[Hoja, Fila, Aporte]] = []
        self._catalogos()

    def _catalogos(self) -> None:
        self.paises = {self._clave(n): i for i, n in self.db.execute(select(Paises.id, Paises.nombre))}
        self.sedes_por_pais = defaultdict(list)
        for sid, pid in self.db.execute(select(Sedes.id, Sedes.pais_id)):
            self.sedes_por_pais[pid].append(sid)
        self.servicios = {c: (i, p) for i, c, p in
                          self.db.execute(select(Servicios.id, Servicios.codigo, Servicios.pais_id))}

    @staticmethod
    def _clave(texto: str | None) -> str:
        from app.migracion.normalizacion import sin_tildes
        return ' '.join(sin_tildes(texto or '').lower().split())

    # ------------------------------------------------------------- primera pasada

    def leer(self) -> None:
        for hoja in fuentes.CATALOGO:
            for fila, aporte in fuentes.recorrer(hoja):
                self.leido.append((hoja, fila, aporte))
                if aporte.persona:
                    self.resolvedor.agregar(aporte.persona, telefono=aporte.telefono,
                                            correo=aporte.correo, origen=fila.origen)
                for otro in aporte.acompanantes:
                    self.resolvedor.agregar(otro, telefono=aporte.telefono, origen=fila.origen)

    # ------------------------------------------------------------ segunda pasada

    def planear(self) -> Plan:
        plan = Plan()
        personas = self.resolvedor.resolver()
        plan.personas = personas
        plan.clientes = len(personas)
        plan.filas_leidas = len(self.leido)

        for hoja, fila, aporte in self.leido:
            plan.por_hoja[f'{hoja.archivo}::{hoja.nombre}'] += 1

            if not aporte.persona:
                plan.anotar(Excepcion(*fila.origen, 'Fila sin nombre de cliente utilizable',
                                      'Revisar si es una fila de trabajo o si al cliente le falta '
                                      'el nombre. Sin nombre no se puede crear la ficha.'))
                continue

            for problema in aporte.problemas:
                plan.anotar(Excepcion(*fila.origen, problema,
                                      'Corregir en el Excel antes de aplicar la migración, '
                                      'o confirmar que se cargue sin ese dato.'))

            if hoja.trae in ('operacion', 'ambos', 'saas'):
                self._planear_operacion(plan, hoja, fila, aporte)
            if hoja.trae in ('dinero', 'ambos'):
                self._planear_dinero(plan, hoja, fila, aporte)

        for p in personas:
            for conflicto in p.conflictos:
                origen = p.menciones[0].origen
                plan.anotar(Excepcion(*origen, f'Identidad: {conflicto}',
                                      'Confirmar si son la misma persona o dos personas de la '
                                      'misma familia. Si son familia, así se cargan: cada una con '
                                      'su ficha, agrupadas.'))
        return plan

    def _planear_operacion(self, plan: Plan, hoja: Hoja, fila: Fila, a: Aporte) -> None:
        plan.solicitantes += 1 + len(a.acompanantes)

        pais_id = self.paises.get(self._clave(a.pais_cita))
        if a.pais_cita and pais_id is None:
            plan.anotar(Excepcion(*fila.origen,
                                  f'País de la cita: «{a.pais_cita[:30]}» no está en el catálogo',
                                  'Agregar el país y su sede al catálogo, o corregir el nombre.'))
        if a.pais_cita and pais_id and not self.sedes_por_pais.get(pais_id):
            plan.anotar(Excepcion(*fila.origen,
                                  f'Sede: no hay ninguna sembrada para «{a.pais_cita[:30]}»',
                                  'Dar el nombre exacto de la sede de ese país para crearla.'))

        # Un trámite se abre si la fila dice algo de la operación: estado,
        # resultado o al menos una cita.
        if a.estado or a.resultado or a.citas:
            plan.casos += 1
            plan.citas += len(a.citas)
            if not a.estado and not a.resultado:
                plan.anotar(Excepcion(*fila.origen, 'Trámite sin estado',
                                      'Entra como «registrado». Confirmar en qué punto está.'))
            self._revisar_citas(plan, fila, a)

    def _revisar_citas(self, plan: Plan, fila: Fila, a: Aporte) -> None:
        por_tipo = {t: c for t, c in a.citas}
        cas, entrevista = por_tipo.get('cas'), por_tipo.get('entrevista')
        if cas and entrevista and cas > entrevista:
            plan.anotar(Excepcion(*fila.origen,
                                  'Fechas imposibles: la cita del CAS es posterior a la entrevista',
                                  'Corregir en el Excel. Se cargan como están y quedan marcadas.'))
        for tipo, cuando in a.citas:
            if cuando.hour == 0 and cuando.minute == 0:
                plan.anotar(Excepcion(*fila.origen, f'Cita de {tipo} sin hora',
                                      'Entra como «pendiente» a las 00:00 para que se vea que '
                                      'falta la hora, en vez de inventar una.'))

    def _planear_dinero(self, plan: Plan, hoja: Hoja, fila: Fila, a: Aporte) -> None:
        if not a.servicio:
            plan.anotar(Excepcion(*fila.origen, 'Venta sin servicio reconocible',
                                  'Agregar la escritura al diccionario de homologación o '
                                  'corregirla en el Excel.'))
            return
        if a.servicio not in self.servicios:
            plan.anotar(Excepcion(*fila.origen,
                                  f'El servicio «{a.servicio}» no está sembrado en el catálogo',
                                  'Crear el servicio y su tarifa antes de aplicar.'))
            return
        if not a.fecha_venta:
            plan.anotar(Excepcion(*fila.origen, 'Venta sin fecha',
                                  'La fecha de venta es obligatoria. Si la fila solo trae la del '
                                  'pago, se usa esa y queda anotado.'))
            return

        plan.negocios += 1
        resumen = plan.dinero_por_hoja[f'{hoja.archivo}::{hoja.nombre}']
        resumen[2] += 1
        resumen[0] += a.valor_cobrado or 0.0
        resumen[1] += sum(m for _, m in a.abonos)
        if a.valor_cobrado:
            plan.valor_vendido += a.valor_cobrado
        else:
            plan.anotar(Excepcion(*fila.origen, 'Venta sin valor pactado',
                                  'Entra en cero, que en el estado financiero sale como «sin '
                                  'acuerdo». VisaNow tiene que decir cuánto se había pactado.'))
        plan.pagos += len(a.abonos)
        plan.valor_cobrado += sum(m for _, m in a.abonos)

        if a.valor_cobrado and not a.abonos:
            plan.anotar(Excepcion(*fila.origen,
                                  f'Venta de {a.valor_cobrado:,.0f} sin ningún pago registrado',
                                  'Entraría a la cartera como deuda completa. Confirmar si se '
                                  'cobró y el registro está en otra hoja.'))
        if a.valor_cobrado and a.abonos and sum(m for _, m in a.abonos) > a.valor_cobrado + 1:
            plan.anotar(Excepcion(*fila.origen, 'Los abonos suman más que el valor cobrado',
                                  'Revisar: puede ser un pago doble o un valor mal escrito.'))

    # ------------------------------------------------------------------ registro

    def registrar(self, plan: Plan, *, modo: str, usuario_id: int | None = None) -> MigracionCorridas:
        """Deja constancia de la corrida y de qué pasó con cada fila.

        En previsualización esto es lo único que se escribe: ni un cliente, ni
        una venta. Permite comparar dos previsualizaciones y ver qué cambió en
        los Excel entre una y otra.
        """
        corrida = MigracionCorridas(modo=modo, ejecutada_por=usuario_id, resumen={
            'filas_leidas': plan.filas_leidas,
            'clientes': plan.clientes, 'solicitantes': plan.solicitantes,
            'casos': plan.casos, 'citas': plan.citas,
            'negocios': plan.negocios, 'pagos': plan.pagos,
            'valor_vendido': round(plan.valor_vendido, 2),
            'valor_cobrado': round(plan.valor_cobrado, 2),
            'cartera': round(plan.cartera, 2),
            'excepciones': len(plan.excepciones),
        })
        self.db.add(corrida)
        self.db.flush()

        con_excepcion = {(e.archivo, e.hoja, e.fila) for e in plan.excepciones}
        for hoja, fila, aporte in self.leido:
            self.db.add(MigracionFilas(
                corrida_id=corrida.id, archivo=fila.archivo, hoja=fila.hoja, fila=fila.numero_fila,
                huella=fila.huella(),
                resultado='excepcion' if fila.origen in con_excepcion else 'creado',
                motivo=None))
        self.db.commit()
        return corrida


def previsualizar(db: Session, *, usuario_id: int | None = None) -> tuple[Plan, MigracionCorridas]:
    m = Migracion(db)
    m.leer()
    plan = m.planear()
    corrida = m.registrar(plan, modo='previsualizacion', usuario_id=usuario_id)
    return plan, corrida
