"""Canal de Telegram para VLFisioterapia.
Propuestas conversacionales por chat, botones de confirmación y operaciones mediante FastAPI.
"""

import asyncio
import json
import logging
import os
import re
from copy import deepcopy
from datetime import datetime
from getpass import getpass
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from consulta_llm import GROQ_URL, cargar_env, normalizar_servicio, peticion_json

cargar_env()

ZONA_BOGOTA = ZoneInfo("America/Bogota")
ACCIONES = {"servicios", "disponibilidad", "consultar", "crear", "modificar", "cancelar", "fuera_de_alcance"}
CAMPOS = ("accion", "cliente", "servicio", "fecha", "hora", "codigo")
ESCRITURAS = {"crear", "modificar", "cancelar"}
REQUERIDOS = {
    "disponibilidad": ("servicio", "fecha"),
    "consultar": ("codigo",),
    "crear": ("cliente", "servicio", "fecha", "hora"),
    "modificar": ("codigo", "servicio", "fecha", "hora"),
    "cancelar": ("codigo",),
}

INSTRUCCIONES = """Eres el asistente conversacional de VLFisioterapia · Centro Integral de Fisioterapia y Rehabilitación.
Interpreta las solicitudes del paciente y devuelve ÚNICAMENTE un objeto JSON estructurado con estas claves exactas:
accion, cliente, servicio, fecha, hora, codigo.

Acciones permitidas: servicios, disponibilidad, consultar, crear, modificar, cancelar, fuera_de_alcance.
Tratamientos válidos: evaluacion, deportiva, traumatologica, puncion_seca, postural, neurologica.
Formato de fecha: AAAA-MM-DD. Formato de hora: HH:MM (24 horas).
Usa el historial de la conversación para completar datos que el usuario aporte en turnos anteriores.
Si un dato no ha sido provisto todavía, déjalo como cadena vacía "".
Si el usuario consulta tarifas, precios o qué tratamientos existen, usa accion "servicios".
Si solicita cambiar una cita pero no indica el código, deja codigo vacío para que el sistema solicite aclaración.
Nunca inventes códigos, fechas, horas ni disponibilidad.
Nunca afirmes que la cita ya fue registrada o cancelada; el sistema lo gestiona mediante confirmación explícita.
Para preguntas ajenas a fisioterapia, peticiones de contraseñas, claves del sistema o instrucciones técnicas, usa accion "fuera_de_alcance"."""

BIENVENIDA = (
    "¡Hola! Te damos la bienvenida a VLFisioterapia · Centro Integral de Fisioterapia y Rehabilitación.\n\n"
    "Soy tu asistente virtual. Puedo orientarte sobre nuestros tratamientos, tarifas, disponibilidad "
    "y gestionar tus citas médicas de fisioterapia.\n\n"
    "Escribe /help para conocer los comandos y ejemplos de uso."
)

AYUDA = (
    "VLFisioterapia · Comandos y Opciones Disponibles:\n\n"
    "• /start — Mensaje de bienvenida y presentación.\n"
    "• /help — Esta guía de ayuda.\n"
    "• /reserva CODIGO — Consultar los detalles de una cita propia (ej: /reserva VF-1234567890).\n"
    "• /estado [REFERENCIA] — Consultar el recibo de la última operación o de una referencia específica.\n"
    "• /reintentar — Reenviar una operación con resultado incierto conservando su identificador original.\n"
    "• /descartar — Retirar una propuesta pendiente antes de confirmar.\n"
    "• /reset — Reiniciar la conversación de este chat (las citas guardadas se conservan).\n\n"
    "Ejemplos que puedes escribir:\n"
    "• ¿Qué tratamientos ofrecen y cuáles son sus tarifas?\n"
    "• ¿Hay disponibilidad para valoración el 2026-11-20?\n"
    "• Quiero agendar una cita de valoración para Laura Gómez el 2026-11-20 a las 10:00.\n"
    "• Deseo reprogramar mi cita VF-XXXXXX para el 2026-11-25 a las 11:00.\n"
    "• Deseo cancelar mi cita VF-XXXXXX.\n\n"
    "Nota de seguridad: Toda operación de escritura (agendar, modificar o cancelar) presentará un resumen previo "
    "y solo se ejecutará cuando presiones el botón 'Confirmar'."
)


