"""Script para preparar datos ficticios limpios en reservas.db para VLFisioterapia.

Sin argumentos: crea reservas.db si no existe y siembra 5 reservas ficticias en los
próximos días hábiles (calculados con la zona horaria America/Bogota) de forma idempotente.
Con --reiniciar: vacía la tabla reservas y vuelve a sembrar los 5 registros de demostración.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from almacen_sqlite import AgendaSQLite

BASE = Path(__file__).resolve().parent
RUTA_NEGOCIO = BASE / "clinica.json"
RUTA_DB = BASE / "reservas.db"


def siguientes_dias_habiles(fecha_base, cantidad=3):
    """Devuelve los próximos días hábiles de lunes a viernes a partir de mañana."""
    dias = []
    cursor = fecha_base + timedelta(days=1)
    while len(dias) < cantidad:
        if cursor.weekday() < 5:  # 0=Lunes ... 4=Viernes
            dias.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return dias


def preparar_datos(reiniciar=False):
    agenda = AgendaSQLite.desde_negocio(RUTA_DB, RUTA_NEGOCIO)
    zona = agenda.zona or ZoneInfo("America/Bogota")
    hoy = datetime.now(zona).date()
    d1, d2, d3 = siguientes_dias_habiles(hoy, 3)

    if reiniciar:
        with agenda.conexion(escritura=True) as con:
            con.execute("DELETE FROM reservas")
        print("Se vació la tabla 'reservas' en reservas.db (--reiniciar).")

    existentes = {fila["cliente"] for fila in agenda.listar()}

    semillas = [
        {
            "cliente": "Paciente Demo 1",
            "servicio": "evaluacion",
            "fecha": d1,
            "hora": "09:00",
            "fisioterapeuta": "mariana",
            "telefono": "+57 300 000 0001",
            "motivo_consulta": "Valoración funcional inicial de rodilla",
            "cancelar": False,
        },
        {
            "cliente": "Paciente Demo 2",
            "servicio": "postural",
            "fecha": d1,
            "hora": "09:00",
            "fisioterapeuta": "valeria",
            "telefono": "+57 300 000 0002",
            "motivo_consulta": "Reeducación postural global de columna",
            "cancelar": False,
        },
        {
            "cliente": "Paciente Demo 3",
            "servicio": "puncion_seca",
            "fecha": d1,
            "hora": "11:00",
            "fisioterapeuta": "carlos",
            "telefono": "+57 300 000 0003",
            "motivo_consulta": "Contractura cervical (cita cancelada de prueba)",
            "cancelar": True,
        },
        {
            "cliente": "Paciente Demo 4",
            "servicio": "deportiva",
            "fecha": d2,
            "hora": "10:00",
            "fisioterapeuta": "mariana",
            "telefono": "+57 300 000 0004",
            "motivo_consulta": "Readaptación deportiva de tobillo",
            "cancelar": False,
        },
        {
            "cliente": "Paciente Demo 5",
            "servicio": "neurologica",
            "fecha": d3,
            "hora": "14:00",
            "fisioterapeuta": "carlos",
            "telefono": "+57 300 000 0005",
            "motivo_consulta": "Sesión de rehabilitación neurológica",
            "cancelar": False,
        },
    ]

    creadas = 0
    omitidas = 0
    for item in semillas:
        if item["cliente"] in existentes:
            omitidas += 1
            continue
        creada = agenda.crear(
            cliente=item["cliente"],
            servicio=item["servicio"],
            fecha=item["fecha"],
            hora=item["hora"],
            fisioterapeuta=item["fisioterapeuta"],
            telefono=item["telefono"],
            motivo_consulta=item["motivo_consulta"],
        )
        if item["cancelar"]:
            agenda.cancelar(creada["codigo"])
        creadas += 1

    filas = agenda.listar()
    print(f"Base de datos lista en: {RUTA_DB}")
    print(f"Sembradas: {creadas} | Ya existentes (omitidas): {omitidas} | Total actual: {len(filas)}")
    for f in filas:
        print(
            f"  - {f['codigo']} | {f['cliente']} | {f['servicio']} ({f['duracion_minutos']} min) "
            f"| {f['fecha']} {f['hora']} | fisio={f['fisioterapeuta_asignado']} | estado={f['estado']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepara datos ficticios de prueba en reservas.db.")
    parser.add_argument(
        "--reiniciar",
        action="store_true",
        help="Borra todas las filas actuales de reservas y vuelve a sembrar las 5 reservas ficticias.",
    )
    args = parser.parse_args()
    preparar_datos(reiniciar=args.reiniciar)
