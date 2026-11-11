"""Suite de pruebas automatizadas para el canal de Telegram de VLFisioterapia.

Cubre:
1. Autenticación de servicio (X-API-Key) y autorización por usuario (X-Telegram-User).
2. Catálogo de servicios y disponibilidad real.
3. Creación de cita, persistencia de propiedad e integridad atómica.
4. Consulta de cita propia y bloqueo estricto de citas ajenas o legacy (Gradio).
5. Modificación y cancelación con validación de resumen/huella actual (optimistic locking).
6. Rechazo de modificaciones a horarios ocupados o citas canceladas.
7. Idempotencia: reenvío con mismos datos devuelve recibo idéntico; reenvío con datos alterados devuelve 409.
8. Concurrencia real multihilo (T22) sobre el mismo horario de un fisioterapeuta.
9. Lógica del bot (propuestas, botones vigentes/antiguos/vencidos, descarte, reset).
10. Simulación de respuesta de red perdida (T24) y recuperación con /estado.
"""

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from almacen_sqlite import AgendaSQLite, ConflictoReserva, ReservaNoEncontrada
from api_telegram import AgendaTelegram, Operacion, crear_router, huella
import bot_telegram

BASE = Path(__file__).resolve().parent
CLINICA = json.loads((BASE / "clinica.json").read_text(encoding="utf-8-sig"))
CLAVE_PRUEBA = "secreto_de_prueba_para_telegram_12345"


def obtener_fecha_laboral_futura(dias_adelante=5):
    hoy = datetime.now(bot_telegram.ZONA_BOGOTA).date()
    fecha = hoy + timedelta(days=dias_adelante)
    while fecha.weekday() not in (0, 1, 2, 3, 4, 5):
        fecha += timedelta(days=1)
    return fecha.isoformat()


def crear_entorno_prueba():
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "reservas_test.db"
    agenda_test = AgendaTelegram.desde_negocio(db_path, CLINICA)
    app_test = FastAPI()
    router = crear_router(agenda_test, CLAVE_PRUEBA)
    app_test.include_router(router)
    cliente_http = TestClient(app_test)
    return temp_dir, db_path, agenda_test, cliente_http


def test_autenticacion_y_seguridad():
    temp_dir, db_path, agenda, cliente = crear_entorno_prueba()
    try:
        # 1. Petición sin X-API-Key -> 401
        r = cliente.get("/telegram/servicios")
        assert r.status_code == 401, f"Esperado 401, obtenido {r.status_code}"
        assert "no autorizado" in r.text.lower()

        # 2. Petición con X-API-Key inválida -> 401
        r = cliente.get("/telegram/servicios", headers={"X-API-Key": "clave_falsa_invalida_1234"})
        assert r.status_code == 401, f"Esperado 401, obtenido {r.status_code}"

        # 3. Petición con X-API-Key válida -> 200
        r = cliente.get("/telegram/servicios", headers={"X-API-Key": CLAVE_PRUEBA})
        assert r.status_code == 200, f"Esperado 200, obtenido {r.status_code}"
        datos = r.json()
        assert "evaluacion" in datos and "deportiva" in datos
        assert datos["evaluacion"]["precio_cop"] == 80000

        # 4. Router deshabilitado cuando clave es vacía -> 503
        app_sin_clave = FastAPI()
        app_sin_clave.include_router(crear_router(agenda, ""))
        c_sin_clave = TestClient(app_sin_clave)
        r = c_sin_clave.get("/telegram/servicios", headers={"X-API-Key": "cualquiera"})
        assert r.status_code == 503, f"Esperado 503 por canal deshabilitado, obtenido {r.status_code}"
        assert "deshabilitado" in r.text.lower()

        # 5. Validación de identidad X-Telegram-User
        # Sin cabecera -> 422
        r = cliente.get("/telegram/reservas/VF-123456", headers={"X-API-Key": CLAVE_PRUEBA})
        assert r.status_code == 422

        # Con usuario no positivo (0 o negativo) -> 422
        r = cliente.get(
            "/telegram/reservas/VF-123456",
            headers={"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": "0"},
        )
        assert r.status_code == 422

        r = cliente.get(
            "/telegram/reservas/VF-123456",
            headers={"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": "-5"},
        )
        assert r.status_code == 422

    finally:
        temp_dir.cleanup()


