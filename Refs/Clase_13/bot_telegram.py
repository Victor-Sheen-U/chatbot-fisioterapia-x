"""Telegram: propuestas por chat y operaciones mediante la FastAPI del equipo."""

import asyncio
import json
import logging
import os
import re
from copy import deepcopy
from datetime import date
from getpass import getpass
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from consulta_llm import GROQ_URL, peticion_json

ACCIONES = {"servicios", "disponibilidad", "consultar", "crear", "modificar", "cancelar", "fuera_de_alcance"}
CAMPOS = ("accion", "cliente", "servicio", "fecha", "hora", "codigo")
ESCRITURAS = {"crear", "modificar", "cancelar"}
REQUERIDOS = {"disponibilidad": ("servicio", "fecha"), "consultar": ("codigo",),
              "crear": ("cliente", "servicio", "fecha", "hora"),
              "modificar": ("codigo", "servicio", "fecha", "hora"), "cancelar": ("codigo",)}
INSTRUCCIONES = """Interpreta solicitudes del negocio. Devuelve solamente un objeto JSON
con accion, cliente, servicio, fecha, hora y codigo, todos como texto.
Acciones: servicios, disponibilidad, consultar, crear, modificar, cancelar, fuera_de_alcance.
Usa el historial para completar datos. Usa fecha AAAA-MM-DD y hora HH:MM.
Si falta información, deja el campo vacío. Si varias reservas podrían ser la solicitada,
deja codigo vacío para pedir aclaración. No inventes códigos, servicios ni disponibilidad.
La consulta de precios usa servicios. Nunca afirmes que ejecutaste una reserva.
Las decisiones de confirmar o descartar las procesa el programa mediante botones.
Las peticiones ajenas al negocio o de secretos usan fuera_de_alcance."""
AYUDA = (
    "Puedes consultar servicios y disponibilidad, preparar reservas, modificarlas y cancelarlas.\n"
    "Revisa siempre el resumen antes de pulsar Confirmar.\n\n"
    "/reserva CODIGO: consultar una reserva propia.\n"
    "/descartar: retirar la propuesta vigente.\n"
    "/estado [REFERENCIA]: comprobar el resultado de una operación.\n"
    "/reintentar: reenviar una operación incierta con el mismo identificador.\n"
    "/reset: reiniciar esta conversación.\n/start: bienvenida.\n/help: ayuda."
)


def nuevo_historial():
    return [{"role": "system", "content": INSTRUCCIONES + f"\nFecha actual: {date.today().isoformat()}."}]


def interpretar(pregunta, historial, clave, modelo):
    payload = {"model": modelo, "messages": historial + [{"role": "user", "content": pregunta}], "stream": False}
    respuesta = peticion_json(GROQ_URL, "POST", payload, {"Authorization": f"Bearer {clave}"})
    plan = json.loads(respuesta["choices"][0]["message"]["content"])
    if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
        raise ValueError("Acción inválida en la respuesta del modelo")
    return {campo: str(plan.get(campo) or "").strip() for campo in CAMPOS}


def preparar_pendiente(plan, chat_id, usuario_id, referencia=""):
    return {"solicitud_id": uuid4().hex, "chat_id": chat_id, "usuario_id": usuario_id,
            "plan": deepcopy(plan), "referencia": referencia,
            "estado": "por_confirmar", "vence_en": monotonic() + 600}


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
        return "El resumen venció. Prepara y revisa una nueva solicitud."
    return None


def teclado_pendiente(pendiente):
    identificador = pendiente["solicitud_id"]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Confirmar", callback_data=f"confirmar:{identificador}"),
        InlineKeyboardButton("Descartar", callback_data=f"descartar:{identificador}"),
    ]])


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
            return self.solicitar("/disponibilidad?" + urlencode(
                {"fecha": plan["fecha"], "servicio": plan["servicio"]}), usuario_id)
        if accion == "consultar":
            return self.consultar(plan["codigo"], usuario_id)
        raise ValueError("Lectura no admitida")

    def consultar(self, codigo, usuario_id):
        return self.solicitar("/reservas/" + quote(codigo, safe=""), usuario_id)

    def ejecutar(self, pendiente):
        plan = pendiente["plan"]
        cuerpo = {"solicitud_id": pendiente["solicitud_id"], "accion": plan["accion"],
                  "datos": {campo: plan.get(campo, "") for campo in CAMPOS if campo != "accion"},
                  "referencia": pendiente["referencia"], "confirmada": True}
        return self.solicitar("/operaciones", pendiente["usuario_id"], "POST", cuerpo)

    def estado(self, identificador, usuario_id):
        return self.solicitar("/operaciones/" + quote(identificador, safe=""), usuario_id)


