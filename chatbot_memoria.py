"""Gestión de historial de conversación multi-turno para VLFisioterapia.

Permite mantener el contexto entre múltiples turnos de diálogo:
1. Recuerda información previa (ej. nombre del paciente, servicio o fecha).
2. Permite completar datos en varios pasos antes de confirmar la operación.
3. Permite reiniciar el contexto con 'REINICIAR' (o desde Gradio) sin borrar las reservas persistidas en SQLite (reservas.db).
"""

import json
import os
from datetime import date
from getpass import getpass
from urllib.error import HTTPError, URLError

from consulta_llm import (
    ACCIONES,
    CAMPOS,
    GROQ_URL,
    API_BASE,
    cargar_env,
    ejecutar,
    extraer_json,
    formatear_respuesta,
    normalizar_servicio,
    peticion_json,
)

INSTRUCCIONES = """
Eres el asistente virtual con memoria de VLFisioterapia (Centro de Fisioterapia y Rehabilitación).
Devuelve ÚNICAMENTE un objeto JSON con estas claves: accion, cliente, servicio, fecha, hora, codigo.
Acciones permitidas: servicios, disponibilidad, crear, modificar, cancelar, consultar, fuera_de_alcance.
Servicios disponibles: evaluacion, deportiva, traumatologica, puncion_seca, postural, neurologica.
Usa fecha en formato AAAA-MM-DD y hora en formato HH:MM (24 horas).

REGLA CLAVE DE MEMORIA:
Ten en cuenta TODOS los mensajes anteriores de la conversación para completar solicitudes por partes.
Por ejemplo:
- Si el usuario dijo su nombre o servicio en un turno previo y ahora indica la fecha o la hora, conserva y acumula los datos anteriores en el JSON.
- Si solo saluda, dice su nombre o hace una pregunta general sin pedir cita, mantén los datos que conozcas y usa accion "fuera_de_alcance" o "servicios".
- Si un dato no ha sido mencionado en ningún turno de la conversación, déjalo como cadena vacía "".
- No inventes datos ni afirmes que la cita ya fue agendada; solo devuelve la intención acumulada.
"""


def nuevo_historial():
    """Crea una nueva conversación que inicia con las instrucciones y la fecha actual."""
    hoy = date.today().isoformat()
    return [{"role": "system", "content": INSTRUCCIONES + f"\nFecha actual del sistema: {hoy}."}]


def interpretar_turno(pregunta, historial, clave, modelo):
    """Envía todo el historial acumulado más la pregunta actual a Groq."""
    mensajes = historial + [{"role": "user", "content": pregunta}]
    payload = {"model": modelo, "messages": mensajes, "stream": False}
    respuesta = peticion_json(
        GROQ_URL, "POST", payload, {"Authorization": f"Bearer {clave}"}
    )
    texto = respuesta["choices"][0]["message"]["content"]
    plan = extraer_json(texto)
    if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
        raise ValueError("Groq no devolvió una acción válida")

    plan = {campo: str(plan.get(campo) or "").strip() for campo in CAMPOS}
    if plan.get("servicio"):
        plan["servicio"] = normalizar_servicio(plan["servicio"])

    return plan, mensajes


def procesar_turno(pregunta, historial, clave, modelo):
    """Interpreta la intención acumulada, evalúa la ejecución en FastAPI y guarda la respuesta en el historial."""
    plan, mensajes = interpretar_turno(pregunta, historial, clave, modelo)
    resultado = ejecutar(plan)
    resumen = {
        "plan": plan,
        "respuesta": resultado.get("mensaje") or resultado.get("datos"),
    }
    actualizado = mensajes + [
        {"role": "assistant", "content": json.dumps(resumen, ensure_ascii=False)}
    ]
    return resultado, actualizado, plan


def main():
    cargar_env()
    clave = os.getenv("GROQ_API_KEY", "").strip() or getpass("API key de Groq: ").strip()
    modelo = os.getenv("GROQ_MODEL", "").strip() or input("ID del modelo de Groq: ").strip()
    if not clave or not modelo:
        print("Se requiere la API key y el ID del modelo.")
        return

    historial = nuevo_historial()
    print("=" * 65)
    print("VLFisioterapia · Chatbot con Memoria e Historial (Clase 07)")
    print(f"Conectado a FastAPI en: {API_BASE}")
    print("Comandos disponibles:")
    print(" • REINICIAR: Limpia el historial de chat (conserva las citas guardadas)")
    print(" • SALIR: Termina la sesión")
    print("=" * 65)

    while True:
        pregunta = input("\nTú: ").strip()
        if pregunta.casefold() == "salir":
            print("¡Hasta pronto!")
            break
        if pregunta.casefold() == "reiniciar":
            historial = nuevo_historial()
            print(">> Conversación reiniciada. Se limpió el historial de chat.")
            print(f">> Mensajes en el historial: {len(historial)} (solo system).")
            continue
        if not pregunta:
            continue

        try:
            resultado, actualizado, plan = procesar_turno(
                pregunta, historial, clave, modelo
            )
            historial = actualizado
            print("Chatbot:", formatear_respuesta(resultado))

            if resultado["tipo"] == "confirmacion":
                confirmacion = input("Confirmar (s/n): ").strip().casefold()
                if confirmacion == "s":
                    final = ejecutar(plan, confirmar=True)
                    historial[-1]["content"] = json.dumps(
                        {"plan": plan, "respuesta": final.get("datos") or final.get("mensaje")},
                        ensure_ascii=False,
                    )
                    print("FastAPI:", formatear_respuesta(final))
                else:
                    historial[-1]["content"] = json.dumps(
                        {"plan": plan, "respuesta": "Operación descartada por el paciente."},
                        ensure_ascii=False,
                    )
                    print("Operación cancelada. Puedes seguir conversando o indicar nuevos datos.")

            print(f"[Historial: {len(historial)} mensajes]")

        except HTTPError as error:
            try:
                detalle = error.read().decode("utf-8")
                detalle_json = json.loads(detalle)
                mensaje_error = detalle_json.get("detail", detalle)
            except Exception:
                mensaje_error = f"Código {error.code}"
            print(f"Error HTTP {error.code} de FastAPI/Groq: {mensaje_error}")
        except (URLError, TimeoutError):
            print(f"No pude conectar con Groq o con FastAPI en {API_BASE}. Revisa que ambos servicios estén activos.")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            print(f"No pude interpretar la respuesta ({exc}). Revisa el formato JSON devuelto.")


if __name__ == "__main__":
    main()
