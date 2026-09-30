"""La migración desde la línea de comandos.

    python -m app.migracion previsualizar    # lee todo, arma el plan, no escribe nada
    python -m app.migracion aplicar          # escribe, en una sola transacción
    python -m app.migracion limpiar          # borra SOLO lo migrado, para volver a empezar
    python -m app.migracion hojas            # qué hoja se migra y cuál no, y por qué

La previsualización es la actividad 6.1: se corre, se revisa el Excel que sale y
se conversa con VisaNow. Aplicar es la 6.2 y es un comando aparte a propósito,
para que nadie cargue datos reales sin haber mirado antes lo que iba a cargar.
"""
import sys
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


def _previsualizar() -> int:
    from app.db.session import SesionLocal
    from app.migracion import reporte
    from app.migracion.motor import previsualizar

    with SesionLocal() as db:
        plan, corrida = previsualizar(db)
        ruta = reporte.escribir(plan, corrida_id=corrida.id)

    def linea(etiqueta: str, valor) -> None:
        texto = f'{valor:,.0f}' if isinstance(valor, (int, float)) else str(valor)
        print(f'  {etiqueta:.<34} {texto:>16}')

    print(f'\nPrevisualizacion #{corrida.id} — no se escribio ningun dato de negocio\n')
    linea('filas leidas', plan.filas_leidas)
    linea('clientes', plan.clientes)
    linea('personas que viajan', plan.solicitantes)
    linea('tramites', plan.casos)
    linea('citas', plan.citas)
    linea('ventas', plan.negocios)
    linea('pagos', plan.pagos)
    print()
    linea('valor vendido', plan.valor_vendido)
    linea('valor cobrado', plan.valor_cobrado)
    linea('CARTERA', plan.cartera)
    print()
    linea('excepciones', len(plan.excepciones))
    for motivo, cuantas in plan.motivos.most_common(8):
        print(f'      {cuantas:>5}  {motivo[:62]}')
    print(f'\n  Reporte: {ruta}')
    return 0


def _hojas() -> int:
    from app.migracion.fuentes import CATALOGO, EXCLUIDAS
    print('\nSE MIGRAN:')
    for h in CATALOGO:
        print(f'  {h.archivo.split(".")[0][:18]:20} {h.nombre[:22]:24} [{h.trae}]')
        print(f'      {h.por_que}')
    print('\nNO SE MIGRAN:')
    for (archivo, hoja), razon in EXCLUIDAS.items():
        print(f'  {archivo.split(".")[0][:18]:20} {hoja[:22]:24}')
        print(f'      {razon}')
    return 0


def _aplicar() -> int:
    from app.db.session import SesionLocal
    from app.migracion.carga import aplicar

    incluir = '--incluir-ventas-sin-cobro' in sys.argv
    with SesionLocal() as db:
        r = aplicar(db, incluir_ventas_sin_cobro=incluir)
    print()
    print(f'Carga #{r.corrida_id}' + (' (incluyendo ventas sin cobro)' if incluir else ''))
    for etiqueta in ('clientes', 'solicitantes', 'casos', 'citas', 'negocios', 'pagos'):
        print(f'  {etiqueta:.<30} {getattr(r, etiqueta):>8,}')
    print(f'  {"filas ya cargadas, omitidas":.<30} {r.omitidas:>8,}')
    print(f'  {"excepciones":.<30} {len(r.excepciones):>8,}')
    return 0


def _limpiar() -> int:
    """Borra lo migrado y nada más.

    Solo toca registros con `origen_archivo`, que es lo que la migración creó:
    lo que el equipo haya cargado a mano desde la aplicación no tiene ese campo
    y no se toca. Sirve para repetir la carga mientras se depura con VisaNow.
    """
    from sqlalchemy import text

    from app.db.session import SesionLocal

    # En orden inverso a las dependencias
    TABLAS = ('pagos', 'citas', 'casos', 'negocios', 'solicitantes', 'clientes')
    with SesionLocal() as db:
        db.execute(text('delete from migracion_filas'))
        db.execute(text('delete from migracion_corridas'))
        borrados = {}
        for tabla in TABLAS:
            r = db.execute(text(f'delete from {tabla} where origen_archivo is not null'))
            borrados[tabla] = r.rowcount
        db.commit()
    print()
    print('Borrado lo migrado (lo cargado a mano desde la aplicacion no se toca):')
    for tabla, n in borrados.items():
        print(f'  {tabla:.<30} {n:>8,}')
    return 0


def _verificar() -> int:
    """Corre las comprobaciones contra la base que esté configurada.

    Devuelve 1 si alguna falla, para poder encadenarlo:
        python -m app.migracion aplicar && python -m app.migracion verificar
    """
    from app.db.session import SesionLocal
    from app.migracion import verificacion

    with SesionLocal() as db:
        resultados = verificacion.correr(db)
    fallaron = [c for c in resultados if not c.paso]
    print()
    for c in resultados:
        print(f'  [{"ok " if c.paso else "MAL"}] {c.que}')
        print(f'         {c.detalle}')
    print()
    print(f'  {len(resultados) - len(fallaron)} de {len(resultados)} comprobaciones pasaron')
    return 1 if fallaron else 0


COMANDOS = {'previsualizar': _previsualizar, 'aplicar': _aplicar, 'limpiar': _limpiar,
            'verificar': _verificar, 'hojas': _hojas}

if __name__ == '__main__':
    comando = sys.argv[1] if len(sys.argv) > 1 else ''
    if comando not in COMANDOS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMANDOS[comando]())