def registrar_turno(context, pregunta, resultado, plan=None):
    mensajes = context.chat_data.setdefault("historial", nuevo_historial())
    mensajes.extend([{"role": "user", "content": pregunta},
                     {"role": "assistant", "content": json.dumps(
                         {"plan": plan, "resultado": resultado}, ensure_ascii=False)}])


def describir_reserva(reserva):
    return (f"Código: {reserva['codigo']}\nCliente: {reserva['cliente']}\n"
            f"Servicio: {reserva['servicio']}\nFecha: {reserva['fecha']}\n"
            f"Hora: {reserva['hora']}\nEstado: {reserva['estado']}")


def formatear_lectura(accion, datos):
    if accion == "servicios":
        return "Servicios:\n" + "\n".join(
            f"{nombre}: ${valor['precio']}, {valor['duracion_minutos']} minutos"
            for nombre, valor in datos.items())
    if accion == "disponibilidad":
        return f"{datos['servicio']} para {datos['fecha']}:\n" + (", ".join(datos["horas"]) or "Sin horarios libres")
    return describir_reserva(datos["reserva"])


async def enviar(mensaje, texto):
    for inicio in range(0, len(texto), 4000):
        await mensaje.reply_text(texto[inicio:inicio + 4000])


async def quitar_controles(context, pendiente):
    if pendiente and pendiente.get("mensaje_id"):
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=pendiente["chat_id"], message_id=pendiente["mensaje_id"], reply_markup=None)
        except TelegramError:
            logging.warning("No se retiró el teclado; la validación del servidor sigue activa")


async def iniciar(update, context):
    context.chat_data.setdefault("historial", nuevo_historial())
    await enviar(update.effective_message, "Hola. Soy el asistente del Salón Aurora. Consulta servicios o prepara una reserva. Usa /help para ver las opciones.")


async def ayuda(update, context):
    await enviar(update.effective_message, AYUDA)


async def reiniciar(update, context):
    pendiente = context.chat_data.get("pendiente")
    if pendiente and pendiente["estado"] in {"ejecutando", "incierta"}:
        await enviar(update.effective_message, "Primero verifica la operación con /estado. Conservo su referencia para evitar un reenvío accidental.")
        return
    await quitar_controles(context, pendiente)
    context.chat_data.clear()
    context.chat_data["historial"] = nuevo_historial()
    await enviar(update.effective_message, "Reinicié esta conversación y retiré su propuesta. Las reservas registradas se conservan.")


async def descartar(update, context):
    pendiente = context.chat_data.get("pendiente")
    if pendiente and pendiente["estado"] != "por_confirmar":
        await enviar(update.effective_message, "La operación necesita verificarse con /estado antes de retirar su referencia.")
        return
    await quitar_controles(context, pendiente)
    context.chat_data.pop("pendiente", None)
    registrar_turno(context, "/descartar", "La propuesta fue descartada sin ejecutar.")
    await enviar(update.effective_message, "Retiré la propuesta pendiente. Las reservas registradas se conservan.")


async def consultar_reserva(update, context):
    if len(context.args) != 1:
        await enviar(update.effective_message, "Usa /reserva CODIGO para consultar una reserva propia.")
        return
    try:
        datos = await asyncio.to_thread(context.bot_data["api"].consultar, context.args[0].upper(), update.effective_user.id)
    except FalloAPI as error:
        await enviar(update.effective_message, error.detalle)
        return
    except (URLError, TimeoutError, ValueError):
        await enviar(update.effective_message, "No pude completar la consulta a la API.")
        return
    registrar_turno(context, update.effective_message.text, datos)
    await enviar(update.effective_message, describir_reserva(datos["reserva"]))


