"""Lógica del cliente LLM: Groq interpreta la intención y FastAPI ejecuta la operación.

Conecta el modelo de lenguaje en Groq (vía API compatible con OpenAI) con los endpoints
REST de VLFisioterapia en FastAPI (servicios, disponibilidad, agendamiento, reprogramación,
cancelación y consulta de citas persistidas en SQLite).
"""

import json
import os
import socket
from datetime import date
from getpass import getpass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

# Asegurar prioridad IPv4 para conexiones rápidas a api.groq.com
_orig_getaddrinfo = socket.getaddrinfo

def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    except Exception:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _getaddrinfo_ipv4


def cargar_env():
    """Carga variables desde el archivo .env si existen y no están en el entorno."""
    ruta_env = Path(__file__).resolve().parent / ".env"
    if ruta_env.exists():
        with open(ruta_env, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    clave, valor = linea.split("=", 1)
                    clave = clave.strip()
                    valor = valor.strip().strip('"').strip("'")
                    if clave not in os.environ:
                        os.environ[clave] = valor


cargar_env()

API_BASE = os.getenv("CHATBOT_API_URL", "http://127.0.0.1:8012").rstrip("/")
RUTAS = {
    "servicios": "/servicios",
    "disponibilidad": "/disponibilidad",
    "citas": "/citas",
    "reprogramar": "/citas/{codigo}/reprogramar",
    "cancelar": "/citas/{codigo}",
    "consultar": "/citas/{codigo}",
}
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CAMPOS = ("accion", "cliente", "servicio", "fecha", "hora", "codigo")
ACCIONES = {
    "servicios",
    "disponibilidad",
    "crear",
    "modificar",
    "cancelar",
    "consultar",
    "fuera_de_alcance",
}
REQUERIDOS = {
    "disponibilidad": ("servicio", "fecha"),
    "crear": ("cliente", "servicio", "fecha", "hora"),
    "modificar": ("codigo", "fecha", "hora"),
    "cancelar": ("codigo",),
    "consultar": ("codigo",),
}

# Diccionario de normalización para mapear nombres coloquiales a claves válidas de clinica.json
MAPA_SERVICIOS = {
    "evaluacion": "evaluacion",
    "valoracion": "evaluacion",
    "diagnostico": "evaluacion",
    "valoracion inicial": "evaluacion",
    "deportiva": "deportiva",
    "fisioterapia deportiva": "deportiva",
    "readaptacion": "deportiva",
    "traumatologica": "traumatologica",
    "traumatologia": "traumatologica",
    "postquirurgica": "traumatologica",
    "fracturas": "traumatologica",
    "puncion_seca": "puncion_seca",
    "puncion seca": "puncion_seca",
    "puncion": "puncion_seca",
    "terapia manual": "puncion_seca",
    "postural": "postural",
    "postura": "postural",
    "rpg": "postural",
    "columna": "postural",
    "reeducacion postural": "postural",
    "neurologica": "neurologica",
    "neurologia": "neurologica",
    "rehabilitacion neurologica": "neurologica",
    "acv": "neurologica",
}


def normalizar_servicio(servicio: str) -> str:
    """Normaliza el nombre del servicio a la clave oficial en la clínica."""
    if not servicio:
        return ""
    limpio = (
        servicio.strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    return MAPA_SERVICIOS.get(limpio, servicio.strip().lower())


INSTRUCCIONES = """
Identifica qué quiere hacer la persona en el centro de fisioterapia VLFisioterapia.
Devuelve únicamente un objeto JSON con estas claves: accion, cliente, servicio, fecha, hora, codigo.
Las acciones posibles son: servicios, disponibilidad, crear, modificar, cancelar, consultar, fuera_de_alcance.
Los servicios disponibles son: evaluacion, deportiva, traumatologica, puncion_seca, postural, neurologica.
Usa fecha en formato AAAA-MM-DD y hora en formato HH:MM (24 horas).
Si un dato no aparece en la pregunta, usa una cadena vacía ""; no lo inventes.
No afirmes que ya creaste o modificaste una cita: solo extrae la intención y los datos.
"""


def peticion_json(url, metodo="GET", datos=None, headers=None):
    """Envía una petición HTTP y decodifica la respuesta JSON."""
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8") if datos is not None else None
    encabezados = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    encabezados.update(headers or {})
    solicitud = Request(url, data=cuerpo, headers=encabezados, method=metodo)
    with urlopen(solicitud, timeout=30) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def extraer_json(texto: str) -> dict:
    """Extrae un diccionario JSON de una cadena de texto, limpiando bloques markdown."""
    texto = texto.strip()
    if texto.startswith("```"):
        lineas = texto.splitlines()
        if len(lineas) >= 2 and lineas[-1].startswith("```"):
            texto = "\n".join(lineas[1:-1]).strip()
        elif lineas[0].startswith("```"):
            texto = "\n".join(lineas[1:]).strip()
    ini = texto.find("{")
    fin = texto.rfind("}")
    if ini != -1 and fin != -1 and fin > ini:
        texto = texto[ini : fin + 1]
    return json.loads(texto)


def interpretar(pregunta, clave, modelo):
    """Llama a Groq para identificar la intención y estructurar los datos del usuario."""
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": pregunta},
        ],
        "stream": False,
    }
    respuesta = peticion_json(
        GROQ_URL,
        "POST",
        payload,
        {"Authorization": f"Bearer {clave}"},
    )
    texto = respuesta["choices"][0]["message"]["content"]
    plan = extraer_json(texto)
    if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
        raise ValueError("Groq no devolvió una acción válida")

    return {campo: str(plan.get(campo) or "").strip() for campo in CAMPOS}


