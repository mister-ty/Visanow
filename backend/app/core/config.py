"""Configuración leída del .env (en local) o de las variables de entorno (en producción)."""
from functools import lru_cache
import pathlib

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = pathlib.Path(__file__).resolve().parents[3]


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / '.env', env_file_encoding='utf-8',
                                      extra='ignore')

    app_env: str = 'local'
    app_secret: str
    database_url: str
    cifrado_llave: str

    jwt_algoritmo: str = 'HS256'
    jwt_expira_minutos: int = 60
    cors_origins: str = 'http://localhost:5173'
    url_ui: str = 'http://localhost:5173'          # base de los enlaces que se envían por correo
    zona_horaria: str = 'America/Bogota'
    moneda_base: str = 'COP'

    # RNF-02: doble factor obligatorio para los perfiles que ven dinero y datos
    # sensibles. Se puede vaciar en local para agilizar pruebas manuales.
    mfa_roles_obligatorio: str = 'administradora,finanzas'

    # Bloqueo por contraseñas erradas
    login_max_intentos: int = 5
    login_bloqueo_minutos: int = 15

    @property
    def es_local(self) -> bool:
        return self.app_env == 'local'

    @property
    def roles_con_mfa(self) -> set[str]:
        return {r.strip() for r in self.mfa_roles_obligatorio.split(',') if r.strip()}

    @property
    def origenes_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(',') if o.strip()]

    @model_validator(mode='after')
    def _secretos_fuertes(self) -> 'Ajustes':
        for nombre in ('app_secret', 'cifrado_llave'):
            if len(getattr(self, nombre)) < 32:
                raise ValueError(f'{nombre.upper()} debe tener al menos 32 caracteres')
        return self


@lru_cache
def ajustes() -> Ajustes:
    return Ajustes()
