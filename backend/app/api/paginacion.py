"""El techo de la paginación, en un solo sitio (RNF-08).

Diez rutas de este sistema devuelven listados por páginas, y nueve de ellas
declaraban `tamano: int = 50` sin máximo. Un valor por omisión no es un techo:
`?tamano=999999` desarma la paginación desde la barra de direcciones del
navegador. Medido el 10/10 sobre la base real, `/pagos?tamano=999999` devolvió
las 583 filas de una sola vez y `/alertas?tamano=999999` las 366. Hoy eso «no
pasa nada» porque hay quinientas filas; con cincuenta mil es la petición que
tumba el servidor, y el requisito de los tres segundos se cae con ella.

Por eso el límite vive acá y no repetido en cada ruta: un techo escrito nueve
veces son nueve oportunidades de que uno quede sin actualizar, y ya pasó —dos
rutas (`/auditoria` y `/rentabilidad/ventas`) sí lo tenían, cada una con su
propio `le=200` suelto.

`TAMANO_MAXIMO` es 200 porque es lo que ya pedía la pantalla más golosa (el
embudo cargaba 200 tarjetas de una) y porque 200 filas serializadas siguen
estando dos órdenes de magnitud por debajo del presupuesto de tres segundos.
Quien necesite más que esto no quiere una página: quiere la exportación, que es
otra ruta y tiene su propio tope.
"""
from typing import Annotated

from fastapi import Query

#: Máximo de filas que una sola petición puede pedir. Pedir más es un 422, no
#: una página gigante: es mejor que el cliente se entere a que el servidor lo
#: intente.
TAMANO_MAXIMO = 200

Pagina = Annotated[int, Query(ge=1, description='Número de página, desde 1.')]

Tamano = Annotated[int, Query(
    ge=1, le=TAMANO_MAXIMO,
    description=f'Filas por página, hasta {TAMANO_MAXIMO}. '
                'Para llevarse el listado completo está la exportación.')]