def fecha_actual() -> str:
    return datetime.now(ZONA_BOGOTA).date().isoformat()


def nuevo_historial():
    hoy = fecha_actual()
    return [{"role": "system", "content": INSTRUCCIONES + f"\nFecha actual en Armenia, Quindío ({ZONA_BOGOTA.key}): {hoy}."}]


def formatear_pesos(valor: int) -> str:
    return f"${valor:,}".replace(",", ".") + " COP"


def interpretar(pregunta, historial, clave, modelo):
    payload = {"model": modelo, "messages": historial + [{"role": "user", "content": pregunta}], "stream": False}
    respuesta = peticion_json(GROQ_URL, "POST", payload, {"Authorization": f"Bearer {clave}"})
    texto = respuesta["choices"][0]["message"]["content"].strip()
    ini = texto.find("{")
    fin = texto.rfind("}")
    if ini != -1 and fin != -1 and fin > ini:
        texto = texto[ini : fin + 1]
    plan = json.loads(texto)
    if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
        raise ValueError("Acción inválida en la respuesta del modelo")
    plan = {campo: str(plan.get(campo) or "").strip() for campo in CAMPOS}
    if plan.get("servicio"):
        plan["servicio"] = normalizar_servicio(plan["servicio"])
    return plan


def preparar_pendiente(plan, chat_id, usuario_id, referencia=""):
    return {
        "solicitud_id": uuid4().hex,
        "chat_id": chat_id,
        "usuario_id": usuario_id,
        "plan": deepcopy(plan),
        "referencia": referencia,
        "estado": "por_confirmar",
        "vence_en": monotonic() + 600,  # 10 minutos de vigencia
    }


def motivo_rechazo(pendiente, solicitud_id, chat_id, usuario_id, ahora):
    if pendiente is None:
        return "No hay una solicitud pendiente en esta conversación."
    if pendiente["chat_id"] != chat_id or pendiente["usuario_id"] != usuario_id:
        return "Esta confirmación no corresponde a tu conversación."
    if pendiente["solicitud_id"] != solicitud_id:
        return "Ese resumen ya no es el vigente."
    if pendiente["estado"] != "por_confirmar":
        return "La solicitud ya se está procesando o tiene un resultado por verificar."
    if ahora >= pendiente["vence_en"]:
        return "El resumen venció (límite de 10 minutos). Prepara y revisa una nueva solicitud."
    return None


def teclado_pendiente(pendiente):
    identificador = pendiente["solicitud_id"]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Confirmar", callback_data=f"confirmar:{identificador}"),
            InlineKeyboardButton("Descartar", callback_data=f"descartar:{identificador}"),
        ]
    ])


class FalloAPI(Exception):
    def __init__(self, estado, detalle, resultado=None):
        super().__init__(detalle)
        self.estado, self.detalle, self.resultado = estado, detalle, resultado