def formatear_respuesta(resultado: dict) -> str:
    """Formatea la respuesta devuelta por la API para mostrar en consola de forma amigable."""
    if resultado.get("mensaje"):
        return resultado["mensaje"]

    datos = resultado.get("datos")
    accion = resultado.get("accion")

    if accion == "servicios" and isinstance(datos, dict):
        lineas = ["Tratamientos disponibles en VLFisioterapia:"]
        for clave, info in datos.items():
            precio = f"${info['precio_cop']:,}".replace(",", ".") + " COP"
            lineas.append(f" • {info['nombre']} ({clave}): {precio} - {info['duracion_minutos']} min")
            lineas.append(f"   {info['descripcion']}")
        return "\n".join(lineas)

    if accion == "disponibilidad" and isinstance(datos, dict):
        horas = datos.get("horarios_disponibles") or datos.get("horas", [])
        if not horas:
            return f"No hay turnos disponibles para {datos.get('servicio')} el {datos.get('fecha')}."
        return f"Turnos libres para {datos.get('servicio')} el {datos.get('fecha')}:\n  " + ", ".join(horas)

    if accion == "consultar" and isinstance(datos, dict):
        return (
            f"Cita {datos.get('codigo')} [{datos.get('estado', '').upper()}]:\n"
            f" • Paciente: {datos.get('cliente')}\n"
            f" • Tratamiento: {datos.get('servicio')}\n"
            f" • Especialista asignado: {datos.get('fisioterapeuta_asignado')}\n"
            f" • Fecha y hora: {datos.get('fecha')} a las {datos.get('hora')}\n"
            f" • Duración: {datos.get('duracion_minutos')} min - Tarifa: ${datos.get('precio_cop', 0):,} COP".replace(",", ".")
        )

    if accion == "crear" and isinstance(datos, dict):
        return (
            f"¡Cita creada con éxito! 🎉 Código: {datos.get('codigo')}\n"
            f" • Paciente: {datos.get('cliente')}\n"
            f" • Servicio: {datos.get('servicio')}\n"
            f" • Fecha y hora: {datos.get('fecha')} a las {datos.get('hora')}\n"
            f" • Fisioterapeuta: {datos.get('fisioterapeuta_asignado')}"
        )

    if accion == "modificar" and isinstance(datos, dict):
        return (
            f"Cita modificada con éxito. Código: {datos.get('codigo')}\n"
            f" • Nueva fecha y hora: {datos.get('fecha')} a las {datos.get('hora')}\n"
            f" • Especialista: {datos.get('fisioterapeuta_asignado')}"
        )

    if accion == "cancelar" and isinstance(datos, dict):
        return f"La cita {datos.get('codigo')} ha sido cancelada. El turno ha quedado disponible."

    return json.dumps(datos, ensure_ascii=False, indent=2)


