"""Configuración leída del .env (en local) o de las variables de entorno (en producción)."""
import pathlib
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = pathlib.Path(__file__).resolve().parents[3]


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / '.env', env_file_encoding='utf-8',
                                      extra='ignore')

    # Falla cerrado: si nadie define APP_ENV se asume producción (sin /docs,
    # sin enlaces de recuperación en el log). El .env de desarrollo dice 'local'.
    app_env: str = 'produccion'
    app_secret: str
    database_url: str
    cifrado_llave: str

    jwt_algoritmo: str = 'HS256'
    jwt_expira_minutos: int = 60
    cors_origins: str = 'http://localhost:5180'
    url_ui: str = 'http://localhost:5180'          # base de los enlaces que se envían por correo
    zona_horaria: str = 'America/Bogota'
    moneda_base: str = 'COP'

    # RNF-02: doble factor obligatorio para los perfiles que ven dinero y datos
    # sensibles. Se puede vaciar en local para agilizar pruebas manuales.
    mfa_roles_obligatorio: str = 'administradora,finanzas'

    # Dónde se guardan los documentos que se suben (RNF-04). Vacío = no se
    # guardan archivos, y subir uno se rechaza con el motivo.
    #
    # Es a propósito que haya que declararla. Render en el plan gratuito tiene
    # disco efímero: lo que se escriba ahí desaparece en el siguiente
    # despliegue, y subir el pasaporte de alguien a un disco así es perderlo sin
    # que nadie se entere hasta que haga falta. Donde hay volumen de verdad se
    # declara y funciona; donde no, los documentos por enlace siguen sirviendo.
    almacenamiento_ruta: str = ''

    # Correo (RNF-02). Sin host ni remitente no se envía nada, y se dice en el
    # log en vez de fingir que se envió. SMTP y no un servicio con su propia
    # llave: VisaNow ya tiene correo, lo habla cualquier proveedor, y no agrega
    # una dependencia ni un secreto más que rotar.
    smtp_host: str = ''
    smtp_puerto: int = 587
    smtp_usuario: str = ''
    smtp_password: str = ''
    smtp_desde: str = ''
    smtp_tls: bool = True          # STARTTLS en el 587, que es lo habitual
    smtp_ssl: bool = False         # SSL directo, para el 465
    smtp_timeout: int = 15         # sin esto, un proveedor caído cuelga la petición

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

    @field_validator('database_url', 'app_secret', 'cifrado_llave', 'cors_origins',
                     'url_ui', mode='before')
    @classmethod
    def _sin_espacios_de_sobra(cls, v):
        """Quita los espacios y saltos de línea que trae un valor pegado a mano.

        El primer despliegue en Render murió por esto: el `DATABASE_URL` quedó
        con un salto de línea al final y Postgres contestó

            FATAL: database "postgres
            " does not exist

        —la comilla de cierre en el renglón siguiente es todo el síntoma—. Pegar
        una cadena en un formulario web y que se cuele el retorno es lo más
        normal del mundo; que eso tumbe el despliegue con un error que no se
        puede leer, no. El valor con espacios de sobra nunca es el que se quiso
        poner, así que recortarlo no esconde ningún error de verdad.
        """
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode='after')
    def _secretos_fuertes(self) -> 'Ajustes':
        for nombre in ('app_secret', 'cifrado_llave'):
            if len(getattr(self, nombre)) < 32:
                raise ValueError(f'{nombre.upper()} debe tener al menos 32 caracteres')
        return self

    @property
    def configuracion_de_desarrollo_en_produccion(self) -> list[str]:
        """Las variables que quedaron con el valor del portátil en producción.

        Avisa, no revienta, y la diferencia importa: cuando escribí esto,
        `CORS_ORIGINS` en Render estaba sin llenar —va declarada con
        `sync: false`— así que un validador que reventara habría impedido
        arrancar a la API y habría tumbado una producción que hoy funciona. Un
        arreglo que apaga el sistema para avisar de un problema que todavía no
        muerde no es un arreglo.

        Lo que sí hace falta es que no se descubra el 16 por la mañana. Esto se
        ve en el log al arrancar y en `/salud`, que es un curl y se puede mirar
        desde el teléfono.

        `cors_origins` y `url_ui` tienen por omisión `http://localhost:5180`, que
        es el valor del portátil, y en Render las dos van declaradas con
        `sync: false`, o sea en blanco hasta que alguien las llene. Si se queda
        así, el único origen que la API acepta es el portátil: cuando la pantalla
        salga a Vercel no va a poder ni ingresar.

        Y lo peor es cómo falla. CORS no da error en el servidor ni deja rastro
        en el log: el navegador bloquea la respuesta y la pantalla se queda en
        blanco o diciendo que no hay conexión. Buscarlo desde ahí son horas, y
        serían las horas del día de la entrega.

        `url_ui` falla todavía más calladito: es la base del enlace de «olvidé mi
        contraseña», así que el correo saldría con un enlace a localhost y quien
        lo reciba no tendría forma de saber por qué no funciona.

        Es la misma familia del `fetch` con dirección relativa: cosas que andan
        en desarrollo porque algo local las tapa.
        """
        if self.es_local:
            return []
        return sorted(nombre.upper() for nombre in ('cors_origins', 'url_ui')
                      if 'localhost' in getattr(self, nombre)
                      or '127.0.0.1' in getattr(self, nombre))


@lru_cache
def ajustes() -> Ajustes:
    return Ajustes()