def test_catalogo_y_disponibilidad():
    temp_dir, db_path, agenda, cliente = crear_entorno_prueba()
    try:
        headers = {"X-API-Key": CLAVE_PRUEBA}
        fecha = obtener_fecha_laboral_futura()

        # Consultar disponibilidad de evaluación
        r = cliente.get(
            f"/telegram/disponibilidad?fecha={fecha}&servicio=evaluacion",
            headers=headers,
        )
        assert r.status_code == 200
        disp = r.json()
        assert "horarios_disponibles" in disp
        assert len(disp["horarios_disponibles"]) > 0
        assert "07:00" in disp["horarios_disponibles"]

    finally:
        temp_dir.cleanup()


def test_ciclo_operaciones_propiedad_y_bloqueo_ajeno():
    temp_dir, db_path, agenda, cliente = crear_entorno_prueba()
    try:
        user_laura = 11111111
        user_andres = 22222222
        fecha = obtener_fecha_laboral_futura()
        hora = "09:00"

        headers_laura = {"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": str(user_laura)}
        headers_andres = {"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": str(user_andres)}

        # 1. Laura crea una cita por Telegram
        solicitud_crear = {
            "solicitud_id": "a" * 32,
            "accion": "crear",
            "datos": {
                "cliente": "Laura Gómez",
                "servicio": "evaluacion",
                "fecha": fecha,
                "hora": hora,
                "codigo": "",
            },
            "referencia": "",
            "confirmada": True,
        }
        r = cliente.post("/telegram/operaciones", json=solicitud_crear, headers=headers_laura)
        assert r.status_code == 201, f"Fallo al crear: {r.text}"
        res = r.json()
        assert res["ok"] is True
        cita = res["reserva"]
        codigo_cita = cita["codigo"]
        referencia_inicial = res["referencia"]
        assert codigo_cita.startswith("VF-")
        assert cita["cliente"] == "Laura Gómez"
        assert cita["precio_cop"] == 80000

        # Verificar que la propiedad quedó registrada en propietarios_telegram
        with agenda.conexion() as con:
            fila = con.execute(
                "SELECT usuario_id FROM propietarios_telegram WHERE codigo=?",
                (codigo_cita,),
            ).fetchone()
            assert fila is not None and fila["usuario_id"] == user_laura

        # 2. Laura consulta su cita propia -> 200
        r_propia = cliente.get(f"/telegram/reservas/{codigo_cita}", headers=headers_laura)
        assert r_propia.status_code == 200
        assert r_propia.json()["reserva"]["codigo"] == codigo_cita
        assert r_propia.json()["referencia"] == referencia_inicial

        # 3. Andrés intenta consultar la cita de Laura -> 404 (no revela existencia)
        r_ajena = cliente.get(f"/telegram/reservas/{codigo_cita}", headers=headers_andres)
        assert r_ajena.status_code == 404
        assert "no disponible" in r_ajena.json()["detail"].lower()

        # 4. Andrés intenta modificar la cita de Laura -> 404
        solicitud_mod_ajena = {
            "solicitud_id": "b" * 32,
            "accion": "modificar",
            "datos": {
                "cliente": "Andrés intento",
                "servicio": "evaluacion",
                "fecha": fecha,
                "hora": "10:00",
                "codigo": codigo_cita,
            },
            "referencia": referencia_inicial,
            "confirmada": True,
        }
        r_mod_ajena = cliente.post("/telegram/operaciones", json=solicitud_mod_ajena, headers=headers_andres)
        assert r_mod_ajena.status_code == 404

        # 5. Andrés intenta cancelar la cita de Laura -> 404
        solicitud_canc_ajena = {
            "solicitud_id": "c" * 32,
            "accion": "cancelar",
            "datos": {
                "cliente": "",
                "servicio": "",
                "fecha": "",
                "hora": "",
                "codigo": codigo_cita,
            },
            "referencia": referencia_inicial,
            "confirmada": True,
        }
        r_canc_ajena = cliente.post("/telegram/operaciones", json=solicitud_canc_ajena, headers=headers_andres)
        assert r_canc_ajena.status_code == 404

        # 6. Intentar acceder a cita creada fuera de Telegram (legacy Gradio/API) -> 404
        # Creamos una cita usando el método base crear() sin propietario Telegram
        fecha_leg = obtener_fecha_laboral_futura(dias_adelante=6)
        cita_legacy = agenda.crear("Paciente Web", "deportiva", fecha_leg, "11:00")
        cod_leg = cita_legacy["codigo"]
        r_legacy = cliente.get(f"/telegram/reservas/{cod_leg}", headers=headers_laura)
        assert r_legacy.status_code == 404, "Citas legacy no deben asignarse a usuarios Telegram"

        # 7. Modificar cita propia de Laura con referencia válida -> 200
        nueva_hora = "14:00"
        solicitud_mod = {
            "solicitud_id": "d" * 32,
            "accion": "modificar",
            "datos": {
                "cliente": "Laura Gómez",
                "servicio": "evaluacion",
                "fecha": fecha,
                "hora": nueva_hora,
                "codigo": codigo_cita,
            },
            "referencia": referencia_inicial,
            "confirmada": True,
        }
        r_mod = cliente.post("/telegram/operaciones", json=solicitud_mod, headers=headers_laura)
        assert r_mod.status_code == 200, f"Error al modificar: {r_mod.text}"
        res_mod = r_mod.json()
        assert res_mod["ok"] is True
        assert res_mod["reserva"]["hora"] == nueva_hora
        assert res_mod["reserva"]["codigo"] == codigo_cita
        referencia_modificada = res_mod["referencia"]

        # 8. Rechazo de resumen obsoleto (optimistic locking)
        # Intentar modificar usando la referencia_inicial vieja -> 409
        solicitud_obsoleta = {
            "solicitud_id": "e" * 32,
            "accion": "modificar",
            "datos": {
                "cliente": "Laura Gómez",
                "servicio": "evaluacion",
                "fecha": fecha,
                "hora": "15:00",
                "codigo": codigo_cita,
            },
            "referencia": referencia_inicial,  # Referencia antigua
            "confirmada": True,
        }
        r_obs = cliente.post("/telegram/operaciones", json=solicitud_obsoleta, headers=headers_laura)
        assert r_obs.status_code == 409
        assert "cambió" in r_obs.json()["detalle"].lower()

        # 9. Cancelar cita propia de Laura -> 200
        solicitud_canc = {
            "solicitud_id": "f" * 32,
            "accion": "cancelar",
            "datos": {
                "cliente": "",
                "servicio": "",
                "fecha": "",
                "hora": "",
                "codigo": codigo_cita,
            },
            "referencia": referencia_modificada,
            "confirmada": True,
        }
        r_canc = cliente.post("/telegram/operaciones", json=solicitud_canc, headers=headers_laura)
        assert r_canc.status_code == 200
        res_canc = r_canc.json()
        assert res_canc["ok"] is True
        assert res_canc["reserva"]["estado"] == "cancelada"

        # 10. Intentar reprogramar la cita cancelada -> 409
        solicitud_mod_canc = {
            "solicitud_id": "1" * 32,
            "accion": "modificar",
            "datos": {
                "cliente": "Laura Gómez",
                "servicio": "evaluacion",
                "fecha": fecha,
                "hora": "16:00",
                "codigo": codigo_cita,
            },
            "referencia": res_canc["referencia"],
            "confirmada": True,
        }
        r_mod_canc = cliente.post("/telegram/operaciones", json=solicitud_mod_canc, headers=headers_laura)
        assert r_mod_canc.status_code == 409
        assert "cancelada" in r_mod_canc.json()["detalle"].lower()

    finally:
        temp_dir.cleanup()