async def recibir_texto(update, context):
    mensaje = update.effective_message
    pregunta = (mensaje.text or "").strip()
    if not pregunta:
        return
    pendiente = context.chat_data.get("pendiente")
    if pendiente and pendiente["estado"] in {"ejecutando", "incierta"}:
        await enviar(mensaje, "Hay una operación por verificar. Usa /estado o /reintentar; conservo su identificador.")
        return
    interprete = context.bot_data.get("interprete", interpretar)
    clave, modelo = context.bot_data.get("clave_modelo", ""), context.bot_data.get("modelo", "")
    if interprete is interpretar and (not clave or not modelo):
        await enviar(mensaje, "Configura GROQ_API_KEY y GROQ_MODEL en la terminal del bot.")
        return
    historial = context.chat_data.setdefault("historial", nuevo_historial())
    try:
        plan = await asyncio.to_thread(interprete, pregunta, historial, clave, modelo)
        if not isinstance(plan, dict) or plan.get("accion") not in ACCIONES:
            raise ValueError("Plan inválido")
        plan = {campo: str(plan.get(campo) or "").strip() for campo in CAMPOS}
        accion = plan["accion"]
        if accion == "fuera_de_alcance":
            texto = "Puedo ayudarte con los servicios, la disponibilidad y tus reservas."
            registrar_turno(context, pregunta, texto, plan)
            await enviar(mensaje, texto)
            return
        if accion in {"consultar", "modificar", "cancelar"}:
            conocidos = context.chat_data.get("codigos", set())
            explicito = plan["codigo"] and plan["codigo"].casefold() in pregunta.casefold()
            if not explicito and (len(conocidos) != 1 or plan["codigo"] not in conocidos):
                plan["codigo"] = ""
        if accion in ESCRITURAS and pendiente:
            if accion != pendiente["plan"]["accion"] or plan["codigo"] != pendiente["plan"]["codigo"]:
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
            texto = "Necesito: " + ", ".join(faltan)
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
        resumen = (f"Acción: {accion}\n" + "\n".join(f"{campo}: {plan[campo]}" for campo in CAMPOS[1:] if plan[campo])
                   + f"\nReferencia de solicitud: {pendiente['solicitud_id']}\nRevisa los datos y elige una opción.")
        registrar_turno(context, pregunta, "Propuesta pendiente de confirmación", plan)
        enviado = await mensaje.reply_text(resumen, reply_markup=teclado_pendiente(pendiente))
        pendiente["mensaje_id"] = enviado.message_id
    except FalloAPI as error:
        await enviar(mensaje, error.detalle)
    except HTTPError:
        await enviar(mensaje, "El proveedor del modelo rechazó la consulta. Revisa su configuración.")
    except (URLError, TimeoutError):
        await enviar(mensaje, "No pude completar la conexión. Todavía no envié una escritura de reserva.")
    except (ValueError, KeyError, IndexError, TypeError):
        await enviar(mensaje, "La respuesta no tiene el formato esperado. Revisa o completa la solicitud.")


def validar_resultado(resultado, pendiente):
    if (not isinstance(resultado, dict) or resultado.get("ok") is not True
            or resultado.get("solicitud_id") != pendiente["solicitud_id"]
            or resultado.get("accion") != pendiente["plan"]["accion"]):
        raise ValueError("Resultado de escritura inesperado")
    for campo in ("codigo", "cliente", "servicio", "fecha", "hora", "estado"):
        if not isinstance(resultado.get("reserva", {}).get(campo), str):
            raise ValueError("La respuesta no identifica la reserva")


async def resultado_registrado(context, pendiente, resultado, mensaje):
    identificador = resultado["solicitud_id"]
    actual = context.chat_data.get("pendiente")
    if actual and actual["solicitud_id"] == identificador:
        context.chat_data.pop("pendiente", None)
    plan_resultado = (pendiente["plan"] if pendiente and pendiente["solicitud_id"] == identificador
                      else {"accion": resultado.get("accion"),
                            "codigo": resultado.get("reserva", {}).get("codigo", "")})
    registrar_turno(context, f"Resultado de solicitud {identificador}", resultado, plan_resultado)
    if resultado.get("ok"):
        reserva = resultado["reserva"]
        context.chat_data.setdefault("codigos", set()).add(reserva["codigo"])
        texto = f"Resultado registrado: {resultado['accion']}.\n" + describir_reserva(reserva)
        texto += f"\nReferencia: {identificador}\nEstado actual: /reserva {reserva['codigo']}"
    else:
        texto = "La API rechazó la operación: " + resultado.get("detalle", "Revisa los datos")
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
            respuesta = {"ok": False, "solicitud_id": pendiente["solicitud_id"],
                         "accion": pendiente["plan"]["accion"], "detalle": error.detalle}
            await resultado_registrado(context, pendiente, respuesta, mensaje)
            return
        pendiente["estado"] = "incierta"
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        pendiente["estado"] = "incierta"
    else:
        await resultado_registrado(context, pendiente, resultado, mensaje)
        return
    await enviar(mensaje, "No pude verificar el resultado. Conservo la misma referencia: "
                 + pendiente["solicitud_id"] + ". Usa /estado antes de preparar otra operación.")


