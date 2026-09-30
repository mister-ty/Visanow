"""Normalizar nombres y teléfonos para poder reconocer a la misma persona.

Ninguna de las tres fuentes tiene número de documento: se buscó en las 27 hojas
y no hay una sola columna de cédula. Eso significa que el índice único que en el
sistema nuevo impide dos fichas con el mismo documento no protege nada durante
la carga, y que la identidad hay que reconstruirla con lo que sí hay: el nombre
y el teléfono.

De aquí sale la regla. Se equivoca en dos direcciones y las dos duelen distinto:
juntar a dos personas distintas en una ficha mezcla los trámites de dos
familiares, y partir a una persona en dos deja su cartera repartida. Por eso la
regla nunca fusiona por teléfono sin mirar el nombre: 66 teléfonos están
compartidos por personas con apellidos distintos, que son familias, no
duplicados.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Tratamientos y ruido que no son parte del nombre
RUIDO = {'sr', 'sra', 'srta', 'dr', 'dra', 'don', 'dona', 'doña', 'ing', 'lic',
         'cliente', 'sin', 'nombre', 'na', 'n/a', 'x', 'xx', 'xxx', 'pendiente'}

# Partículas que no sirven para distinguir a dos personas
PARTICULAS = {'de', 'del', 'la', 'las', 'los', 'y', 'e', 'da', 'do', 'van', 'von'}

# Solo estos separadores parten una celda en dos personas. La « E » casi nunca
# es conjunción en español y « / » suele separar un alias, no a otra persona.
SEPARADORES = (' Y ', ' & ', ' + ')

INDICATIVOS = {
    '57': 'CO', '1': 'US', '34': 'ES', '52': 'MX', '51': 'PE', '56': 'CL',
    '54': 'AR', '58': 'VE', '507': 'PA', '593': 'EC', '971': 'AE', '44': 'GB',
    '39': 'IT', '33': 'FR', '49': 'DE', '55': 'BR', '86': 'CN', '61': 'AU',
}


def sin_tildes(texto: str) -> str:
    """La misma normalización que la columna generada `nombre_busqueda` de la
    base: `lower(sin_tildes(nombre))`. Tiene que coincidir o la búsqueda no
    encuentra lo que la migración cargó."""
    descompuesto = unicodedata.normalize('NFD', texto)
    return ''.join(c for c in descompuesto if unicodedata.category(c) != 'Mn')


def limpiar_anotaciones(nombre: str) -> tuple[str, str | None]:
    """Separa el nombre de lo que le escribieron al lado.

    Las hojas anotan el parentesco o el contexto dentro de la misma celda:
    «(ESPOSA DE …)», «(HIJO DE …)», «- adelanto». Eso no es parte del nombre y,
    si se deja, la misma persona escrita con y sin anotación queda como dos.
    La anotación no se tira: se guarda para la cronología, porque suele ser el
    único registro del parentesco.
    """
    anotaciones = re.findall(r'[\(\[]([^)\]]{2,60})[\)\]]', nombre)
    limpio = re.sub(r'[\(\[][^)\]]*[\)\]]', ' ', nombre)
    # Una anotación también puede ir después de un guion rodeado de espacios
    if ' - ' in limpio:
        izquierda, _, derecha = limpio.partition(' - ')
        if len(tokens_crudos(izquierda)) >= 2:
            anotaciones.append(derecha.strip())
            limpio = izquierda
    return ' '.join(limpio.split()), ' · '.join(a.strip() for a in anotaciones if a.strip()) or None


def tokens_crudos(nombre: str) -> list[str]:
    limpio = sin_tildes(nombre).lower()
    limpio = re.sub(r'[^a-z0-9ñ ]+', ' ', limpio)
    return [p for p in limpio.split() if p and p not in RUIDO and p not in PARTICULAS and len(p) > 1]


def tokens(nombre: str) -> list[str]:
    """Las palabras significativas del nombre, en minúscula, sin tildes y sin
    las anotaciones que le hayan escrito al lado."""
    nombre, _ = limpiar_anotaciones(nombre)
    limpio = sin_tildes(nombre).lower()
    limpio = re.sub(r'[^a-z0-9ñ ]+', ' ', limpio.replace('ñ', 'ñ'))
    palabras = [p for p in limpio.split() if p]
    return [p for p in palabras if p not in RUIDO and p not in PARTICULAS and len(p) > 1]


def clave_nombre(nombre: str) -> str:
    """La clave con la que se compara un nombre contra otro."""
    return ' '.join(tokens(nombre))


def es_nombre_de_persona(bruto: str | None) -> bool:
    """Descarta lo que ocupa la columna de cliente sin ser una persona: notas,
    números de teléfono sueltos, marcas de la hoja."""
    if not bruto:
        return False
    t = bruto.strip()
    if len(t) < 3:
        return False
    letras = sum(c.isalpha() for c in t)
    if letras < 3 or letras < len(t) / 2:
        return False
    return bool(tokens(t))


def partir_personas(bruto: str) -> list[str]:
    """Una celda puede traer dos personas: «Ana Gómez y Luis Gómez».

    Solo se parte cuando los dos lados quedan con nombre y apellido. «María y
    familia» o «Pedro y esposa» no se parten: el segundo lado no es un nombre.
    """
    texto = ' ' + bruto.strip() + ' '
    for sep in SEPARADORES:
        if sep in texto.upper():
            corte = texto.upper().index(sep)
            izq, der = texto[:corte].strip(), texto[corte + len(sep):].strip()
            if len(tokens(izq)) >= 2 and len(tokens(der)) >= 2:
                return [izq, der]
            break
    return [bruto.strip()]


def nombres_compatibles(a: str, b: str) -> bool:
    """¿Son la misma persona escrita de dos formas, o dos personas distintas?

    Compatible si: son iguales; uno está contenido en el otro (falta el segundo
    apellido); o difieren en un solo token por un carácter, que es un error de
    tipeo. Dos hermanos con el mismo apellido NO son compatibles: su nombre de
    pila es distinto y ninguno contiene al otro.
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    ca, cb = set(ta), set(tb)
    if ca <= cb or cb <= ca:
        # Contenido: «Ana Gómez» dentro de «Ana Gómez Ruiz». Pero exige que el
        # nombre de pila coincida, o «Gómez Ruiz» se tragaría a cualquier Gómez.
        return ta[0] == tb[0]
    if len(ta) == len(tb):
        distintos = [(x, y) for x, y in zip(ta, tb) if x != y]
        if len(distintos) == 1:
            x, y = distintos[0]
            return _distancia_uno(x, y)
    return False


