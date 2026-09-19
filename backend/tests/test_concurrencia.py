"""Pruebas de concurrencia. No usan el fixture db, que comparte una sola sesión:
abren sesiones reales que confirman, como lo harían solicitudes simultáneas.

La base de pruebas se recrea en cada corrida, así que no hace falta limpiar
(y la auditoría no se puede borrar: es inalterable)."""
import secrets
import threading

from sqlalchemy import func, select

from app.core.errores import Conflicto, ErrorDominio
from app.db.session import SesionLocal
from app.models.esquema import Auditoria, Usuarios
from app.services import auth as servicio_auth
from app.services import usuarios as servicio_usuarios


def _en_paralelo(n: int, tarea) -> list:
    barrera = threading.Barrier(n)
    resultados: list = [None] * n

    def correr(i):
        barrera.wait()
        with SesionLocal() as s:
            try:
                resultados[i] = tarea(s)
            except ErrorDominio as e:
                resultados[i] = e

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    return resultados


def test_intentos_simultaneos_no_se_pierden_y_bloquean():
    """Hallazgo de la revisión: con solicitudes en paralelo el contador perdía
    incrementos y el límite de 5 intentos se podía pasar unas 15 veces."""
    email = f'rafaga.{secrets.token_hex(3)}@visanow.co'
    with SesionLocal() as s:
        u, _ = servicio_usuarios.crear(s, None, nombre='Prueba ráfaga', email=email, rol='comercial')
        uid = u.id

    _en_paralelo(8, lambda s: servicio_auth.autenticar(s, email, 'errada-123', '10.0.0.1'))

    with SesionLocal() as s:
        u = s.get(Usuarios, uid)
        ops = dict(s.execute(select(Auditoria.operacion, func.count())
                             .where(Auditoria.entidad_id == uid, Auditoria.operacion != 'insert')
                             .group_by(Auditoria.operacion)).all())
    assert u.bloqueado_hasta is not None, f'8 intentos simultáneos no bloquearon la cuenta: {ops}'
    # Serializados: 4 fallos, el 5.º bloquea, los 3 restantes encuentran la cuenta bloqueada
    assert ops == {'login_fallido': 4, 'bloqueo': 1, 'login_bloqueado': 3}, ops


def test_alta_simultanea_del_mismo_correo_da_conflicto_no_error_500():
    email = f'doble.{secrets.token_hex(3)}@visanow.co'
    res = _en_paralelo(2, lambda s: servicio_usuarios.crear(
        s, None, nombre='Prueba doble', email=email, rol='comercial'))
    exitos = [r for r in res if isinstance(r, tuple)]
    conflictos = [r for r in res if isinstance(r, Conflicto)]
    assert len(exitos) == 1 and len(conflictos) == 1, res
