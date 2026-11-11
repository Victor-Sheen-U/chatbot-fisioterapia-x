"""Lógica del chatbot: Groq interpreta y la FastAPI ejecuta.

En esta clase se usa desde la terminal. Más adelante Gradio podrá llamar
interpretar() y ejecutar() sin cambiar la lógica del negocio.
Adapta API_BASE y RUTAS a la FastAPI de tu equipo.
"""

import json
import os
from getpass import getpass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_BASE = os.getenv("CHATBOT_API_URL", "http://127.0.0.1:8027").rstrip("/")
RUTAS = {
    "servicios": "/api/servicios",
    "disponibilidad": "/api/disponibilidad",
    "reservas": "/api/reservas",
}
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ACCIONES = {"servicios", "disponibilidad", "crear", "modificar", "cancelar", "fuera_de_alcance"}
REQUERIDOS = {
    "disponibilidad": ("servicio", "fecha"),
    "crear": ("cliente", "servicio", "fecha", "hora"),
    "modificar": ("codigo", "servicio", "fecha", "hora"),
    "cancelar": ("codigo",),
}
INSTRUCCIONES = """
Identifica qué quiere hacer la persona con el negocio. Devuelve únicamente
un objeto JSON con estas claves: accion, cliente, servicio, fecha, hora, codigo.
Las acciones posibles son: servicios, disponibilidad, crear, modificar,
cancelar, fuera_de_alcance. Usa fecha AAAA-MM-DD y hora HH:MM.
Si un dato no aparece en la pregunta, usa una cadena vacía; no lo inventes.
No digas que hiciste una reserva: solo identifica la intención.
"""


def peticion_json(url, metodo="GET", datos=None, headers=None):
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8") if datos is not None else None
    encabezados = {"Content-Type": "application/json"} if cuerpo is not None else {}
    encabezados.update(headers or {})
    solicitud = Request(url, data=cuerpo, headers=encabezados, method=metodo)
    with urlopen(solicitud, timeout=30) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def interpretar(pregunta, clave, modelo):
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": pregunta},
        ],
        "stream": False,
    }
    respuesta = peticion_json(
        GROQ_URL, "POST", payload,
        {"Authorization": f"Bearer {clave}"},
    )
    texto = respuesta["choices"][0]["message"]["content"]
    plan = json.loads(texto)
    if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
        raise ValueError("Groq no devolvió una acción válida")
    return {campo: str(plan.get(campo) or "").strip()
            for campo in ("accion", "cliente", "servicio", "fecha", "hora", "codigo")}


def ejecutar(plan, confirmar=False, api_base=API_BASE):
    accion = plan["accion"]
    if accion not in ACCIONES:
        raise ValueError("Acción no permitida")
    if accion == "fuera_de_alcance":
        return {"tipo": "mensaje", "mensaje": "Puedo ayudar con servicios, disponibilidad y reservas."}

    faltan = [campo for campo in REQUERIDOS.get(accion, ()) if not plan.get(campo)]
    if faltan:
        return {"tipo": "faltan_datos", "mensaje": "Necesito: " + ", ".join(faltan), "plan": plan}

    if accion in {"crear", "modificar", "cancelar"} and not confirmar:
        resumen = ", ".join(f"{campo}={plan[campo]}" for campo in REQUERIDOS[accion])
        return {"tipo": "confirmacion", "mensaje": f"Voy a {accion} la reserva: {resumen}. ¿Confirmas?", "plan": plan}

    base = api_base.rstrip("/")
    reservas = RUTAS["reservas"]
    if accion == "servicios":
        datos = peticion_json(base + RUTAS["servicios"])
    elif accion == "disponibilidad":
        parametros = urlencode({"fecha": plan["fecha"], "servicio": plan["servicio"]})
        datos = peticion_json(base + RUTAS["disponibilidad"] + "?" + parametros)
    elif accion == "crear":
        cuerpo = {campo: plan[campo] for campo in ("cliente", "servicio", "fecha", "hora")}
        cuerpo["confirmada"] = True
        datos = peticion_json(base + reservas, "POST", cuerpo)
    elif accion == "modificar":
        cuerpo = {campo: plan[campo] for campo in ("servicio", "fecha", "hora")}
        datos = peticion_json(base + reservas + "/" + quote(plan["codigo"], safe=""), "PUT", cuerpo)
    else:
        datos = peticion_json(base + reservas + "/" + quote(plan["codigo"], safe=""), "DELETE")
    return {"tipo": "resultado", "accion": accion, "datos": datos}


def main():
    clave = os.getenv("GROQ_API_KEY", "").strip() or getpass("API key de Groq: ").strip()
    modelo = os.getenv("GROQ_MODEL", "").strip() or input("ID del modelo de Groq: ").strip()
    if not clave or not modelo:
        print("Necesito la API key y el ID del modelo.")
        return
    print("Escribe una solicitud. Para terminar, escribe SALIR.")
    while True:
        pregunta = input("\nTú: ").strip()
        if pregunta.casefold() == "salir":
            break
        if not pregunta:
            continue
        try:
            plan = interpretar(pregunta, clave, modelo)
            resultado = ejecutar(plan)
            print("Chatbot:", resultado.get("mensaje") or json.dumps(resultado["datos"], ensure_ascii=False, indent=2))
            if resultado["tipo"] == "confirmacion" and input("Confirmar (s/n): ").strip().casefold() == "s":
                resultado = ejecutar(plan, confirmar=True)
                print("FastAPI:", json.dumps(resultado["datos"], ensure_ascii=False, indent=2))
        except HTTPError as error:
            print(f"Error HTTP {error.code}. Revisa la respuesta de Groq o de la FastAPI.")
        except (URLError, TimeoutError):
            print("No pude conectar con Groq o con la FastAPI. Revisa ambos servicios.")
        except (ValueError, KeyError, IndexError, TypeError):
            print("No pude interpretar la respuesta. Revisa el formato JSON y los datos solicitados.")


if __name__ == "__main__":
    main()