def _distancia_uno(a: str, b: str) -> bool:
    """Difieren en un solo carácter: sustitución, inserción o borrado."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    corto, largo = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(largo)):
        if largo[:i] + largo[i + 1:] == corto:
            return True
    return False


# ------------------------------------------------------------------- teléfonos

@dataclass
class Telefono:
    e164: str | None
    pais: str | None
    problema: str | None = None

    def __bool__(self) -> bool:
        return self.e164 is not None


def normalizar_telefono(bruto: str | None, *, pais_por_defecto: str = '57') -> Telefono:
    """A formato internacional.

    Los números que parecen basura no siempre lo son: hay clientes que atienden
    desde Dubái, Madrid y Ciudad de México. La regla de «diez dígitos» los
    descarta a todos, así que aquí se normaliza por indicativo, no por largo.
    Si la celda trae varios números, se toma el primero y se anota.
    """
    if not bruto:
        return Telefono(None, None)
    t = str(bruto).strip()
    # Varios números en una celda: separados por / , ; o « - » con espacios
    partes = [p for p in re.split(r'[/,;]|\s-\s|\so\s', t) if any(c.isdigit() for c in p)]
    aviso = 'la celda traía más de un número; se tomó el primero' if len(partes) > 1 else None
    primero = partes[0] if partes else t

    tiene_mas = primero.strip().startswith('+')
    digitos = re.sub(r'\D', '', primero)
    if not digitos:
        return Telefono(None, None, problema=f'«{t[:25]}» no tiene dígitos')
    digitos = digitos.lstrip('0')

    if tiene_mas or len(digitos) > 10:
        for largo in (3, 2, 1):
            ind = digitos[:largo]
            if ind in INDICATIVOS and 7 <= len(digitos) - largo <= 12:
                return Telefono('+' + digitos, INDICATIVOS[ind], problema=aviso)
        if len(digitos) >= 11:
            return Telefono('+' + digitos, None,
                            problema=aviso or 'indicativo internacional no reconocido')
    if len(digitos) == 10:
        return Telefono('+' + pais_por_defecto + digitos, 'CO', problema=aviso)
    if len(digitos) == 7:
        return Telefono(None, None, problema=f'«{t[:25]}» parece un fijo sin indicativo de ciudad')
    return Telefono(None, None, problema=f'«{t[:25]}» no es un número de teléfono válido')


def correo_valido(bruto: str | None) -> str | None:
    if not bruto:
        return None
    t = bruto.strip().lower()
    return t if re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', t) else None