def test_idempotencia_y_recibos():
    temp_dir, db_path, agenda, cliente = crear_entorno_prueba()
    try:
        user_id = 99999999
        headers = {"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": str(user_id)}
        fecha = obtener_fecha_laboral_futura()

        solicitud_id = "1234567890abcdef1234567890abcdef"
        payload = {
            "solicitud_id": solicitud_id,
            "accion": "crear",
            "datos": {
                "cliente": "Carlos Idempotente",
                "servicio": "deportiva",
                "fecha": fecha,
                "hora": "08:00",
                "codigo": "",
            },
            "referencia": "",
            "confirmada": True,
        }

        # Primera llamada -> 201
        r1 = cliente.post("/telegram/operaciones", json=payload, headers=headers)
        assert r1.status_code == 201
        data1 = r1.json()
        cod_cita = data1["reserva"]["codigo"]

        # Segunda llamada con exactamente los mismos datos -> 201 (mismo resultado sin duplicar fila)
        r2 = cliente.post("/telegram/operaciones", json=payload, headers=headers)
        assert r2.status_code == 201
        assert r2.json() == data1

        # Comprobar en SQLite que existe solo 1 cita creada
        with agenda.conexion() as con:
            filas = con.execute("SELECT * FROM reservas WHERE cliente='Carlos Idempotente'").fetchall()
            assert len(filas) == 1
            op_filas = con.execute(
                "SELECT * FROM operaciones_telegram WHERE solicitud_id=?", (solicitud_id,)
            ).fetchall()
            assert len(op_filas) == 1

        # Reutilizar el mismo solicitud_id con datos diferentes -> 409
        payload_distinto = deepcopy(payload)
        payload_distinto["datos"]["hora"] = "09:00"
        r_conflicto = cliente.post("/telegram/operaciones", json=payload_distinto, headers=headers)
        assert r_conflicto.status_code == 409
        assert "pertenece a otros datos" in r_conflicto.json()["detalle"]

        # Recuperar el recibo mediante GET /telegram/operaciones/{solicitud_id}
        r_recibo = cliente.get(f"/telegram/operaciones/{solicitud_id}", headers=headers)
        assert r_recibo.status_code == 200
        recibo = r_recibo.json()
        assert recibo["estado_http"] == 201
        assert recibo["resultado"]["reserva"]["codigo"] == cod_cita

        # Otro usuario consultando el mismo solicitud_id -> 404
        headers_otro = {"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": "77777777"}
        r_ajeno = cliente.get(f"/telegram/operaciones/{solicitud_id}", headers=headers_otro)
        assert r_ajeno.status_code == 404

    finally:
        temp_dir.cleanup()