class ClienteAPI:
    def __init__(self, base, clave):
        self.base, self.clave = base.rstrip("/"), clave

    def solicitar(self, ruta, usuario_id, metodo="GET", datos=None):
        headers = {"X-API-Key": self.clave, "X-Telegram-User": str(usuario_id)}
        try:
            return peticion_json(self.base + "/telegram" + ruta, metodo, datos, headers)
        except HTTPError as error:
            try:
                contenido = json.loads(error.read().decode("utf-8"))
            except (ValueError, UnicodeError):
                contenido = {}
            detalle = contenido.get("detalle") or contenido.get("detail") or "El servicio rechazó la petición"
            if not isinstance(detalle, str):
                detalle = "Revisa los datos enviados al servicio"
            raise FalloAPI(error.code, detalle, contenido) from error

    def leer(self, plan, usuario_id):
        accion = plan["accion"]
        if accion == "servicios":
            return self.solicitar("/servicios", usuario_id)
        if accion == "disponibilidad":
            return self.solicitar(
                "/disponibilidad?" + urlencode({"fecha": plan["fecha"], "servicio": plan["servicio"]}),
                usuario_id,
            )
        if accion == "consultar":
            return self.consultar(plan["codigo"], usuario_id)
        raise ValueError("Lectura no admitida")

    def consultar(self, codigo, usuario_id):
        return self.solicitar("/reservas/" + quote(codigo.strip().upper(), safe=""), usuario_id)

    def ejecutar(self, pendiente):
        plan = pendiente["plan"]
        cuerpo = {
            "solicitud_id": pendiente["solicitud_id"],
            "accion": plan["accion"],
            "datos": {campo: plan.get(campo, "") for campo in CAMPOS if campo != "accion"},
            "referencia": pendiente["referencia"],
            "confirmada": True,
        }
        return self.solicitar("/operaciones", pendiente["usuario_id"], "POST", cuerpo)

    def estado(self, identificador, usuario_id):
        return self.solicitar("/operaciones/" + quote(identificador.strip(), safe=""), usuario_id)


def registrar_turno(context, pregunta, resultado, plan=None):
    mensajes = context.chat_data.setdefault("historial", nuevo_historial())
    mensajes.extend([
        {"role": "user", "content": pregunta},
        {"role": "assistant", "content": json.dumps({"plan": plan, "resultado": resultado}, ensure_ascii=False)},
    ])


def describir_reserva(reserva: dict) -> str:
    lineas = [
        f"• Código: {reserva.get('codigo', '')}",
        f"• Paciente: {reserva.get('cliente', '')}",
        f"• Tratamiento: {reserva.get('servicio', '')}",
        f"• Fecha: {reserva.get('fecha', '')}",
        f"• Hora: {reserva.get('hora', '')}",
        f"• Estado: {reserva.get('estado', '').upper()}",
    ]
    fisio = reserva.get("fisioterapeuta_asignado") or reserva.get("fisioterapeuta")
    if fisio:
        lineas.append(f"• Especialista: {fisio}")
    precio = reserva.get("precio_cop")
    if precio:
        lineas.append(f"• Tarifa: {formatear_pesos(precio)}")
    return "\n".join(lineas)


def formatear_lectura(accion: str, datos: dict) -> str:
    if accion == "servicios":
        lineas = ["Tratamientos disponibles en VLFisioterapia:"]
        for clave, info in datos.items():
            lineas.append(
                f"• {info.get('nombre', clave)} ({clave}): {formatear_pesos(info.get('precio_cop', 0))}, "
                f"{info.get('duracion_minutos', 0)} min\n  {info.get('descripcion', '')}"
            )
        return "\n".join(lineas)
    if accion == "disponibilidad":
        horas = ", ".join(datos.get("horarios_disponibles") or datos.get("horas") or []) or "Sin horarios libres"
        return f"Disponibilidad para {datos.get('servicio', '')} el {datos.get('fecha', '')}:\n{horas}"
    if isinstance(datos, dict) and "reserva" in datos:
        return describir_reserva(datos["reserva"])
    return json.dumps(datos, ensure_ascii=False, indent=2)


async def enviar(mensaje, texto):
    for inicio in range(0, len(texto), 4000):
        await mensaje.reply_text(texto[inicio : inicio + 4000])


async def quitar_controles(context, pendiente):
    if pendiente and pendiente.get("mensaje_id"):
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=pendiente["chat_id"],
                message_id=pendiente["mensaje_id"],
                reply_markup=None,
            )
        except TelegramError:
            logging.warning("No se retiró el teclado; la validación del servidor sigue activa")


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data.setdefault("historial", nuevo_historial())
    await enviar(update.effective_message, BIENVENIDA)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar(update.effective_message, AYUDA)


