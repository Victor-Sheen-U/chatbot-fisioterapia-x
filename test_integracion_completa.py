"""Script de prueba de integración completa para VLFisioterapia.
Prueba:
1. Endpoints de main.py (nativos y de compatibilidad).
2. consulta_llm.py (interpretación real con Groq y ejecución en FastAPI).
3. chatbot_memoria.py (memoria multi-turno, acumulación de datos y comando REINICIAR).
"""

import json
import os
import sys
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

import main
import consulta_llm
import chatbot_memoria

def probar_todo():
    print("=" * 70)
    print("VERIFICACIÓN DE INTEGRACIÓN COMPLETA (CLASES 06 Y 07)")
    print("=" * 70)

    # 1. Probar endpoints de main.py con TestClient
    print("\n[1/3] Probando endpoints de main.py (nativos y compatibilidad)...")
    cliente = TestClient(main.app)

    # Verificación de saludo y catálogos
    r = cliente.get("/api/saludo")
    assert r.status_code == 200 and "mensaje" in r.json(), "Fallo /api/saludo"
    print("  ✓ GET /api/saludo OK")

    r = cliente.get("/api/servicios")
    assert r.status_code == 200 and "evaluacion" in r.json(), "Fallo /api/servicios"
    print("  ✓ GET /api/servicios OK")

    # Disponibilidad (calculando día laboral futuro)
    hoy = datetime.now(main.ZONA).date()
    fecha_prueba = hoy + timedelta(days=3)
    while fecha_prueba.weekday() in (5, 6): # evitar fin de semana
        fecha_prueba += timedelta(days=1)
    fecha_str = fecha_prueba.isoformat()

    r = cliente.get("/api/disponibilidad", params={"fecha": fecha_str, "servicio": "evaluacion"})
    assert r.status_code == 200, "Fallo /api/disponibilidad"
    data_disp = r.json()
    assert "horarios_disponibles" in data_disp and "horas" in data_disp, "Faltan claves de disponibilidad"
    hora_disponible = data_disp["horarios_disponibles"][0]
    print(f"  ✓ GET /api/disponibilidad OK (Turnos disponibles: {len(data_disp['horas'])})")

    # Crear reserva por ruta de compatibilidad /api/reservas
    payload_crear = {
        "cliente": "Paciente Prueba Integración",
        "servicio": "evaluacion",
        "fecha": fecha_str,
        "hora": hora_disponible,
        "confirmada": True
    }
    r = cliente.post("/api/reservas", json=payload_crear)
    assert r.status_code == 201, f"Fallo al crear reserva: {r.text}"
    cita_creada = r.json()
    cod_cita = cita_creada["codigo"]
    print(f"  ✓ POST /api/reservas OK (Cita creada: {cod_cita})")

    # Consultar reserva creada
    r = cliente.get(f"/api/reservas/{cod_cita}")
    assert r.status_code == 200 and r.json()["codigo"] == cod_cita, "Fallo /api/reservas/{codigo}"
    print(f"  ✓ GET /api/reservas/{cod_cita} OK")

    # Cancelar reserva
    r = cliente.delete(f"/api/reservas/{cod_cita}")
    assert r.status_code == 200 and r.json()["estado"] == "cancelada", "Fallo DELETE /api/reservas/{codigo}"
    print(f"  ✓ DELETE /api/reservas/{cod_cita} OK (Estado: cancelada)")

    # 2. Probar consulta_llm.py con Groq real
    print("\n[2/3] Probando consulta_llm.py con el modelo Groq real...")
    clave = os.getenv("GROQ_API_KEY", "")
    modelo = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    assert clave, "No se encontró GROQ_API_KEY en .env"

    pregunta = "¿Qué tratamientos ofrecen y cuánto cuestan?"
    print(f"  Pregunta: '{pregunta}'")
    plan = consulta_llm.interpretar(pregunta, clave, modelo)
    print(f"  Plan Groq: {plan}")
    assert plan["accion"] == "servicios", f"Se esperaba accion 'servicios', obtenido '{plan['accion']}'"

    with cliente:
        # Patching peticion_json para que use cliente de TestClient
        def testclient_peticion(url, metodo="GET", datos=None, headers=None):
            if "groq.com" in url:
                return original_peticion(url, metodo, datos, headers)
            # Parse path from url
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path
            if parsed.query:
                path += "?" + parsed.query
            if metodo == "GET":
                resp = cliente.get(path)
            elif metodo == "POST":
                resp = cliente.post(path, json=datos)
            elif metodo == "PATCH":
                resp = cliente.patch(path, json=datos)
            elif metodo == "DELETE":
                resp = cliente.delete(path)
            else:
                resp = cliente.request(metodo, path, json=datos)
            if resp.status_code >= 400:
                from urllib.error import HTTPError
                raise HTTPError(url, resp.status_code, resp.text, {}, None)
            return resp.json()

        original_peticion = consulta_llm.peticion_json
        consulta_llm.peticion_json = testclient_peticion
        chatbot_memoria.peticion_json = testclient_peticion

        try:
            res_ejecutar = consulta_llm.ejecutar(plan)
            assert res_ejecutar["tipo"] == "resultado" and "evaluacion" in res_ejecutar["datos"], "Fallo ejecutar() servicios"
            print("  ✓ consulta_llm.ejecutar(plan_servicios) OK")

            # 3. Probar chatbot_memoria.py (Memoria Multi-Turno y REINICIAR)
            print("\n[3/3] Probando chatbot_memoria.py (Memoria Multi-Turno y REINICIAR)...")
            historial = chatbot_memoria.nuevo_historial()
            assert len(historial) == 1 and historial[0]["role"] == "system", "El historial inicial debe tener solo system"
            print(f"  Historial inicial: {len(historial)} mensaje (solo system)")

            # Turno 1: Usuario da nombre y servicio pero no da la hora
            t1_pregunta = f"Hola, me llamo Mariana Gomez y deseo agendar una valoración para el {fecha_str}"
            print(f"  Turno 1: '{t1_pregunta}'")
            res1, hist1, plan1 = chatbot_memoria.procesar_turno(t1_pregunta, historial, clave, modelo)
            print(f"  Plan Turno 1: {plan1}")
            print(f"  Tipo resultado Turno 1: {res1['tipo']} -> {res1.get('mensaje')}")
            assert res1["tipo"] == "faltan_datos", f"Se esperaba 'faltan_datos', se obtuvo '{res1['tipo']}'"
            assert "hora" in res1["mensaje"].lower(), "Debe advertir que falta la hora"
            assert len(hist1) == 3, f"El historial debe tener 3 mensajes (system, user, assistant), tiene {len(hist1)}"

            # Turno 2: Usuario completa la hora que faltaba
            t2_pregunta = f"A las {hora_disponible}"
            print(f"  Turno 2: '{t2_pregunta}'")
            res2, hist2, plan2 = chatbot_memoria.procesar_turno(t2_pregunta, hist1, clave, modelo)
            print(f"  Plan Turno 2 (acumulado): {plan2}")
            print(f"  Tipo resultado Turno 2: {res2['tipo']} -> {res2.get('mensaje')}")

            # Verificar que el LLM recordó Mariana Gomez, evaluacion y fecha del turno anterior
            assert plan2["cliente"] != "", "El modelo no recordó el cliente del Turno 1"
            assert plan2["hora"] == hora_disponible, "El modelo no asignó la hora del Turno 2"
            assert res2["tipo"] == "confirmacion", f"Se esperaba confirmación, se obtuvo {res2['tipo']}"

            # Confirmar y ejecutar la cita
            print("  Confirmando la cita...")
            final = consulta_llm.ejecutar(plan2, confirmar=True)
            cod_final = final["datos"]["codigo"]
            print(f"  ✓ Cita agendada con éxito: {cod_final} para {final['datos']['cliente']}")

            # Probar REINICIAR
            print("  Probando comando REINICIAR...")
            hist_reiniciado = chatbot_memoria.nuevo_historial()
            assert len(hist_reiniciado) == 1, "REINICIAR debe dejar solo 1 mensaje"
            print(f"  ✓ Historial reiniciado. Mensajes: {len(hist_reiniciado)}")

            # Comprobar que la cita sigue en la base de datos a pesar de reiniciar el chat
            cita_en_bd = cliente.get(f"/citas/{cod_final}").json()
            assert cita_en_bd["codigo"] == cod_final, "La cita debe permanecer en reservas.db"
            print(f"  ✓ Comprobación persistencia: La cita {cod_final} sigue existiendo en reservas.db!")

            # Cancelar cita de prueba para dejar la base de datos limpia
            cliente.delete(f"/citas/{cod_final}?confirmado=true")
            print(f"  ✓ Cita de prueba {cod_final} cancelada para mantener limpia la agenda.")

        finally:
            consulta_llm.peticion_json = original_peticion
            chatbot_memoria.peticion_json = original_peticion

    print("\n" + "=" * 70)
    print("¡TODAS LAS PRUEBAS DE INTEGRACIÓN PASARON EXITOSAMENTE (100% OK)!")
    print("=" * 70)

if __name__ == "__main__":
    probar_todo()