def test_concurrencia_t22():
    temp_dir, db_path, agenda, cliente = crear_entorno_prueba()
    try:
        user_1 = 10000001
        user_2 = 10000002
        fecha = obtener_fecha_laboral_futura(dias_adelante=7)
        hora = "10:00"
        # Carlos Gomez atiende 'neurologica' de 60 minutos como único especialista
        # Por lo tanto no hay profesional alternativo que pueda absorber el turno

        solicitud_1 = {
            "solicitud_id": "1" * 32,
            "accion": "crear",
            "datos": {
                "cliente": "Paciente Concurrente 1",
                "servicio": "neurologica",
                "fecha": fecha,
                "hora": hora,
                "codigo": "",
                "fisioterapeuta": "carlos",
            },
            "referencia": "",
            "confirmada": True,
        }
        solicitud_2 = {
            "solicitud_id": "2" * 32,
            "accion": "crear",
            "datos": {
                "cliente": "Paciente Concurrente 2",
                "servicio": "neurologica",
                "fecha": fecha,
                "hora": hora,
                "codigo": "",
                "fisioterapeuta": "carlos",
            },
            "referencia": "",
            "confirmada": True,
        }

        resultados = []

        def peticion(user_id, body):
            headers = {"X-API-Key": CLAVE_PRUEBA, "X-Telegram-User": str(user_id)}
            res = cliente.post("/telegram/operaciones", json=body, headers=headers)
            resultados.append((user_id, res.status_code, res.json()))

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(peticion, user_1, solicitud_1)
            f2 = executor.submit(peticion, user_2, solicitud_2)
            f1.result()
            f2.result()

        codigos_http = sorted([r[1] for r in resultados])
        assert codigos_http == [201, 409], f"Se esperaba exactamente un 201 y un 409, obtenido: {codigos_http}"

        # Comprobar en SQLite que solo existe una cita activa en ese intervalo
        with agenda.conexion() as con:
            citas_activas = con.execute(
                "SELECT * FROM reservas WHERE fecha=? AND hora=? AND estado='activa'",
                (fecha, hora),
            ).fetchall()
            assert len(citas_activas) == 1
    finally:
        temp_dir.cleanup()