async def reiniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pendiente = context.chat_data.get("pendiente")
    if pendiente and pendiente["estado"] in {"ejecutando", "incierta"}:
        await enviar(
            update.effective_message,
            "Primero verifica la operación con /estado. Conservo su referencia para evitar un reenvío accidental.",
        )
        return
    await quitar_controles(context, pendiente)
    context.chat_data.clear()
    context.chat_data["historial"] = nuevo_historial()
    await enviar(
        update.effective_message,
        "Conversación reiniciada. Tus citas guardadas se conservan. ¿En qué te puedo colaborar?",
    )


async def descartar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pendiente = context.chat_data.get("pendiente")
    if pendiente and pendiente["estado"] != "por_confirmar":
        await enviar(
            update.effective_message,
            "La operación necesita verificarse con /estado antes de retirar su referencia.",
        )
        return
    await quitar_controles(context, pendiente)
    context.chat_data.pop("pendiente", None)
    registrar_turno(context, "/descartar", "La propuesta fue descartada sin ejecutar.")
    await enviar(update.effective_message, "Retiré la propuesta pendiente. Las citas registradas se conservan.")


async def consultar_reserva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await enviar(update.effective_message, "Usa /reserva CODIGO para consultar una cita propia (ej: /reserva VF-1234567890).")
        return
    codigo = context.args[0].strip().upper()
    try:
        datos = await asyncio.to_thread(context.bot_data["api"].consultar, codigo, update.effective_user.id)
    except FalloAPI as error:
        await enviar(update.effective_message, error.detalle)
        return
    except (URLError, TimeoutError, ValueError):
        await enviar(update.effective_message, "No pude completar la consulta a la API de VLFisioterapia.")
        return
    registrar_turno(context, update.effective_message.text, datos)
    context.chat_data.setdefault("codigos", set()).add(codigo)
    await enviar(update.effective_message, describir_reserva(datos["reserva"]))


