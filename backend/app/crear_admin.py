"""Crea la primera administradora. Sin ella nadie puede entrar a crear usuarios.

    python -m app.crear_admin --nombre "Nombre Apellido" --email correo@dominio.com

Imprime una contraseña temporal una sola vez. Al primer ingreso el sistema
obliga a cambiarla y a activar el doble factor.
"""
import argparse
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select

from app.db.session import SesionLocal
from app.models.esquema import Roles, Usuarios
from app.services import usuarios


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--nombre', required=True)
    p.add_argument('--email', required=True)
    p.add_argument('--forzar', action='store_true',
                   help='Crearla aunque ya exista otra administradora activa')
    args = p.parse_args()

    # La misma validación que aplica la API al ingresar: si no, se podría crear
    # una administradora con un correo que después el login rechaza.
    try:
        email = validate_email(args.email.strip(), check_deliverability=False).normalized
    except EmailNotValidError as e:
        sys.exit(f'Correo inválido: {e}')

    with SesionLocal() as db:
        existentes = db.scalar(select(func.count()).select_from(Usuarios).join(Roles)
                               .where(Roles.codigo == 'administradora', Usuarios.activo.is_(True)))
        if existentes and not args.forzar:
            sys.exit(f'Ya hay {existentes} administradora(s) activa(s). Cree las demás cuentas desde '
                     'la aplicación, o use --forzar si perdió el acceso.')
        u, temporal = usuarios.crear(db, None, nombre=args.nombre, email=email,
                                     rol='administradora')

    print(f'\nAdministradora creada: {u.nombre} <{u.email}>')
    print(f'Contraseña temporal:   {temporal}')
    print('\nSe muestra una sola vez. Al primer ingreso habrá que cambiarla y activar el doble factor.')


if __name__ == '__main__':
    main()