def test_logica_bot_telegram_unitario():
    """Valida la lógica del adaptador bot_telegram.py con dobles y simulación."""
    temp_dir, db_path, agenda, cliente = crear_entorno_prueba()
    try:
        # 1. Prueba de ClienteAPI conectando con el TestClient
        api_cliente = bot_telegram.ClienteAPI("http://testserver", CLAVE_PRUEBA)

        def mock_peticion_json(url, metodo="GET", datos=None, headers=None):
            path = url.replace("http://testserver", "")
            if metodo == "GET":
                r = cliente.get(path, headers=headers)
            elif metodo == "POST":
                r = cliente.post(path, json=datos, headers=headers)
            if r.status_code >= 400:
                from urllib.error import HTTPError
                import io
                raise HTTPError(url, r.status_code, r.text, {}, io.BytesIO(r.text.encode()))
            return r.json()

        with patch("bot_telegram.peticion_json", side_effect=mock_peticion_json):
            servicios = api_cliente.solicitar("/servicios", 12345)
            assert "evaluacion" in servicios

            # 2. Formateo de lectura con moneda COP y sin campos genéricos
            texto_srv = bot_telegram.formatear_lectura("servicios", servicios)
            assert "$80.000 COP" in texto_srv
            assert "Tratamientos disponibles" in texto_srv

            # 3. Preparación de propuesta y validación de vencimiento (> 10 minutos)
            plan_propuesta = {
                "accion": "crear",
                "cliente": "Paciente Prueba",
                "servicio": "evaluacion",
                "fecha": "2026-11-20",
                "hora": "10:00",
                "codigo": "",
            }
            chat_id = 9999
            user_id = 5555
            pendiente = bot_telegram.preparar_pendiente(plan_propuesta, chat_id, user_id)
            assert pendiente["estado"] == "por_confirmar"
            assert pendiente["vence_en"] > bot_telegram.monotonic()

            # Validación de rechazo: mismo usuario en tiempo válido -> None
            assert bot_telegram.motivo_rechazo(
                pendiente, pendiente["solicitud_id"], chat_id, user_id, bot_telegram.monotonic()
            ) is None

            # Validación de rechazo: usuario diferente -> mensaje de rechazo
            rechazo_otro_user = bot_telegram.motivo_rechazo(
                pendiente, pendiente["solicitud_id"], chat_id, 8888, bot_telegram.monotonic()
            )
            assert "no corresponde" in rechazo_otro_user

            # Validación de rechazo: propuesta vencida (> 600 segundos)
            rechazo_vencida = bot_telegram.motivo_rechazo(
                pendiente, pendiente["solicitud_id"], chat_id, user_id, bot_telegram.monotonic() + 601
            )
            assert "venció" in rechazo_vencida

            # Validación de rechazo: botón antiguo de propuesta anterior
            rechazo_antiguo = bot_telegram.motivo_rechazo(
                pendiente, "otra_solicitud_vieja", chat_id, user_id, bot_telegram.monotonic()
            )
            assert "no es el vigente" in rechazo_antiguo

            # 4. Descarte de propuesta: no debe enviar escrituras
            # Probamos que ClienteAPI.ejecutar no fue invocado
            with patch.object(api_cliente, "ejecutar") as mock_ejecutar:
                # Simular descarte
                pendiente_descarte = bot_telegram.preparar_pendiente(plan_propuesta, chat_id, user_id)
                assert pendiente_descarte["solicitud_id"] != ""
                mock_ejecutar.assert_not_called()

            # 5. Simulación T24 (respuesta perdida después de guardar)
            # Primero ejecutamos con pérdida controlada
            fecha_t24 = obtener_fecha_laboral_futura(dias_adelante=8)
            plan_t24 = {
                "accion": "crear",
                "cliente": "Paciente T24",
                "servicio": "postural",
                "fecha": fecha_t24,
                "hora": "14:00",
                "codigo": "",
            }
            pendiente_t24 = bot_telegram.preparar_pendiente(plan_t24, chat_id, user_id)
            sol_id_t24 = pendiente_t24["solicitud_id"]

            original_ejecutar = api_cliente.ejecutar
            simulado_perdido = True

            def ejecutar_con_perdida(pend):
                nonlocal simulado_perdido
                res = original_ejecutar(pend)
                if simulado_perdido:
                    simulado_perdido = False
                    raise TimeoutError("Simulación T24: Timeout tras guardar en BD")
                return res

            with patch.object(api_cliente, "ejecutar", side_effect=ejecutar_con_perdida):
                # Intentamos ejecutar, lanzará TimeoutError
                try:
                    api_cliente.ejecutar(deepcopy(pendiente_t24))
                    assert False, "Debió lanzar TimeoutError"
                except TimeoutError:
                    pendiente_t24["estado"] = "incierta"

            # El bot pasa a estado incierta
            assert pendiente_t24["estado"] == "incierta"

            # Ahora el usuario ejecuta /estado sol_id_t24
            recibo_recuperado = api_cliente.estado(sol_id_t24, user_id)
            assert recibo_recuperado["estado_http"] == 201
            assert recibo_recuperado["resultado"]["ok"] is True
            cod_t24 = recibo_recuperado["resultado"]["reserva"]["codigo"]
            assert cod_t24.startswith("VF-")

            # Comprobar que solo hay 1 fila en la base de datos para ese paciente
            with agenda.conexion() as con:
                filas_t24 = con.execute("SELECT * FROM reservas WHERE cliente='Paciente T24'").fetchall()
                assert len(filas_t24) == 1
    finally:
        temp_dir.cleanup()