async def atender_decision(update, context):
    consulta = update.callback_query
    await consulta.answer()
    chat = update.effective_chat
    if chat is None or chat.type != "private" or not isinstance(consulta.data, str):
        return
    accion, identificador = consulta.data.split(":", 1)
    pendiente = context.chat_data.get("pendiente")
    motivo = motivo_rechazo(pendiente, identificador, chat.id, consulta.from_user.id, monotonic())
    if motivo:
        if (pendiente and pendiente["solicitud_id"] == identificador
                and pendiente["usuario_id"] == consulta.from_user.id
                and pendiente["estado"] == "por_confirmar" and monotonic() >= pendiente["vence_en"]):
            await quitar_controles(context, pendiente)
            context.chat_data.pop("pendiente", None)
        await context.bot.send_message(chat.id, motivo)
        return
    if accion == "descartar":
        await quitar_controles(context, pendiente)
        context.chat_data.pop("pendiente", None)
        registrar_turno(context, f"Descartar {identificador}", "La propuesta no se ejecutó", pendiente["plan"])
        await context.bot.send_message(chat.id, "Descarté la propuesta. Las reservas registradas se conservan.")
        return
    await ejecutar_confirmada(context, pendiente, consulta.message)


async def consultar_estado(update, context):
    pendiente = context.chat_data.get("pendiente")
    identificador = (context.args[0] if len(context.args) == 1 else
                     pendiente["solicitud_id"] if pendiente else context.chat_data.get("ultima_solicitud", ""))
    if not re.fullmatch(r"[0-9a-f]{32}", identificador):
        await enviar(update.effective_message, "Usa /estado REFERENCIA con la referencia del resumen.")
        return
    try:
        datos = await asyncio.to_thread(context.bot_data["api"].estado, identificador, update.effective_user.id)
        resultado = datos["resultado"]
        if resultado.get("solicitud_id") != identificador:
            raise ValueError("Referencia inesperada")
        if resultado.get("ok"):
            provisional = pendiente if pendiente and pendiente["solicitud_id"] == identificador else {
                "solicitud_id": identificador, "plan": {"accion": resultado.get("accion")}}
            validar_resultado(resultado, provisional)
    except FalloAPI as error:
        texto = ("Todavía no hay un resultado verificable. Conservo la referencia; no asumo que la escritura falló."
                 if error.estado == 404 else error.detalle)
        await enviar(update.effective_message, texto)
        return
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        await enviar(update.effective_message, "No pude verificar el estado. Conservo la referencia de la operación.")
        return
    await resultado_registrado(context, pendiente, resultado, update.effective_message)


async def reintentar(update, context):
    pendiente = context.chat_data.get("pendiente")
    if not pendiente or pendiente["estado"] != "incierta":
        await enviar(update.effective_message, "No hay una operación incierta para reenviar.")
        return
    await ejecutar_confirmada(context, pendiente, update.effective_message)


async def desconocido(update, context):
    await enviar(update.effective_message, "Comando no disponible. Usa /help para ver las opciones.")


async def otro_mensaje(update, context):
    await enviar(update.effective_message, "Envíame una consulta escrita. Por ahora atiendo mensajes de texto.")


async def informar_error(update, context):
    logging.error("Error del bot: %s", type(context.error).__name__)


def registrar_handlers(aplicacion):
    privado = filters.ChatType.PRIVATE
    aplicacion.add_handler(CallbackQueryHandler(
        atender_decision, pattern=r"^(confirmar|descartar):[0-9a-f]{32}$", block=True))
    for nombre, funcion in (("start", iniciar), ("help", ayuda), ("reset", reiniciar),
                            ("descartar", descartar), ("reserva", consultar_reserva),
                            ("estado", consultar_estado), ("reintentar", reintentar)):
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
        print("Configura el token y la clave de la API antes de iniciar.")
        return
    api = ClienteAPI(os.getenv("CHATBOT_API_URL", "http://127.0.0.1:8011"), clave_api)
    try:
        aplicacion = crear_aplicacion(token, api, os.getenv("GROQ_API_KEY", ""), os.getenv("GROQ_MODEL", ""))
        print("Bot en ejecución. Abre su chat privado. Para detenerlo: Ctrl+C.")
        aplicacion.run_polling(allowed_updates=["message", "callback_query"])
    except TelegramError as error:
        print(f"Telegram no completó el inicio: {type(error).__name__}.")


if __name__ == "__main__":
    main()