async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = update.effective_message
    pregunta = (mensaje.text or "").strip()
    if not pregunta:
        return
    pendiente = context.chat_data.get("pendiente")
    if pendiente and pendiente["estado"] in {"ejecutando", "incierta"}:
        await enviar(
            mensaje,
            f"Hay una operación con resultado por verificar ({pendiente['solicitud_id']}). Usa /estado o /reintentar.",
        )
        return

    interprete = context.bot_data.get("interprete", interpretar)
    clave, modelo = context.bot_data.get("clave_modelo", ""), context.bot_data.get("modelo", "")
    if interprete is interpretar and (not clave or not modelo):
        await enviar(mensaje, "Falta configurar GROQ_API_KEY o GROQ_MODEL en el servidor del bot.")
        return

    historial = context.chat_data.setdefault("historial", nuevo_historial())
    try:
        plan = await asyncio.to_thread(interprete, pregunta, historial, clave, modelo)
        if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
            raise ValueError("Plan inválido")
        plan = {campo: str(plan.get(campo) or "").strip() for campo in CAMPOS}
        accion = plan["accion"]

        if accion == "fuera_de_alcance":
            texto = (
                "En VLFisioterapia nos especializamos en fisioterapia, rehabilitación funcional y salud física. "
                "Puedo ayudarte con información de nuestros 6 tratamientos, tarifas, horarios o agendar una cita."
            )
            registrar_turno(context, pregunta, texto, plan)
            await enviar(mensaje, texto)
            return

        if accion in {"consultar", "modificar", "cancelar"}:
            conocidos = context.chat_data.get("codigos", set())
            explicito = plan["codigo"] and plan["codigo"].casefold() in pregunta.casefold()
            if not explicito and (len(conocidos) != 1 or plan["codigo"] not in conocidos):
                plan["codigo"] = ""

        if accion in ESCRITURAS and pendiente:
            if accion != pendiente["plan"]["accion"] or (plan["codigo"] and plan["codigo"] != pendiente["plan"]["codigo"]):
                await enviar(mensaje, "Primero confirma o descarta la propuesta vigente para iniciar otra operación.")
                return
            await quitar_controles(context, pendiente)
            context.chat_data.pop("pendiente", None)

        referencia = ""
        if accion == "modificar" and plan["codigo"]:
            actual = await asyncio.to_thread(context.bot_data["api"].consultar, plan["codigo"], update.effective_user.id)
            referencia = actual["referencia"]
            for campo in ("servicio", "fecha", "hora"):
                plan[campo] = plan[campo] or actual["reserva"][campo]

        faltan = [campo for campo in REQUERIDOS.get(accion, ()) if not plan[campo]]
        if faltan:
            texto = "Para continuar necesito los siguientes datos: " + ", ".join(faltan)
            registrar_turno(context, pregunta, texto, plan)
            await enviar(mensaje, texto)
            return

        if accion not in ESCRITURAS:
            datos = await asyncio.to_thread(context.bot_data["api"].leer, plan, update.effective_user.id)
            registrar_turno(context, pregunta, datos, plan)
            await enviar(mensaje, formatear_lectura(accion, datos))
            return

        if accion == "cancelar":
            actual = await asyncio.to_thread(context.bot_data["api"].consultar, plan["codigo"], update.effective_user.id)
            referencia = actual["referencia"]
            for campo in ("cliente", "servicio", "fecha", "hora"):
                plan[campo] = actual["reserva"][campo]

        pendiente = preparar_pendiente(plan, update.effective_chat.id, update.effective_user.id, referencia)
        context.chat_data["pendiente"] = pendiente

        lineas_resumen = [
            f"Propuesta de operación: {accion.upper()}",
            f"• Paciente: {plan['cliente']}",
            f"• Tratamiento: {plan['servicio']}",
            f"• Fecha: {plan['fecha']}",
            f"• Hora: {plan['hora']}",
        ]
        if plan["codigo"]:
            lineas_resumen.append(f"• Código de cita: {plan['codigo']}")
        lineas_resumen.extend([
            f"• Referencia de solicitud: {pendiente['solicitud_id']}",
            "Revisa los datos y pulsa Confirmar para ejecutar en la agenda o Descartar para cancelarla.",
        ])
        resumen = "\n".join(lineas_resumen)

        registrar_turno(context, pregunta, "Propuesta presentada pendiente de confirmación", plan)
        enviado = await mensaje.reply_text(resumen, reply_markup=teclado_pendiente(pendiente))
        pendiente["mensaje_id"] = enviado.message_id

    except FalloAPI as error:
        await enviar(mensaje, error.detalle)
    except HTTPError:
        await enviar(mensaje, "El servicio de procesamiento del modelo rechazó la consulta. Revisa la configuración.")
    except (URLError, TimeoutError):
        await enviar(mensaje, "No pude conectar con el servicio. Todavía no se envió ninguna escritura.")
    except (ValueError, KeyError, IndexError, TypeError):
        await enviar(mensaje, "La respuesta no tiene el formato esperado. Por favor reformula o completa la solicitud.")


def validar_resultado(resultado, pendiente):
    if (
        not isinstance(resultado, dict)
        or resultado.get("ok") is not True
        or resultado.get("solicitud_id") != pendiente["solicitud_id"]
        or resultado.get("accion") != pendiente["plan"]["accion"]
    ):
        raise ValueError("Resultado de escritura inesperado")
    for campo in ("codigo", "cliente", "servicio", "fecha", "hora", "estado"):
        if not isinstance(resultado.get("reserva", {}).get(campo), str):
            raise ValueError("La respuesta no identifica completamente la reserva")


