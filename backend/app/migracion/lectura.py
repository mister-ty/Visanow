"""Leer una celda de Excel sin que mienta.

Los tres libros llevan años de uso y traen de todo: errores de fórmula que
`data_only=True` devuelve como el texto «#VALUE!», números de serie de fecha
imposibles, celulares guardados como número (que `str()` convierte en
«3001234567.0», con un dígito que no existe), montos escritos en miles y celdas
con dos personas adentro.

Cada función de aquí devuelve el valor limpio o `None`, y nunca revienta. Lo que
no se puede leer lo reporta quien llama, para que termine en el reporte de
excepciones en vez de entrar mal a la base.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import openpyxl

BOGOTA = ZoneInfo('America/Bogota')

# `data_only=True` devuelve el error de la fórmula como texto, no como nulo.
ERRORES_EXCEL = ('#VALUE!', '#REF!', '#DIV/0!', '#N/A', '#NAME?', '#NULL!', '#NUM!', '#SPILL!')

# El negocio existe desde 2023 y las ventas llegan hasta hoy. Fuera de esta
# ventana no es una fecha: es un serial corrupto o una celda mal formateada.
FECHA_MINIMA = dt.date(2019, 1, 1)
FECHA_MAXIMA = dt.date(2028, 12, 31)


@dataclass
class Celda:
    """El valor leído más la razón por la que no se pudo leer, si aplica."""
    valor: Any = None
    problema: str | None = None

    def __bool__(self) -> bool:
        return self.valor is not None


def texto(bruto: Any) -> Celda:
    """Texto limpio. Un número entero guardado como float pierde el «.0»: es lo
    que convierte el celular 3001234567 en «3001234567.0» y lo daña."""
    if bruto is None:
        return Celda()
    if isinstance(bruto, str):
        t = bruto.strip()
        if not t:
            return Celda()
        if t.upper() in ERRORES_EXCEL or (t.startswith('#') and t.upper().rstrip('!') + '!' in ERRORES_EXCEL):
            return Celda(problema=f'la celda trae un error de Excel ({t})')
        return Celda(' '.join(t.split()))
    if isinstance(bruto, bool):
        return Celda('sí' if bruto else 'no')
    if isinstance(bruto, float):
        return Celda(str(int(bruto)) if bruto.is_integer() else str(bruto))
    if isinstance(bruto, (dt.datetime, dt.date)):
        return Celda(bruto.isoformat())
    return Celda(str(bruto).strip() or None)


def numero(bruto: Any) -> Celda:
    """Un monto o una cantidad. Acepta el texto con separadores colombianos
    ($ 1.250.000) pero no inventa: si no convierte, lo dice."""
    if bruto is None:
        return Celda()
    if isinstance(bruto, bool):
        return Celda(problema='la celda es verdadero/falso, no un número')
    if isinstance(bruto, (int, float)):
        return Celda(float(bruto))
    t = texto(bruto)
    if not t:
        return Celda(problema=t.problema)
    limpio = (t.valor.replace('$', '').replace(' ', '').replace('\xa0', '')
              .replace('COP', '').replace('cop', ''))
    # En Colombia el punto separa miles y la coma decimales
    if ',' in limpio and '.' in limpio:
        limpio = limpio.replace('.', '').replace(',', '.')
    elif ',' in limpio:
        limpio = limpio.replace(',', '.')
    elif limpio.count('.') > 1:
        limpio = limpio.replace('.', '')
    elif '.' in limpio:
        entero, _, decimal = limpio.partition('.')
        if len(decimal) == 3:          # «1.250» son mil doscientos cincuenta, no 1,25
            limpio = entero + decimal
    try:
        return Celda(float(limpio))
    except ValueError:
        return Celda(problema=f'«{t.valor[:40]}» no es un número')


def fecha(bruto: Any) -> Celda:
    """Una fecha con zona horaria de Bogotá.

    El servidor PostgreSQL corre en UTC: una fecha sin zona entra cinco horas
    antes de lo que dice el Excel, y una cita de las 8:30 a. m. queda registrada
    a las 3:30 a. m. Por eso aquí nunca sale un datetime ingenuo.
    """
    if bruto is None:
        return Celda()
    if isinstance(bruto, dt.datetime):
        d = bruto
    elif isinstance(bruto, dt.date):
        d = dt.datetime.combine(bruto, dt.time())
    elif isinstance(bruto, (int, float)) and not isinstance(bruto, bool):
        try:                                    # serial de Excel (base 1899-12-30)
            d = dt.datetime(1899, 12, 30) + dt.timedelta(days=float(bruto))
        except (OverflowError, ValueError):
            return Celda(problema=f'el número {bruto:.0f} no corresponde a una fecha')
    else:
        t = texto(bruto)
        if not t:
            return Celda(problema=t.problema)
        for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d/%m/%y'):
            try:
                d = dt.datetime.strptime(t.valor[:10], formato)
                break
            except ValueError:
                continue
        else:
            return Celda(problema=f'«{t.valor[:30]}» no es una fecha')
    if not (FECHA_MINIMA <= d.date() <= FECHA_MAXIMA):
        return Celda(problema=f'la fecha {d.date().isoformat()} está fuera del periodo del negocio')
    return Celda(d.replace(tzinfo=BOGOTA) if d.tzinfo is None else d.astimezone(BOGOTA))


def hora_de(bruto: Any) -> dt.time | None:
    """La hora que trae una celda de fecha, si trae alguna distinta de medianoche."""
    c = fecha(bruto)
    if not c:
        return None
    t = c.valor.timetz()
    return None if (t.hour == 0 and t.minute == 0) else t


# ------------------------------------------------------------------- las hojas

@dataclass
class Fila:
    """Una fila de una hoja, con de dónde salió, para poder rastrearla y para
    que la migración sepa si ya la cargó."""
    archivo: str
    hoja: str
    numero_fila: int
    celdas: dict[str, Any]
    problemas: list[str] = field(default_factory=list)

    def bruto(self, columna: str) -> Any:
        return self.celdas.get(columna)

    def texto(self, columna: str) -> str | None:
        c = texto(self.bruto(columna))
        if c.problema:
            self.problemas.append(f'{columna}: {c.problema}')
        return c.valor

    def numero(self, columna: str) -> float | None:
        c = numero(self.bruto(columna))
        if c.problema:
            self.problemas.append(f'{columna}: {c.problema}')
        return c.valor

    def fecha(self, columna: str) -> dt.datetime | None:
        c = fecha(self.bruto(columna))
        if c.problema:
            self.problemas.append(f'{columna}: {c.problema}')
        return c.valor

    def vacia(self) -> bool:
        return all(texto(v).valor is None for v in self.celdas.values())

    @property
    def origen(self) -> tuple[str, str, int]:
        return (self.archivo, self.hoja, self.numero_fila)

    def huella(self) -> str:
        """sha256 del contenido. Si el Excel se edita después de migrar, cambia
        y la fila se vuelve a mirar en vez de darse por hecha."""
        crudo = json.dumps({k: texto(v).valor for k, v in sorted(self.celdas.items())},
                           ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(crudo.encode('utf-8')).hexdigest()


# Un libro se abre una sola vez aunque se lean seis de sus hojas. Sin esto,
# CUENTAS VISANOW se cargaba entero seis veces y el proceso se quedaba sin
# memoria a mitad de la segunda corrida.
_LIBROS: dict[pathlib.Path, Any] = {}


def abrir(ruta: pathlib.Path):
    libro = _LIBROS.get(ruta)
    if libro is None:
        libro = _LIBROS[ruta] = openpyxl.load_workbook(ruta, data_only=True, read_only=False)
    return libro


def cerrar_libros() -> None:
    """Suelta los libros abiertos. Se llama al terminar una corrida."""
    for libro in _LIBROS.values():
        libro.close()
    _LIBROS.clear()


def leer_hoja(ruta: pathlib.Path, hoja: str, *, fila_encabezado: int = 1,
              hasta_vacias: int = 40) -> Iterator[Fila]:
    """Recorre una hoja devolviendo filas con dato.

    Las hojas tienen fórmulas arrastradas cientos de filas más abajo del último
    dato real: `max_row` dice 1004 donde hay 262 ventas. Se corta después de
    `hasta_vacias` filas seguidas sin nada.
    """
    wb = abrir(ruta)
    if hoja not in wb.sheetnames:
        raise KeyError(f'la hoja «{hoja}» no está en {ruta.name}. Hay: {wb.sheetnames}')
    h = wb[hoja]
    titulos: dict[int, str] = {}
    for c in range(1, h.max_column + 1):
        t = texto(h.cell(fila_encabezado, c).value)
        if t:
            titulos[c] = t.valor
    if not titulos:
        wb.close()
        return

    vacias = 0
    for r in range(fila_encabezado + 1, h.max_row + 1):
        celdas = {titulo: h.cell(r, c).value for c, titulo in titulos.items()}
        fila = Fila(archivo=ruta.name, hoja=hoja, numero_fila=r, celdas=celdas)
        if fila.vacia():
            vacias += 1
            if vacias >= hasta_vacias:
                break
            continue
        vacias = 0
        yield fila
