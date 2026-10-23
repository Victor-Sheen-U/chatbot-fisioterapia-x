"""Suite de pruebas unitarias y de integración para VLFisioterapia.
Ejecutable sin dependencias externas (usa TestClient en memoria y archivos temporales).
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
import main


def ejecutar_pruebas():
    print("Iniciando pruebas de VLFisioterapia...")
    with TemporaryDirectory() as carpeta_temporal:
        db_temp = Path(carpeta_temporal) / "reservas_test.db"
        agenda_temp = main.AgendaSQLite.desde_negocio(db_temp, main.CLINICA)

        original_agenda = main.agenda
        main.agenda = agenda_temp
        main.SESIONES.clear()

        try:
            with TestClient(main.app) as cliente:
                # 1. Catálogos e Información
                resp = cliente.get("/clinica")
                assert resp.status_code == 200
                assert resp.json()["nombre"] == "VLFisioterapia · Centro Integral de Fisioterapia y Rehabilitación"

                resp_servicios = cliente.get("/servicios")
                assert resp_servicios.status_code == 200
                assert "evaluacion" in resp_servicios.json()
                assert "deportiva" in resp_servicios.json()

                resp_fisios = cliente.get("/fisioterapeutas")
                assert resp_fisios.status_code == 200
                assert "mariana" in resp_fisios.json()

                resp_faq = cliente.get("/faq")
                assert resp_faq.status_code == 200
                assert len(resp_faq.json()["faq"]) > 0
                assert len(resp_faq.json()["seguros_convenios"]) > 0

                # 2. Disponibilidad
                # Buscar un día laborable futuro (lunes a viernes)
                fecha_futura = datetime.now(main.ZONA).date() + timedelta(days=2)
                while fecha_futura.weekday() in (5, 6):  # Evitar sábado/domingo para prueba estándar de semana
                    fecha_futura += timedelta(days=1)
                dia_str = fecha_futura.isoformat()

                disp = cliente.get("/disponibilidad", params={"fecha": dia_str, "servicio": "evaluacion"}).json()
                assert "08:00" in disp["horarios_disponibles"]

                # Domingo cerrado -> horarios vacíos
                domingo = fecha_futura + timedelta(days=(6 - fecha_futura.weekday()) % 7)
                disp_dom = cliente.get("/disponibilidad", params={"fecha": domingo.isoformat(), "servicio": "evaluacion"}).json()
                assert disp_dom["horarios_disponibles"] == []

                # Fecha pasada -> 422
                assert cliente.get("/disponibilidad", params={"fecha": "2020-01-01", "servicio": "evaluacion"}).status_code == 422

                # 3. Validaciones de creación de cita
                datos_cita = {
                    "cliente": "Carlos Ruiz",
                    "servicio": "evaluacion",
                    "fecha": dia_str,
                    "hora": "08:00",
                    "fisioterapeuta": "mariana",
                    "telefono": "+57 312 999 8877",
                    "motivo_consulta": "Dolor lumbar agudo al levantar peso",
                    "confirmado": True
                }

                # Sin confirmación -> 422
                assert cliente.post("/citas", json={**datos_cita, "confirmado": False}).status_code == 422
                # Hora inválida -> 422
                assert cliente.post("/citas", json={**datos_cita, "hora": "25:00"}).status_code == 422
                # Servicio inexistente -> 422
                assert cliente.post("/citas", json={**datos_cita, "servicio": "magia"}).status_code == 422
                # Fecha pasada -> 422
                assert cliente.post("/citas", json={**datos_cita, "fecha": "2019-05-10"}).status_code == 422

                # 4. Concurrencia de reserva: 2 solicitudes simultáneas para el mismo fisioterapeuta y hora
                with ThreadPoolExecutor(max_workers=2) as executor:
                    respuestas = list(executor.map(lambda _: cliente.post("/citas", json=datos_cita), range(2)))

                codigos_estado = sorted([r.status_code for r in respuestas])
                assert codigos_estado == [201, 409], f"Se esperaba [201, 409], obtenido {codigos_estado}"

                cita_exitosa = next(r.json() for r in respuestas if r.status_code == 201)
                cod_cita = cita_exitosa["codigo"]
                assert cod_cita.startswith("VF-")
                assert cita_exitosa["estado"] == "activa"

                # Persistencia en base de datos SQLite
                citas_disco = agenda_temp.listar()
                assert len(citas_disco) == 1

                # 5. Consulta de cita
                assert cliente.get(f"/citas/{cod_cita}").status_code == 200
                assert cliente.get("/citas/VF-INEXISTENTE").status_code == 404

                # Horario 08:00 ya no debe estar disponible para Mariana
                disp_mariana = cliente.get("/disponibilidad", params={
                    "fecha": dia_str, "servicio": "evaluacion", "fisioterapeuta": "mariana"
                }).json()["horarios_disponibles"]
                assert "08:00" not in disp_mariana

                # 5b. Pruebas de cruce por profesional y adyacencia exacta (Fase 7: puntos 3, 4, 5, 6)
                # Punto 3: Evaluacion (60 min) con mariana a las 10:00 -> aceptada
                r_m10 = cliente.post("/citas", json={
                    "cliente": "Paciente Mariana 10",
                    "servicio": "evaluacion",
                    "fecha": dia_str,
                    "hora": "10:00",
                    "fisioterapeuta": "mariana",
                    "confirmado": True
                })
                assert r_m10.status_code == 201
                cod_m10 = r_m10.json()["codigo"]

                # Intento a las 10:30 (deportiva, 45 min) con mariana -> 409 (cruce de intervalo)
                r_cruce = cliente.post("/citas", json={
                    "cliente": "Paciente Cruce",
                    "servicio": "deportiva",
                    "fecha": dia_str,
                    "hora": "10:30",
                    "fisioterapeuta": "mariana",
                    "confirmado": True
                })
                assert r_cruce.status_code == 409

                # Punto 4: Lo mismo a las 10:30 con valeria (o sin fisioterapeuta) -> aceptado (cruce es por profesional)
                r_valeria = cliente.post("/citas", json={
                    "cliente": "Paciente Valeria 1030",
                    "servicio": "deportiva",
                    "fecha": dia_str,
                    "hora": "10:30",
                    "fisioterapeuta": "valeria",
                    "confirmado": True
                })
                assert r_valeria.status_code == 201
                cod_valeria = r_valeria.json()["codigo"]

                # Punto 5: Adyacencia exacta: cita que empieza justo cuando termina la anterior (11:00 con mariana) -> aceptada
                r_adyacente = cliente.post("/citas", json={
                    "cliente": "Paciente Adyacente",
                    "servicio": "deportiva",
                    "fecha": dia_str,
                    "hora": "11:00",
                    "fisioterapeuta": "mariana",
                    "confirmado": True
                })
                assert r_adyacente.status_code == 201
                cod_adyacente = r_adyacente.json()["codigo"]

                # Punto 6: Reprogramar a horario ocupado -> 409 y conserva sus datos anteriores
                r_reprog_ocupado = cliente.patch(f"/citas/{cod_valeria}/reprogramar", json={
                    "nueva_fecha": dia_str,
                    "nueva_hora": "10:00",
                    "fisioterapeuta": "mariana",
                    "confirmado": True
                })
                assert r_reprog_ocupado.status_code == 409
                cita_val_check = cliente.get(f"/citas/{cod_valeria}").json()
                assert cita_val_check["hora"] == "10:30"
                assert cita_val_check["fisioterapeuta_asignado"] == "valeria"

                # Limpiar citas auxiliares para no interferir con las secciones siguientes
                cliente.delete(f"/citas/{cod_m10}", params={"confirmado": True})
                cliente.delete(f"/citas/{cod_valeria}", params={"confirmado": True})
                cliente.delete(f"/citas/{cod_adyacente}", params={"confirmado": True})

                # 6. Reprogramación de cita
                # Reprogramar a las 11:00
                reprog_payload = {
                    "nueva_fecha": dia_str,
                    "nueva_hora": "11:00",
                    "confirmado": True
                }
                res_reprog = cliente.patch(f"/citas/{cod_cita}/reprogramar", json=reprog_payload)
                assert res_reprog.status_code == 200
                cita_reprog = res_reprog.json()
                assert cita_reprog["hora"] == "11:00"
                assert len(cita_reprog["historial_reprogramaciones"]) == 1

                # Comprobar que el slot anterior (08:00) se liberó
                disp_mariana_post = cliente.get("/disponibilidad", params={
                    "fecha": dia_str, "servicio": "evaluacion", "fisioterapeuta": "mariana"
                }).json()["horarios_disponibles"]
                assert "08:00" in disp_mariana_post
                assert "11:00" not in disp_mariana_post

                # Intentar reprogramar a horario ocupado -> 409
                assert cliente.patch(f"/citas/{cod_cita}/reprogramar", json={
                    "nueva_fecha": dia_str,
                    "nueva_hora": "11:00",
                    "confirmado": True
                }).status_code == 409

                # 7. Cancelación de cita
                # Sin parámetro confirmado -> 422
                assert cliente.delete(f"/citas/{cod_cita}").status_code == 422
                res_canc = cliente.delete(f"/citas/{cod_cita}", params={"confirmado": True})
                assert res_canc.status_code == 200
                assert res_canc.json()["estado"] == "cancelada"

                # Slot 11:00 se liberó
                disp_liberado = cliente.get("/disponibilidad", params={
                    "fecha": dia_str, "servicio": "evaluacion", "fisioterapeuta": "mariana"
                }).json()["horarios_disponibles"]
                assert "11:00" in disp_liberado

                # Intentar reprogramar una cita cancelada -> 400
                assert cliente.patch(f"/citas/{cod_cita}/reprogramar", json=reprog_payload).status_code == 400

                # 8. Escalamiento / Atención Humana
                resp_esc = cliente.post("/escalar", json={
                    "paciente": "Elena Gómez",
                    "telefono": "+57 310 111 2233",
                    "motivo": "Sospecha de fractura con dolor severo incontrolable",
                    "session_id": "sesion-urgencia-1"
                })
                assert resp_esc.status_code == 200
                assert resp_esc.json()["estatus"] == "escalado_exitoso"
                assert "whatsapp" in resp_esc.json()["contacto_inmediato"]

                # 9. Flujo Conversacional /chat (Simulación puente Flowise)
                def enviar_chat(mensaje: str, extraccion: dict = None, sesion: str = "paciente-101"):
                    return cliente.post("/chat", json={
                        "session_id": sesion,
                        "mensaje": mensaje,
                        "datos": extraccion or {}
                    })

                # Saludo inicial
                r_inicio = enviar_chat("Hola, buenas tardes").json()
                assert "VLFisioterapia" in r_inicio["respuesta"]

                # Consulta informativa
                r_info = enviar_chat("¿Qué precio tiene la punción seca?", {"intencion": "informacion"}).json()
                assert "Punción Seca" in r_info["respuesta"]
                assert "COP" in r_info["respuesta"]

                # Proceso de reserva paso a paso
                # Paso 1: Pedir reserva con servicio
                r_res1 = enviar_chat("Quiero agendar una cita de fisioterapia deportiva", {
                    "intencion": "reservar",
                    "servicio": "deportiva"
                }).json()
                assert "AAAA-MM-DD" in r_res1["respuesta"]

                # Paso 2: Indicar fecha
                r_res2 = enviar_chat(f"Para el {dia_str}", {
                    "intencion": "continuar",
                    "fecha": dia_str
                }).json()
                assert "Horarios disponibles" in r_res2["respuesta"]

                # Paso 3: Indicar hora
                r_res3 = enviar_chat("A las 09:00", {
                    "intencion": "continuar",
                    "hora": "09:00"
                }).json()
                assert "¿A nombre de qué paciente" in r_res3["respuesta"]

                # Paso 4: Indicar nombre
                r_res4 = enviar_chat("Soy Andrés Morales", {
                    "intencion": "continuar",
                    "cliente": "Andrés Morales"
                }).json()
                assert "CONFIRMAR" in r_res4["respuesta"]
                assert "Andrés Morales" in r_res4["respuesta"]

                # Paso 5: Corrección de hora antes de confirmar
                r_corregir = enviar_chat("Mejor a las 10:00", {
                    "intencion": "continuar",
                    "hora": "10:00"
                }).json()
                assert "10:00" in r_corregir["respuesta"]
                assert "CONFIRMAR" in r_corregir["respuesta"]

                # Palabras como "Sí" o "Dale" NO autorizan; solo CONFIRMAR
                r_no_autoriza = enviar_chat("Sí, dale por favor", {}).json()
                assert "CONFIRMAR" in r_no_autoriza["respuesta"]

                # Confirmación oficial
                r_confirm = enviar_chat("CONFIRMAR").json()
                assert "¡Cita agendada con éxito!" in r_confirm["respuesta"]
                nuevo_cod = r_confirm["estado_sesion"]["ultimo_codigo"]
                assert nuevo_cod.startswith("VF-")

                # Reintentar confirmar sin nada pendiente -> rechazado
                r_doble_conf = enviar_chat("CONFIRMAR").json()
                assert "No tienes ningún resumen pendiente" in r_doble_conf["respuesta"]

                # Reprogramación vía chat
                r_chat_rep = enviar_chat(f"Quiero reprogramar mi cita {nuevo_cod}", {
                    "intencion": "reprogramar",
                    "codigo": nuevo_cod,
                    "fecha": dia_str,
                    "hora": "14:00"
                }).json()
                assert "CONFIRMAR" in r_chat_rep["respuesta"]

                r_chat_rep_ok = enviar_chat("CONFIRMAR").json()
                assert "Cita reprogramada con éxito" in r_chat_rep_ok["respuesta"]

                # Cancelación vía chat
                r_chat_canc = enviar_chat(f"Cancelar cita {nuevo_cod}", {
                    "intencion": "cancelar",
                    "codigo": nuevo_cod
                }).json()
                assert "Vas a cancelar la siguiente cita" in r_chat_canc["respuesta"]

                r_chat_canc_ok = enviar_chat("CONFIRMAR").json()
                assert "ha sido cancelada satisfactoriamente" in r_chat_canc_ok["respuesta"]

                # Escalamiento vía chat
                r_chat_esc = enviar_chat("Quiero hablar con una persona de recepción", {
                    "intencion": "escalar"
                }).json()
                assert "recepción médica" in r_chat_esc["respuesta"]
                assert "+57" in r_chat_esc["respuesta"]

                # Reset de sesión
                r_reset = enviar_chat("/reset").json()
                assert "reiniciada" in r_reset["respuesta"]

                # 10. Robustez de almacenamiento y tolerancia a fallos (fallo SQLite -> 503)
                datos_falla = {
                    "cliente": "Paciente Prueba",
                    "servicio": "evaluacion",
                    "fecha": dia_str,
                    "hora": "15:00",
                    "confirmado": True
                }
                total_antes = len(agenda_temp.listar())
                with patch.object(main.sqlite3, "connect", side_effect=main.sqlite3.OperationalError("Fallo simulado de SQLite")):
                    resp_falla = cliente.post("/citas", json=datos_falla)
                    assert resp_falla.status_code == 503
                assert len(agenda_temp.listar()) == total_antes

                print("Todas las pruebas pasaron satisfactoriamente (100% OK).")
        finally:
            main.agenda = original_agenda
            main.SESIONES.clear()


if __name__ == "__main__":
    ejecutar_pruebas()
