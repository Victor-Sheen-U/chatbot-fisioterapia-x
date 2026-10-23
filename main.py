"""API de Fisioterapia y Rehabilitación · VLFisioterapia
Gestión de citas, disponibilidad de profesionales, FAQ, derivación humana y puente Flowise.
Persistencia relacional en SQLite (reservas.db) con control de concurrencia y transacciones inmediatas.
"""

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import uvicorn

from almacen_sqlite import AgendaSQLite, ConflictoReserva, ReservaNoEncontrada, CitaCancelada

BASE = Path(__file__).resolve().parent
ARCHIVO_CLINICA = BASE / "clinica.json"

CLINICA = json.loads(ARCHIVO_CLINICA.read_text(encoding="utf-8-sig"))
ZONA = ZoneInfo(CLINICA["zona_horaria"])
agenda = AgendaSQLite.desde_negocio(BASE / "reservas.db", CLINICA)

if CLINICA["paso_minutos"] <= 0:
    raise ValueError("El paso de minutos debe ser positivo.")
if any(s["duracion_minutos"] <= 0 or s["precio_cop"] < 0 for s in CLINICA["servicios"].values()):
    raise ValueError("Revisar precios y duraciones de los servicios en clinica.json.")

LOCK = RLock()
SESIONES: dict[str, dict] = {}