async def resultado_registrado(context, pendiente, resultado, mensaje):
    identificador = resultado["solicitud_id"]
    actual = context.chat_data.get("pendiente")
    if actual and actual["solicitud_id"] == identificador:
        context.chat_data.pop("pendiente", None)

    plan_resultado = (
        pendiente["plan"]
        if pendiente and pendiente["solicitud_id"] == identificador
        else {"accion": resultado.get("accion"), "codigo": resultado.get("reserva", {}).get("codigo", "")}
    )
    registrar_turno(context, f"Resultado de solicitud {identificador}", resultado, plan_resultado)

    if resultado.get("ok"):
        reserva = resultado["reserva"]
        context.chat_data.setdefault("codigos", set()).add(reserva["codigo"])
        texto = (
            f"¡Operación {resultado['accion'].upper()} registrada con éxito! 🎉\n"
            + describir_reserva(reserva)
            + f"\n• Referencia de operación: {identificador}"
            f"\n• Consulta directa: /reserva {reserva['codigo']}"
        )
    else:
        texto = "La API de VLFisioterapia rechazó la operación: " + resultado.get("detalle", "Revisa los datos.")
    await enviar(mensaje, texto)


async def ejecutar_confirmada(context, pendiente, mensaje):
    pendiente["estado"] = "ejecutando"
    context.chat_data["ultima_solicitud"] = pendiente["solicitud_id"]
    await quitar_controles(context, pendiente)

    try:
        resultado = await asyncio.to_thread(context.bot_data["api"].ejecutar, deepcopy(pendiente))
        validar_resultado(resultado, pendiente)
    except FalloAPI as error:
        if error.estado < 500:
            respuesta = {
                "ok": False,
                "solicitud_id": pendiente["solicitud_id"],
                "accion": pendiente["plan"]["accion"],
                "detalle": error.detalle,
            }
            await resultado_registrado(context, pendiente, respuesta, mensaje)
            return
        pendiente["estado"] = "incierta"
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        pendiente["estado"] = "incierta"
    else:
        await resultado_registrado(context, pendiente, resultado, mensaje)
        return

    await enviar(
        mensaje,
        "No pude verificar el resultado inmediatamente debido a un problema de red. "
        f"Conservo la misma referencia de operación: {pendiente['solicitud_id']}. "
        "Usa /estado para recuperar el recibo guardado antes de intentar otra operación.",
    )


async def atender_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    consulta = update.callback_query
    await consulta.answer()
    chat = update.effective_chat
    if chat is None or chat.type != "private" or not isinstance(consulta.data, str):
        return

    accion, identificador = consulta.data.split(":", 1)
    pendiente = context.chat_data.get("pendiente")
    motivo = motivo_rechazo(pendiente, identificador, chat.id, consulta.from_user.id, monotonic())
    if motivo:
        if (
            pendiente
            and pendiente["solicitud_id"] == identificador
            and pendiente["usuario_id"] == consulta.from_user.id
            and pendiente["estado"] == "por_confirmar"
            and monotonic() >= pendiente["vence_en"]
        ):
            await quitar_controles(context, pendiente)
            context.chat_data.pop("pendiente", None)
        await context.bot.send_message(chat.id, motivo)
        return

    if accion == "descartar":
        await quitar_controles(context, pendiente)
        context.chat_data.pop("pendiente", None)
        registrar_turno(context, f"Descartar {identificador}", "La propuesta no se ejecutó", pendiente["plan"])
        await context.bot.send_message(chat.id, "Propuesta descartada. No se modificó tu agenda.")
        return

    await ejecutar_confirmada(context, pendiente, consulta.message)


async def consultar_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pendiente = context.chat_data.get("pendiente")
    identificador = ""
    if context.args and len(context.args) >= 1:
        identificador = context.args[0].strip().lower()
    if not identificador:
        if pendiente and isinstance(pendiente, dict) and pendiente.get("solicitud_id"):
            identificador = pendiente["solicitud_id"]
        else:
            identificador = context.chat_data.get("ultima_solicitud", "")

    if not re.fullmatch(r"[0-9a-f]{32}", identificador):
        await enviar(update.effective_message, "Usa /estado REFERENCIA indicando la referencia hexadecimal de 32 caracteres.")
        return

    try:
        datos = await asyncio.to_thread(context.bot_data["api"].estado, identificador, update.effective_user.id)
        resultado = datos["resultado"]
        if resultado.get("solicitud_id") != identificador:
            raise ValueError("Referencia inesperada")
        if resultado.get("ok"):
            provisional = (
                pendiente
                if pendiente and pendiente["solicitud_id"] == identificador
                else {"solicitud_id": identificador, "plan": {"accion": resultado.get("accion")}}
            )
            validar_resultado(resultado, provisional)
    except FalloAPI as error:
        texto = (
            "Todavía no hay un resultado verificable registrado para esa solicitud. "
            "Conservo la referencia; no asumo que falló."
            if error.estado == 404
            else error.detalle
        )
        await enviar(update.effective_message, texto)
        return
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        await enviar(update.effective_message, "No pude verificar el estado en la API. Conservo la referencia de la operación.")
        return

    await resultado_registrado(context, pendiente, resultado, update.effective_message)


