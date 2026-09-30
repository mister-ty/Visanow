"""La migración desde la línea de comandos.

    python -m app.migracion previsualizar    # lee todo, arma el plan, no escribe nada
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


COMANDOS = {'previsualizar': _previsualizar, 'hojas': _hojas}

if __name__ == '__main__':
    comando = sys.argv[1] if len(sys.argv) > 1 else ''
    if comando not in COMANDOS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMANDOS[comando]())