def ejecutar(plan, confirmar=False, api_base=API_BASE):
    """Ejecuta la acción validada llamando al endpoint correspondiente de FastAPI."""
    accion = plan.get("accion", "")
    if accion not in ACCIONES:
        raise ValueError(f"Acción '{accion}' no permitida")

    if accion == "fuera_de_alcance":
        return {
            "tipo": "mensaje",
            "mensaje": (
                "En VLFisioterapia nos especializamos en fisioterapia, rehabilitación funcional y salud física. "
                "Puedo ayudarte con información de tratamientos, disponibilidad de horarios o agendar, consultar, modificar y cancelar citas."
            ),
        }

    # Normalizar clave de servicio si viene informada
    if plan.get("servicio"):
        plan["servicio"] = normalizar_servicio(plan["servicio"])

    faltan = [campo for campo in REQUERIDOS.get(accion, ()) if not plan.get(campo)]
    if faltan:
        nombres_amigables = {
            "cliente": "nombre del paciente",
            "servicio": "servicio (evaluacion, deportiva, traumatologica, puncion_seca, postural, neurologica)",
            "fecha": "fecha en formato AAAA-MM-DD",
            "hora": "hora en formato HH:MM",
            "codigo": "código de la cita (ejemplo: VF-XXXXXXXXXX)",
        }
        faltan_str = ", ".join(nombres_amigables.get(c, c) for c in faltan)
        return {
            "tipo": "faltan_datos",
            "mensaje": f"Para {accion} necesito los siguientes datos pendientes: {faltan_str}.",
            "plan": plan,
        }

    if accion in {"crear", "modificar", "cancelar"} and not confirmar:
        if accion == "crear":
            resumen = f"servicio={plan['servicio']}, paciente={plan['cliente']}, fecha={plan['fecha']}, hora={plan['hora']}"
        elif accion == "modificar":
            resumen = f"código={plan['codigo']}, nueva fecha={plan['fecha']}, nueva hora={plan['hora']}"
        else:
            resumen = f"código={plan['codigo']}"
        return {
            "tipo": "confirmacion",
            "mensaje": f"Voy a {accion} la cita: {resumen}. ¿Confirmas la operación? (s/n)",
            "plan": plan,
        }

    base = api_base.rstrip("/")

    if accion == "servicios":
        datos = peticion_json(base + RUTAS["servicios"])
    elif accion == "disponibilidad":
        parametros = urlencode({"fecha": plan["fecha"], "servicio": plan["servicio"]})
        datos = peticion_json(base + RUTAS["disponibilidad"] + "?" + parametros)
    elif accion == "consultar":
        cod = quote(plan["codigo"].strip().upper(), safe="")
        datos = peticion_json(base + f"/citas/{cod}")
    elif accion == "crear":
        cuerpo = {
            "cliente": plan["cliente"],
            "servicio": plan["servicio"],
            "fecha": plan["fecha"],
            "hora": plan["hora"],
            "confirmado": True,
        }
        datos = peticion_json(base + RUTAS["citas"], "POST", cuerpo)
    elif accion == "modificar":
        cod = quote(plan["codigo"].strip().upper(), safe="")
        cuerpo = {
            "nueva_fecha": plan["fecha"],
            "nueva_hora": plan["hora"],
            "confirmado": True,
        }
        datos = peticion_json(base + f"/citas/{cod}/reprogramar", "PATCH", cuerpo)
    elif accion == "cancelar":
        cod = quote(plan["codigo"].strip().upper(), safe="")
        datos = peticion_json(base + f"/citas/{cod}?confirmado=true", "DELETE")
    else:
        raise ValueError(f"Acción no soportada: {accion}")

    return {"tipo": "resultado", "accion": accion, "datos": datos}


def main():
    cargar_env()
    clave = os.getenv("GROQ_API_KEY", "").strip() or getpass("API key de Groq: ").strip()
    modelo = os.getenv("GROQ_MODEL", "").strip() or input("ID del modelo de Groq: ").strip()
    if not clave or not modelo:
        print("Se requiere la API key y el ID del modelo.")
        return

    print("=" * 60)
    print("VLFisioterapia · Asistente con LLM (Clase 06)")
    print(f"Conectado a FastAPI en: {API_BASE}")
    print("Escribe tu solicitud. Para terminar, escribe SALIR.")
    print("=" * 60)

    while True:
        pregunta = input("\nTú: ").strip()
        if pregunta.casefold() == "salir":
            print("¡Hasta luego!")
            break
        if not pregunta:
            continue
        try:
            plan = interpretar(pregunta, clave, modelo)
            resultado = ejecutar(plan)
            print("Chatbot:", formatear_respuesta(resultado))
            if resultado["tipo"] == "confirmacion":
                confirmacion = input("Confirmar (s/n): ").strip().casefold()
                if confirmacion == "s":
                    resultado = ejecutar(plan, confirmar=True)
                    print("FastAPI:", formatear_respuesta(resultado))
                else:
                    print("Operación cancelada por el usuario.")
        except HTTPError as error:
            try:
                detalle = error.read().decode("utf-8")
                detalle_json = json.loads(detalle)
                mensaje_error = detalle_json.get("detail", detalle)
            except Exception:
                mensaje_error = f"Código {error.code}"
            print(f"Error HTTP {error.code} de FastAPI/Groq: {mensaje_error}")
        except (URLError, TimeoutError):
            print(f"No pude conectar con Groq o con la FastAPI en {API_BASE}. Asegúrate de que el servidor esté encendido.")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            print(f"No pude interpretar la respuesta ({exc}). Revisa el formato JSON devuelto.")


if __name__ == "__main__":
    main()