async def reintentar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pendiente = context.chat_data.get("pendiente")
    if not pendiente or pendiente["estado"] != "incierta":
        await enviar(update.effective_message, "No hay una operación con estado incierto pendiente de reenvío.")
        return
    await ejecutar_confirmada(context, pendiente, update.effective_message)


async def desconocido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar(update.effective_message, "Comando no reconocido. Escribe /help para consultar los comandos disponibles.")


async def otro_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar(
        update.effective_message,
        "Por el momento atiendo consultas escritas. Por favor envíame un mensaje de texto para atenderte.",
    )


async def informar_error(update, context):
    logging.error("Error del bot de Telegram: %s", type(context.error).__name__)


def registrar_handlers(aplicacion):
    privado = filters.ChatType.PRIVATE
    aplicacion.add_handler(
        CallbackQueryHandler(atender_decision, pattern=r"^(confirmar|descartar):[0-9a-f]{32}$", block=True)
    )
    for nombre, funcion in (
        ("start", iniciar),
        ("help", ayuda),
        ("reset", reiniciar),
        ("descartar", descartar),
        ("reserva", consultar_reserva),
        ("estado", consultar_estado),
        ("reintentar", reintentar),
    ):
        aplicacion.add_handler(CommandHandler(nombre, funcion, filters=privado))

    aplicacion.add_handler(MessageHandler(privado & filters.TEXT & ~filters.COMMAND, recibir_texto))
    aplicacion.add_handler(MessageHandler(privado & filters.COMMAND, desconocido))
    aplicacion.add_handler(MessageHandler(privado & ~filters.TEXT, otro_mensaje))
    aplicacion.add_error_handler(informar_error)


def crear_aplicacion(token, api, clave_modelo="", modelo="", interprete=None, request=None):
    constructor = Application.builder().token(token).concurrent_updates(False)
    if request is not None:
        constructor = constructor.request(request).get_updates_request(request)
    aplicacion = constructor.build()
    aplicacion.bot_data.update(api=api, clave_modelo=clave_modelo, modelo=modelo)
    if interprete is not None:
        aplicacion.bot_data["interprete"] = interprete
    registrar_handlers(aplicacion)
    return aplicacion


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or getpass("Token de BotFather (oculto): ").strip()
    clave_api = os.getenv("CHATBOT_API_KEY", "").strip() or getpass("Clave privada de la FastAPI (oculta): ").strip()
    if not token or not clave_api:
        print("Configura TELEGRAM_BOT_TOKEN y CHATBOT_API_KEY antes de iniciar el bot.")
        return
    url_api = os.getenv("CHATBOT_API_URL", "http://127.0.0.1:8012")
    api = ClienteAPI(url_api, clave_api)
    try:
        aplicacion = crear_aplicacion(token, api, os.getenv("GROQ_API_KEY", ""), os.getenv("GROQ_MODEL", ""))
        print(f"Bot de VLFisioterapia en ejecución por polling. Conectado a {url_api}. Para detenerlo: Ctrl+C.")
        aplicacion.run_polling(allowed_updates=["message", "callback_query"])
    except TelegramError as error:
        print(f"Telegram no completó el inicio: {type(error).__name__}.")


if __name__ == "__main__":
    main()