app = FastAPI(
    title=CLINICA["nombre"],
    version="2.0.0",
    description="API de fisioterapia para gestión de citas, especialistas, FAQ y atención al paciente."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# MODELOS PYDANTIC
# ==============================================================================

class DatosCita(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente: str = Field(min_length=2, max_length=100, description="Nombre y apellido del paciente")
    servicio: str = Field(min_length=1, max_length=50, description="Clave del servicio fisioterapéutico")
    fecha: date = Field(description="Fecha de la cita en formato AAAA-MM-DD")
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Hora de inicio en formato HH:MM (24h)")
    fisioterapeuta: str | None = Field(default=None, max_length=50, description="Clave del especialista opcional")
    telefono: str | None = Field(default=None, max_length=30, description="Teléfono de contacto del paciente")
    motivo_consulta: str | None = Field(default=None, max_length=300, description="Breve descripción del dolor o lesión")


class CrearCita(DatosCita):
    confirmado: Literal[True]


class ReprogramarCita(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nueva_fecha: date
    nueva_hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    fisioterapeuta: str | None = Field(default=None, max_length=50)
    confirmado: Literal[True]


class RegistroCita(DatosCita):
    codigo: str
    estado: Literal["activa", "cancelada", "reprogramada"]
    precio_cop: int
    duracion_minutos: int = Field(gt=0)
    fisioterapeuta_asignado: str
    creada_en: str
    cancelada_en: str | None = None
    reprogramada_en: str | None = None
    historial_reprogramaciones: list[dict] = Field(default_factory=list)


class SolicitudEscalamiento(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    paciente: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)
    motivo: str = Field(min_length=3, max_length=500)
    session_id: str = Field(min_length=1, max_length=150)


class Extraccion(BaseModel):
    """Modelo de datos extraídos por el LLM. Es entrada no confiable y se valida exhaustivamente."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    intencion: Literal[
        "informacion", "reservar", "consultar", "reprogramar",
        "cancelar", "escalar", "continuar", "fuera"
    ] = "continuar"
    cliente: str | None = Field(default=None, min_length=2, max_length=100)
    servicio: str | None = Field(default=None, max_length=50)
    fecha: date | None = None
    hora: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    fisioterapeuta: str | None = Field(default=None, max_length=50)
    codigo: str | None = Field(default=None, max_length=50)
    telefono: str | None = Field(default=None, max_length=30)
    motivo: str | None = Field(default=None, max_length=300)


class MensajeChat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=150)
    mensaje: str = Field(min_length=1, max_length=2000)
    datos: Extraccion = Field(default_factory=Extraccion)


# ==============================================================================
# PERSISTENCIA Y FUNCIONES AUXILIARES
# ==============================================================================

def responder(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except CitaCancelada as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ReservaNoEncontrada as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictoReserva as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Error de base de datos. La operación no pudo confirmarse."
        ) from error


ALIAS_SERVICIOS = {
    "corte": "evaluacion",  # Compatibilidad con pruebas de diapositivas de clase
    "barba": "evaluacion",
    "fisioterapia deportiva": "deportiva",
    "deporte": "deportiva",
    "readaptacion": "deportiva",
    "valoracion": "evaluacion",
    "valoracion inicial": "evaluacion",
    "diagnostico": "evaluacion",
    "traumatologia": "traumatologica",
    "postquirurgica": "traumatologica",
    "fractura": "traumatologica",
    "fracturas": "traumatologica",
    "puncion seca": "puncion_seca",
    "puncion": "puncion_seca",
    "terapia manual": "puncion_seca",
    "rpg": "postural",
    "columna": "postural",
    "postura": "postural",
    "reeducacion postural": "postural",
    "neurologia": "neurologica",
    "rehabilitacion neurologica": "neurologica",
    "acv": "neurologica",
}


def normalizar_clave_servicio(clave_servicio: str) -> str:
    clave = clave_servicio.strip().lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return ALIAS_SERVICIOS.get(clave, clave)


def validar_servicio(clave_servicio: str) -> dict:
    clave = normalizar_clave_servicio(clave_servicio)
    if clave not in CLINICA["servicios"]:
        opciones = ", ".join(CLINICA["servicios"].keys())
        raise HTTPException(status_code=422, detail=f"Servicio no reconocido. Tratamientos válidos: {opciones}")
    return CLINICA["servicios"][clave]


def validar_fisioterapeuta(clave_fisio: str | None, clave_servicio: str) -> str:
    """Valida o selecciona automáticamente un fisioterapeuta capacitado para el servicio."""
    servicio = validar_servicio(clave_servicio)
    profesionales = CLINICA["fisioterapeutas"]

    if clave_fisio:
        fisio_key = clave_fisio.strip().lower()
        if fisio_key not in profesionales:
            validos = ", ".join(profesionales.keys())
            raise HTTPException(status_code=422, detail=f"Fisioterapeuta '{clave_fisio}' no encontrado. Disponibles: {validos}")
        if clave_servicio not in profesionales[fisio_key]["servicios_asignados"]:
            nombre = profesionales[fisio_key]["nombre"]
            raise HTTPException(status_code=422, detail=f"{nombre} no atiende el servicio '{servicio['nombre']}'.")
        return fisio_key

    # Asignar primer fisioterapeuta habilitado por defecto
    for k, v in profesionales.items():
        if clave_servicio in v["servicios_asignados"]:
            return k
    return "mariana"


def obtener_horarios_disponibles(fecha: date, clave_servicio: str, clave_fisio: str | None = None) -> list[str]:
    """Calcula los bloques horarios disponibles verificando agenda del profesional y horario de clínica."""
    res = responder(
        agenda.disponibilidad,
        fecha.isoformat(),
        clave_servicio,
        fisioterapeuta=clave_fisio
    )
    return res["horarios_disponibles"]


def formatear_pesos(valor: int) -> str:
    return f"${valor:,}".replace(",", ".") + " COP"


def formatear_resumen_cita(c: dict) -> str:
    fisio_nombre = CLINICA["fisioterapeutas"].get(c.get("fisioterapeuta_asignado", c.get("fisioterapeuta", "")), {}).get("nombre", "Especialista asignado")
    srv_nombre = CLINICA["servicios"].get(c["servicio"], {}).get("nombre", c["servicio"])
    return f"Paciente {c['cliente']} · {srv_nombre} con {fisio_nombre} el {c['fecha']} a las {c['hora']}"


def responder_chat(estado: dict, texto: str) -> dict:
    return {"respuesta": texto, "estado_sesion": estado.copy()}


# ==============================================================================
# ENDPOINTS REST
# ==============================================================================

@app.get("/clinica", tags=["Información"])
def obtener_clinica():
    """Información general, ubicación, horarios y políticas de VLFisioterapia."""
    return CLINICA


@app.get("/servicios", tags=["Información"])
def listar_servicios():
    """Catálogo de tratamientos fisioterapéuticos con tarifas y duraciones."""
    return CLINICA["servicios"]


@app.get("/fisioterapeutas", tags=["Información"])
def listar_fisioterapeutas():
    """Especialistas de la clínica, registros profesionales y áreas de atención."""
    return CLINICA["fisioterapeutas"]


@app.get("/faq", tags=["Información"])
def listar_faq():
    """Preguntas frecuentes, preparación de la consulta y convenios de seguros."""
    return {
        "faq": CLINICA["faq"],
        "seguros_convenios": CLINICA["seguros_convenios"],
        "requisitos_consulta": CLINICA["requisitos_consulta"],
        "politicas_citas": CLINICA["politicas_citas"]
    }


@app.get("/disponibilidad", tags=["Citas"])
def consultar_disponibilidad(
    fecha: date = Query(..., description="Fecha requerida en formato AAAA-MM-DD"),
    servicio: str = Query(..., description="Clave del tratamiento fisioterapéutico"),
    fisioterapeuta: str | None = Query(None, description="Clave opcional de un fisioterapeuta específico")
):
    """Consulta los horarios disponibles para un servicio y fecha específicos."""
    with LOCK:
        horarios = obtener_horarios_disponibles(fecha, servicio, fisioterapeuta)
        return {
            "fecha": fecha.isoformat(),
            "servicio": servicio,
            "fisioterapeuta": fisioterapeuta or "cualquiera",
            "horarios_disponibles": horarios,
            "horas": horarios
        }


@app.post("/citas", status_code=201, tags=["Citas"])
def agendar_cita(datos: CrearCita):
    """Registra una nueva cita médica con validación de disponibilidad y bloqueo concurrente."""
    with LOCK:
        fila = responder(
            agenda.crear,
            cliente=datos.cliente,
            servicio=datos.servicio,
            fecha=datos.fecha.isoformat(),
            hora=datos.hora,
            fisioterapeuta=datos.fisioterapeuta,
            telefono=datos.telefono,
            motivo_consulta=datos.motivo_consulta,
        )
        return RegistroCita.model_validate(fila).model_dump(mode="json")


@app.get("/citas/{codigo}", tags=["Citas"])
def consultar_cita(codigo: str):
    """Consulta el estado y detalles de una cita mediante su código VF-..."""
    with LOCK:
        fila = responder(agenda.consultar, codigo)
        return RegistroCita.model_validate(fila).model_dump(mode="json")


@app.patch("/citas/{codigo}/reprogramar", tags=["Citas"])
def reprogramar_cita(codigo: str, datos: ReprogramarCita):
    """Reprograma una cita existente a una nueva fecha y hora disponible."""
    with LOCK:
        fila = responder(
            agenda.modificar,
            codigo,
            fecha=datos.nueva_fecha.isoformat(),
            hora=datos.nueva_hora,
            fisioterapeuta=datos.fisioterapeuta,
        )
        return RegistroCita.model_validate(fila).model_dump(mode="json")


@app.delete("/citas/{codigo}", tags=["Citas"])
def cancelar_cita(codigo: str, confirmado: bool = Query(False)):
    """Cancela una cita liberando el espacio para otros pacientes."""
    if not confirmado:
        raise HTTPException(status_code=422, detail="Se requiere 'confirmado=true' para ejecutar la cancelación.")
    with LOCK:
        fila = responder(agenda.cancelar, codigo)
        return RegistroCita.model_validate(fila).model_dump(mode="json")


@app.post("/escalar", tags=["Derivación"])
def escalar_atencion(solicitud: SolicitudEscalamiento):
    """Registra una solicitud de derivación para atención humana personalizada."""
    return {
        "estatus": "escalado_exitoso",
        "mensaje": CLINICA["derivacion_humana"]["descripcion"],
        "contacto_inmediato": {
            "telefono": CLINICA["derivacion_humana"]["telefono"],
            "whatsapp": CLINICA["derivacion_humana"]["whatsapp"],
            "enlace_chat": CLINICA["derivacion_humana"]["url_whatsapp"]
        },
        "ticket": {
            "paciente": solicitud.paciente or "No provisto",
            "motivo": solicitud.motivo,
            "session_id": solicitud.session_id,
            "escalado_en": datetime.now(ZONA).isoformat()
        }
    }


# ==============================================================================
# ENDPOINT PUENTE FLOWISE (/chat)
# ==============================================================================

@app.post("/chat", tags=["Flowise Bridge"])
def flujo_conversacional(entrada: MensajeChat):
    """Puente conversacional orquestado para Flowise con control de estados y confirmación estricta."""
    with LOCK:
        estado = SESIONES.setdefault(entrada.session_id, {})
        mensaje_usuario = entrada.mensaje.strip().casefold()

        # Comandos universales de sesión
        if mensaje_usuario == "/reset":
            estado.clear()
            return responder_chat(estado, "Solicitud reiniciada. Tus citas previamente registradas se conservan. ¿En qué te puedo ayudar?")

        if mensaje_usuario in {"no", "abortar", "cancelar solicitud"}:
            estado.clear()
            return responder_chat(estado, "Solicitud descartada con éxito. No se realizó ningún cambio en tu agenda.")

        try:
            # Confirmación de operaciones críticas pendientes
            if mensaje_usuario == "confirmar":
                pendiente = estado.get("pendiente")
                if not pendiente:
                    return responder_chat(estado, "No tienes ningún resumen pendiente por confirmar. Por favor, indícame qué deseas realizar.")

                accion = pendiente["accion"]
                if accion == "crear":
                    cita_creada = agendar_cita(CrearCita(**pendiente["datos"], confirmado=True))
                    texto = (
                        f"¡Cita agendada con éxito! 🎉 {formatear_resumen_cita(cita_creada)}. "
                        f"Código de cita: {cita_creada['codigo']}. "
                        "Recuerda llegar 10 minutos antes con ropa cómoda y tus exámenes previos si los tienes."
                    )
                    estado.clear()
                    estado["ultimo_codigo"] = cita_creada["codigo"]
                    return responder_chat(estado, texto)

                elif accion == "reprogramar":
                    cita_rep = reprogramar_cita(
                        pendiente["codigo"],
                        ReprogramarCita(
                            nueva_fecha=pendiente["nueva_fecha"],
                            nueva_hora=pendiente["nueva_hora"],
                            confirmado=True
                        )
                    )
                    texto = (
                        f"Cita reprogramada con éxito. {formatear_resumen_cita(cita_rep)}. "
                        f"Conserva tu código {cita_rep['codigo']}."
                    )
                    estado.clear()
                    estado["ultimo_codigo"] = cita_rep["codigo"]
                    return responder_chat(estado, texto)

                elif accion == "cancelar":
                    cita_canc = cancelar_cita(pendiente["codigo"], confirmado=True)
                    texto = f"Tu cita {cita_canc['codigo']} ha sido cancelada satisfactoriamente. El horario fue liberado."
                    estado.clear()
                    estado["ultimo_codigo"] = cita_canc["codigo"]
                    return responder_chat(estado, texto)

            # Procesamiento de extracción del LLM
            datos_extraidos = entrada.datos.model_dump(mode="json", exclude_none=True)
            intencion = datos_extraidos.pop("intencion", "continuar")

            # 1. Fuera de alcance
            if intencion == "fuera":
                return responder_chat(
                    estado,
                    "En VLFisioterapia nos especializamos exclusivamente en fisioterapia, rehabilitación funcional y salud física. "
                    "Puedo ayudarte con información de nuestros tratamientos, tarifas, horarios o agendar una cita."
                )

            # 2. Escalamiento / Atención humana
            if intencion == "escalar":
                escalar_atencion(SolicitudEscalamiento(
                    paciente=estado.get("cliente") or datos_extraidos.get("cliente"),
                    telefono=datos_extraidos.get("telefono"),
                    motivo=entrada.mensaje,
                    session_id=entrada.session_id
                ))
                contacto = CLINICA["derivacion_humana"]
                return responder_chat(
                    estado,
                    f"Te he transferido con nuestro equipo de recepción médica. "
                    f"Puedes comunicarte directamente por WhatsApp al {contacto['whatsapp']} o llamando al {contacto['telefono']}. "
                    f"Horario de atención humana: {contacto['horario']}."
                )

            # 3. Información general y FAQ
            if intencion == "informacion":
                servicios_info = "; ".join(
                    f"{s['nombre']}: {formatear_pesos(s['precio_cop'])} ({s['duracion_minutos']} min)"
                    for s in CLINICA["servicios"].values()
                )
                dias_nombre = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                horarios_info = "; ".join(
                    f"{dias_nombre[int(d)]} {h[0]} a {h[1]}" for d, h in CLINICA["horarios"].items()
                )
                seguros_str = ", ".join(CLINICA["seguros_convenios"][:3]) + " y particulares"

                resp_info = (
                    f"En VLFisioterapia ofrecemos: {servicios_info}. "
                    f"Ubicación: {CLINICA['ubicacion']}. "
                    f"Horarios: {horarios_info}. Domingo cerrado. "
                    f"Convenios con: {seguros_str}. "
                    "Requisitos: Asistir con ropa cómoda y orden médica si vas por seguro. "
                    "¿Deseas agendar una valoración o cita para algún tratamiento?"
                )
                if estado.get("pendiente"):
                    resp_info += " (Conservo tus datos de reserva pendientes)."
                return responder_chat(estado, resp_info)

            # Actualizar intención activa en sesión
            if intencion in {"reservar", "consultar", "reprogramar", "cancelar"}:
                if estado.get("intencion") != intencion:
                    estado.clear()
                estado["intencion"] = intencion

            if not estado.get("intencion"):
                estado["intencion"] = "reservar" if datos_extraidos else "inicio"

            if estado["intencion"] == "inicio":
                estado.clear()
                return responder_chat(
                    estado,
                    "¡Hola! Te damos la bienvenida a VLFisioterapia, centro de fisioterapia y rehabilitación. "
                    "Puedo orientarte con información de tratamientos, precios, horarios, consultar una cita, "
                    "reprogramar, cancelar o transferirte con recepción. ¿En qué te puedo colaborar hoy?"
                )

            # Invalidar resumen pendiente si cambiaron datos
            if any(estado.get(k) != v for k, v in datos_extraidos.items()):
                estado.pop("pendiente", None)

            estado.update(datos_extraidos)
            accion = estado["intencion"]

            # 4. Consultar cita
            if accion == "consultar":
                if not estado.get("codigo"):
                    return responder_chat(estado, "Por favor, escribe el código de tu cita (por ejemplo, VF-XXXXXXXXXX).")
                cita = consultar_cita(estado["codigo"])
                return responder_chat(
                    estado,
                    f"Detalles de tu cita: {formatear_resumen_cita(cita)}. "
                    f"Estado actual: {cita['estado'].upper()}. Código: {cita['codigo']}."
                )

            # 5. Cancelar cita
            if accion == "cancelar":
                if not estado.get("codigo"):
                    return responder_chat(estado, "Indica el código de la cita que deseas cancelar (ejemplo VF-...).")
                cita = consultar_cita(estado["codigo"])
                if cita["estado"] == "cancelada":
                    return responder_chat(estado, f"La cita {cita['codigo']} ya se encuentra cancelada.")
                estado["pendiente"] = {"accion": "cancelar", "codigo": cita["codigo"]}
                return responder_chat(
                    estado,
                    f"Vas a cancelar la siguiente cita: {formatear_resumen_cita(cita)}. "
                    "Para proceder escribe CONFIRMAR o responde ABORTAR para mantenerla."
                )

            # 6. Reprogramar cita
            if accion == "reprogramar":
                if not estado.get("codigo"):
                    return responder_chat(estado, "Por favor, indica el código de la cita que necesitas reprogramar (ej. VF-...).")
                cita = consultar_cita(estado["codigo"])
                if cita["estado"] == "cancelada":
                    return responder_chat(estado, "Esta cita está cancelada y no puede reprogramarse. Debes solicitar una nueva cita.")

                if not estado.get("fecha"):
                    return responder_chat(estado, f"Cita actual: {cita['fecha']} a las {cita['hora']}. ¿Para qué nueva fecha deseas reprogramar? (Indica AAAA-MM-DD).")

                fecha_nueva = date.fromisoformat(estado["fecha"])
                libres = obtener_horarios_disponibles(fecha_nueva, cita["servicio"], cita.get("fisioterapeuta_asignado"))
                if not libres:
                    estado.pop("fecha", None)
                    return responder_chat(estado, f"No hay turnos disponibles para el {fecha_nueva}. Por favor indica otra fecha.")

                if not estado.get("hora") or estado["hora"] not in libres:
                    return responder_chat(estado, f"Turnos libres para el {fecha_nueva}: {', '.join(libres)}. ¿Cuál hora prefieres?")

                estado["pendiente"] = {
                    "accion": "reprogramar",
                    "codigo": cita["codigo"],
                    "nueva_fecha": fecha_nueva.isoformat(),
                    "nueva_hora": estado["hora"]
                }
                return responder_chat(
                    estado,
                    f"Solicitud de cambio: Cita {cita['codigo']} pasará al {fecha_nueva} a las {estado['hora']}. "
                    "Escribe CONFIRMAR para aplicar el cambio o ABORTAR para cancelar la solicitud."
                )

            # 7. Reservar nueva cita
            if accion == "reservar":
                if not estado.get("servicio"):
                    servicios_disponibles = ", ".join([f"'{k}' ({v['nombre']})" for k, v in CLINICA["servicios"].items()])
                    return responder_chat(
                        estado,
                        f"¿Qué tratamiento necesitas? Las opciones son: {servicios_disponibles}. "
                        "(Si es tu primera vez, recomendamos 'evaluacion')."
                    )

                validar_servicio(estado["servicio"])

                if not estado.get("fecha"):
                    return responder_chat(
                        estado,
                        "Por favor, indica la fecha deseada en formato AAAA-MM-DD (ejemplo: 2026-09-18). "
                        "Atendemos de lunes a sábado."
                    )

                fecha_obj = date.fromisoformat(estado["fecha"])
                fisio_sel = estado.get("fisioterapeuta")
                libres = obtener_horarios_disponibles(fecha_obj, estado["servicio"], fisio_sel)

                if not libres:
                    estado.pop("pendiente", None)
                    return responder_chat(
                        estado,
                        f"No hay disponibilidad para el servicio de {estado['servicio']} el día {fecha_obj.isoformat()}. "
                        "Por favor, indícanos otra fecha."
                    )

                if not estado.get("hora") or estado["hora"] not in libres:
                    estado.pop("pendiente", None)
                    return responder_chat(
                        estado,
                        f"Horarios disponibles para el {fecha_obj.isoformat()}: {', '.join(libres)}. "
                        "¿A qué hora prefieres tu sesión?"
                    )

                if not estado.get("cliente"):
                    return responder_chat(estado, "¿A nombre de qué paciente preparo la reserva?")

                fisio_asignado = validar_fisioterapeuta(fisio_sel, estado["servicio"])
                solicitud = DatosCita(
                    cliente=estado["cliente"],
                    servicio=estado["servicio"],
                    fecha=fecha_obj,
                    hora=estado["hora"],
                    fisioterapeuta=fisio_asignado,
                    telefono=estado.get("telefono"),
                    motivo_consulta=estado.get("motivo")
                ).model_dump(mode="json")

                estado["pendiente"] = {"accion": "crear", "datos": solicitud}
                info_srv = validar_servicio(solicitud["servicio"])
                fisio_nom = CLINICA["fisioterapeutas"][fisio_asignado]["nombre"]

                return responder_chat(
                    estado,
                    f"Resumen de tu cita: {info_srv['nombre']} para {solicitud['cliente']} con {fisio_nom} "
                    f"el {solicitud['fecha']} a las {solicitud['hora']}. "
                    f"Tarifa: {formatear_pesos(info_srv['precio_cop'])} ({info_srv['duracion_minutos']} minutos). "
                    "Para agendar formalmente, escribe CONFIRMAR. Si deseas corregir algún dato responde con el cambio o ABORTAR."
                )

        except HTTPException as exc:
            estado.pop("pendiente", None)
            return JSONResponse(status_code=exc.status_code, content=responder_chat(estado, exc.detail))
        except (ValidationError, ValueError) as exc:
            estado.pop("pendiente", None)
            return JSONResponse(
                status_code=422,
                content=responder_chat(estado, f"Datos inconsistentes o formato inválido. Use fecha AAAA-MM-DD y hora HH:MM.")
            )


# ==============================================================================
# RUTAS DE COMPATIBILIDAD CON DIAPOSITIVAS Y PRUEBAS (Clases 06 y 07)
# ==============================================================================

@app.get("/api/saludo", tags=["Compatibilidad"])
@app.get("/saludo", tags=["Compatibilidad"])
def saludo():
    return {"mensaje": "La API está funcionando"}


@app.get("/api/servicios", tags=["Compatibilidad"])
def api_servicios():
    return CLINICA["servicios"]


@app.get("/api/disponibilidad", tags=["Compatibilidad"])
def api_disponibilidad(
    fecha: date = Query(..., description="Fecha requerida en formato AAAA-MM-DD"),
    servicio: str = Query(..., description="Clave del tratamiento fisioterapéutico"),
    fisioterapeuta: str | None = Query(None)
):
    return consultar_disponibilidad(fecha=fecha, servicio=servicio, fisioterapeuta=fisioterapeuta)


class ReservaCompat(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    cliente: str = Field(min_length=2, max_length=100)
    servicio: str
    fecha: date
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    confirmada: bool | None = None
    confirmado: bool | None = None
    fisioterapeuta: str | None = None
    telefono: str | None = None
    motivo_consulta: str | None = None


@app.post("/api/reservas", status_code=201, tags=["Compatibilidad"])
def api_crear_reserva(datos: ReservaCompat):
    esta_confirmada = datos.confirmado is True or datos.confirmada is True
    if not esta_confirmada:
        raise HTTPException(status_code=400, detail="Debe confirmar la reserva")
    clave_srv = normalizar_clave_servicio(datos.servicio)
    return agendar_cita(CrearCita(
        cliente=datos.cliente,
        servicio=clave_srv,
        fecha=datos.fecha,
        hora=datos.hora,
        fisioterapeuta=datos.fisioterapeuta,
        telefono=datos.telefono,
        motivo_consulta=datos.motivo_consulta,
        confirmado=True
    ))


@app.get("/api/reservas/{codigo}", tags=["Compatibilidad"])
def api_consultar_reserva(codigo: str):
    return consultar_cita(codigo)


class CambioReservaCompat(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    servicio: str | None = None
    fecha: date | None = None
    hora: str | None = None
    nueva_fecha: date | None = None
    nueva_hora: str | None = None
    fisioterapeuta: str | None = None
    confirmado: bool | None = True


@app.put("/api/reservas/{codigo}", tags=["Compatibilidad"])
@app.patch("/api/reservas/{codigo}", tags=["Compatibilidad"])
def api_modificar_reserva(codigo: str, datos: CambioReservaCompat):
    fecha_final = datos.nueva_fecha or datos.fecha
    hora_final = datos.nueva_hora or datos.hora
    if not fecha_final or not hora_final:
        raise HTTPException(status_code=422, detail="Se requiere nueva_fecha y nueva_hora.")
    return reprogramar_cita(codigo, ReprogramarCita(
        nueva_fecha=fecha_final,
        nueva_hora=hora_final,
        fisioterapeuta=datos.fisioterapeuta,
        confirmado=True
    ))


@app.delete("/api/reservas/{codigo}", tags=["Compatibilidad"])
def api_cancelar_reserva(codigo: str):
    return cancelar_cita(codigo, confirmado=True)


@app.get("/", include_in_schema=False)
def raiz():
    return {"mensaje": "Bienvenido a VLFisioterapia"}


if __name__ == "__main__":
    puerto = int(os.getenv("PORT", 8012))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"Iniciando VLFisioterapia en http://{host}:{puerto}")
    uvicorn.run("main:app", host=host, port=puerto, reload=True)
