"""Reconocer a la misma persona escrita de formas distintas en 17 hojas.

El problema medido: unas 1.800 menciones de persona repartidas entre los tres
libros, que corresponden a bastantes menos personas reales. Sin documento de
identidad en ninguna fuente, la única forma de saber que «Ana María Gómez» de
una hoja y «ana maria gomez r.» de otra son la misma es compararlas.

La regla tiene dos guardas, y las dos vienen de haber medido los datos:

1. El teléfono NO fusiona por sí solo. Decenas de teléfonos están compartidos
   por personas con apellidos distintos: son familias, y el celular es el de
   quien contrata. Fusionar por teléfono a secas convierte una familia de
   cuatro en una sola ficha.

2. El correo es el ancla más débil y va de último. Hay correos que aparecen en
   diez filas con nombres distintos: son buzones compartidos o cuentas de la
   propia agencia. Si un correo aparece en cinco o más filas, se descarta como
   ancla.

Lo que la regla no puede decidir sola no lo decide: queda marcado como conflicto
y va al reporte de excepciones, para que lo resuelva quien conoce a la gente.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.migracion.normalizacion import (clave_nombre, correo_valido, nombres_compatibles,
                                         normalizar_telefono, tokens)

CORREO_COMPARTIDO_DESDE = 5      # un correo en 5+ filas no identifica a nadie


@dataclass
class Mencion:
    """Cada vez que una persona aparece en una hoja."""
    nombre: str
    telefono: str | None = None
    correo: str | None = None
    origen: tuple[str, str, int] = ('', '', 0)

    @property
    def clave(self) -> str:
        return clave_nombre(self.nombre)


@dataclass
class Persona:
    """Una persona real, reconstruida a partir de sus menciones."""
    nombre: str                                   # la escritura más completa
    claves: set[str] = field(default_factory=set)
    telefonos: set[str] = field(default_factory=set)
    correos: set[str] = field(default_factory=set)
    menciones: list[Mencion] = field(default_factory=list)
    conflictos: list[str] = field(default_factory=list)

    def absorber(self, m: Mencion) -> None:
        self.menciones.append(m)
        self.claves.add(m.clave)
        if m.telefono:
            self.telefonos.add(m.telefono)
        if m.correo:
            self.correos.add(m.correo)
        # Se conserva la escritura más larga: suele traer el segundo apellido
        if len(tokens(m.nombre)) > len(tokens(self.nombre)):
            self.nombre = m.nombre

    @property
    def telefono(self) -> str | None:
        return sorted(self.telefonos)[0] if self.telefonos else None

    @property
    def correo(self) -> str | None:
        return sorted(self.correos)[0] if self.correos else None


class Resolvedor:
    """Acumula menciones y al final entrega las personas.

    Se resuelve al final y no sobre la marcha a propósito: una mención temprana
    con el nombre incompleto se une bien a otra tardía con el nombre completo
    solo si se miran todas juntas.
    """

    def __init__(self) -> None:
        self.menciones: list[Mencion] = []
        self.descartadas: list[tuple[Mencion, str]] = []

    def agregar(self, nombre: str, *, telefono: str | None = None, correo: str | None = None,
                origen: tuple[str, str, int] = ('', '', 0)) -> Mencion | None:
        tel = normalizar_telefono(telefono)
        m = Mencion(nombre=nombre.strip(), telefono=tel.e164,
                    correo=correo_valido(correo), origen=origen)
        if not m.clave:
            self.descartadas.append((m, 'el nombre no tiene ninguna palabra utilizable'))
            return None
        self.menciones.append(m)
        return m

    # ---------------------------------------------------------------- resolución

    def resolver(self) -> list[Persona]:
        personas: list[Persona] = []
        por_clave: dict[str, Persona] = {}

        # 1. Nombre idéntico. Es la unión segura y no necesita guarda.
        for m in self.menciones:
            p = por_clave.get(m.clave)
            if p is None:
                p = Persona(nombre=m.nombre)
                por_clave[m.clave] = p
                personas.append(p)
            p.absorber(m)

        # 2. El teléfono junta candidatos, pero solo se fusionan los que además
        #    tienen nombres compatibles. Lo demás es una familia.
        personas = self._fusionar_por(personas, lambda p: p.telefonos, 'teléfono')

        # 3. El correo, con la guarda de los buzones compartidos.
        compartidos = self._correos_compartidos()
        personas = self._fusionar_por(
            personas, lambda p: {c for c in p.correos if c not in compartidos}, 'correo')

        for p in personas:
            for clave in p.claves:
                por_clave[clave] = p
        self._por_clave = por_clave
        return personas

    def _correos_compartidos(self) -> set[str]:
        cuenta: dict[str, set[str]] = defaultdict(set)
        for m in self.menciones:
            if m.correo:
                cuenta[m.correo].add(m.clave)
        return {c for c, nombres in cuenta.items() if len(nombres) >= CORREO_COMPARTIDO_DESDE}

    def _fusionar_por(self, personas: list[Persona], sacar_anclas, etiqueta: str) -> list[Persona]:
        por_ancla: dict[str, list[Persona]] = defaultdict(list)
        for p in personas:
            for ancla in sacar_anclas(p):
                por_ancla[ancla].append(p)

        absorbidas: set[int] = set()
        for ancla, candidatas in por_ancla.items():
            if len(candidatas) < 2:
                continue
            vivas = [p for p in candidatas if id(p) not in absorbidas]
            for i, base in enumerate(vivas):
                if id(base) in absorbidas:
                    continue
                for otra in vivas[i + 1:]:
                    if id(otra) in absorbidas:
                        continue
                    if any(nombres_compatibles(a, b)
                           for a in _escrituras(base) for b in _escrituras(otra)):
                        for m in otra.menciones:
                            base.absorber(m)
                        base.conflictos.extend(otra.conflictos)
                        absorbidas.add(id(otra))
                    else:
                        # Mismo ancla y nombres que no se parecen: casi siempre
                        # una familia compartiendo el celular de quien contrata.
                        base.conflictos.append(
                            f'comparte {etiqueta} con «{otra.nombre}», que parece otra persona')
        return [p for p in personas if id(p) not in absorbidas]

    def buscar(self, nombre: str) -> Persona | None:
        return getattr(self, '_por_clave', {}).get(clave_nombre(nombre))


def _escrituras(p: Persona) -> list[str]:
    vistos, salida = set(), []
    for m in p.menciones:
        if m.clave not in vistos:
            vistos.add(m.clave)
            salida.append(m.nombre)
    return salida