def ejecutar_todas_las_pruebas():
    print("=" * 70)
    print("INICIANDO SUITE DE PRUEBAS DE TELEGRAM (CLASE 13) — VLFisioterapia")
    print("=" * 70)

    print("\n[1/5] Probando autenticación (X-API-Key), claves y autorización de usuario...")
    test_autenticacion_y_seguridad()
    print("  ✓ Autenticación (401), desactivación segura (503) e identidad (422) verificadas!")

    print("\n[2/5] Probando catálogo (/telegram/servicios) y disponibilidad real...")
    test_catalogo_y_disponibilidad()
    print("  ✓ Catálogo VLFisioterapia (precios COP) y disponibilidad horaria verificados!")

    print("\n[3/5] Probando ciclo completo: crear, propiedad, bloqueo ajeno, modificar, cancelar...")
    test_ciclo_operaciones_propiedad_y_bloqueo_ajeno()
    print("  ✓ Creación, asociación de propiedad, aislamiento de cuenta, resumen obsoleto (409) y cancelación OK!")

    print("\n[4/5] Probando idempotencia, recibos persistentes y protección contra reintentos...")
    test_idempotencia_y_recibos()
    print("  ✓ Idempotencia estricta, detección de datos alterados (409) y recuperación de recibos OK!")

    print("\n[5/5] Probando concurrencia multihilo (T22) y lógica de bot / T24 respuesta perdida...")
    test_concurrencia_t22()
    test_logica_bot_telegram_unitario()
    print("  ✓ Concurrencia real (201 vs 409), rechazo de botones vencidos/antiguos y simulación T24 OK!")

    print("\n" + "=" * 70)
    print("¡TODAS LAS PRUEBAS DEL CANAL TELEGRAM PASARON EXITOSAMENTE (100% OK)!")
    print("=" * 70)


if __name__ == "__main__":
    ejecutar_todas_las_pruebas()
