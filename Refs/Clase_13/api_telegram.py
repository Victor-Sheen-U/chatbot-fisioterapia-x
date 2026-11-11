"""Rutas de Telegram sobre la AgendaSQLite del proyecto."""

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from threading import local
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from almacen_sqlite import AgendaSQLite, ConflictoReserva, ReservaNoEncontrada


def huella(valor):
    texto = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class DatosReserva(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cliente: str = Field(default="", max_length=120)
    servicio: str = Field(default="", max_length=100)
    fecha: str = Field(default="", max_length=10)
    hora: str = Field(default="", max_length=5)
    codigo: str = Field(default="", max_length=64)


class Operacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solicitud_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    accion: Literal["crear", "modificar", "cancelar"]
    datos: DatosReserva
    referencia: str = Field(default="", max_length=64)
    confirmada: Literal[True]


class AgendaTelegram(AgendaSQLite):
    """Reutiliza las validaciones existentes dentro de la misma transacción."""

    def __init__(self, *args, **kwargs):
        self._hilo = local()
        super().__init__(*args, **kwargs)
        with self.conexion(escritura=True) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS propietarios_telegram (
                codigo TEXT PRIMARY KEY,
                usuario_id INTEGER NOT NULL
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS operaciones_telegram (
                solicitud_id TEXT PRIMARY KEY,
                usuario_id INTEGER NOT NULL,
                huella TEXT NOT NULL,
                estado_http INTEGER NOT NULL,
                respuesta TEXT NOT NULL
            )""")

    @contextmanager
    def conexion(self, escritura=False):
        compartida = getattr(self._hilo, "conexion", None)
        if compartida is not None:
            yield compartida
        else:
            with super().conexion(escritura) as con:
                yield con

    def _propia(self, con, codigo, usuario_id):
        propietario = con.execute(
            "SELECT usuario_id FROM propietarios_telegram WHERE codigo=?", (codigo,)
        ).fetchone()
        if propietario is None or propietario["usuario_id"] != usuario_id:
            raise ReservaNoEncontrada("Reserva no disponible para este usuario")
        return self.obtener(con, codigo)

    def consultar_propia(self, codigo, usuario_id):
        with self.conexion() as con:
            reserva = self._propia(con, codigo, usuario_id)
            return {"reserva": reserva, "referencia": huella(reserva)}

    def consultar_operacion(self, solicitud_id, usuario_id):
        with self.conexion() as con:
            fila = con.execute(
                "SELECT * FROM operaciones_telegram WHERE solicitud_id=? AND usuario_id=?",
                (solicitud_id, usuario_id),
            ).fetchone()
            if fila is None:
                raise ReservaNoEncontrada("Todavía no hay un resultado registrado para esa solicitud")
            return fila["estado_http"], json.loads(fila["respuesta"])

    def operar(self, solicitud, usuario_id):
        contenido = solicitud.model_dump()
        identificador = solicitud.solicitud_id
        firma = huella(contenido)
        accion = solicitud.accion
        datos = solicitud.datos
        with self.conexion(escritura=True) as con:
            self._hilo.conexion = con
            try:
                anterior = con.execute(
                    "SELECT * FROM operaciones_telegram WHERE solicitud_id=?", (identificador,)
                ).fetchone()
                if anterior is not None:
                    if anterior["usuario_id"] != usuario_id:
                        return 404, {"ok": False, "detalle": "Solicitud no disponible"}
                    if anterior["huella"] != firma:
                        return 409, {"ok": False, "detalle": "El identificador ya pertenece a otros datos"}
                    return anterior["estado_http"], json.loads(anterior["respuesta"])

                con.execute("SAVEPOINT cambio_reserva")
                try:
                    if accion != "crear":
                        actual = self._propia(con, datos.codigo, usuario_id)
                        if not solicitud.referencia or huella(actual) != solicitud.referencia:
                            raise ConflictoReserva("La reserva cambió. Consúltala y prepara otro resumen")
                    if accion == "crear":
                        reserva = self.crear(datos.cliente, datos.servicio, datos.fecha, datos.hora)
                        con.execute(
                            "INSERT INTO propietarios_telegram VALUES (?, ?)",
                            (reserva["codigo"], usuario_id),
                        )
                    elif accion == "modificar":
                        reserva = self.modificar(datos.codigo, datos.servicio, datos.fecha, datos.hora)
                    else:
                        reserva = self.cancelar(datos.codigo)
                    estado = 201 if accion == "crear" else 200
                    respuesta = {"ok": True, "solicitud_id": identificador,
                                 "accion": accion, "reserva": reserva,
                                 "referencia": huella(reserva)}
                except (ReservaNoEncontrada, ConflictoReserva, ValueError) as error:
                    con.execute("ROLLBACK TO cambio_reserva")
                    estado = (404 if isinstance(error, ReservaNoEncontrada) else
                              409 if isinstance(error, ConflictoReserva) else 422)
                    respuesta = {"ok": False, "solicitud_id": identificador,
                                 "accion": accion, "detalle": str(error)}
                finally:
                    con.execute("RELEASE cambio_reserva")
                con.execute(
                    "INSERT INTO operaciones_telegram VALUES (?, ?, ?, ?, ?)",
                    (identificador, usuario_id, firma, estado,
                     json.dumps(respuesta, ensure_ascii=False)),
                )
                return estado, respuesta
            finally:
                self._hilo.conexion = None


def crear_router(agenda, clave):
    if not clave or len(clave) < 16 or not clave.isascii():
        raise ValueError("CHATBOT_API_KEY debe tener al menos 16 caracteres ASCII")
    router = APIRouter(prefix="/telegram", tags=["Telegram"])

    def autenticar(x_api_key: str = Header(default="")):
        if not secrets.compare_digest(clave, x_api_key):
            raise HTTPException(401, "Acceso del servicio no autorizado")

    def identidad(x_telegram_user: int = Header(...), _=Depends(autenticar)):
        if x_telegram_user <= 0:
            raise HTTPException(422, "Identificador de usuario inválido")
        return x_telegram_user

    def leer(funcion, *args):
        try:
            return funcion(*args)
        except ReservaNoEncontrada as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except sqlite3.OperationalError as error:
            raise HTTPException(503, "El almacenamiento no está disponible") from error

    @router.get("/servicios", dependencies=[Depends(autenticar)])
    def servicios():
        return agenda.servicios

    @router.get("/disponibilidad", dependencies=[Depends(autenticar)])
    def disponibilidad(fecha: str, servicio: str):
        return leer(agenda.disponibilidad, fecha, servicio)

    @router.get("/reservas/{codigo}")
    def consultar(codigo: str, usuario_id: int = Depends(identidad)):
        return leer(agenda.consultar_propia, codigo, usuario_id)

    @router.post("/operaciones")
    def operar(solicitud: Operacion, usuario_id: int = Depends(identidad)):
        try:
            estado, contenido = agenda.operar(solicitud, usuario_id)
        except sqlite3.OperationalError as error:
            raise HTTPException(503, "No se obtuvo un resultado verificable; consulta el estado") from error
        return JSONResponse(status_code=estado, content=contenido)

    @router.get("/operaciones/{solicitud_id}")
    def estado(solicitud_id: str, usuario_id: int = Depends(identidad)):
        codigo, contenido = leer(agenda.consultar_operacion, solicitud_id, usuario_id)
        return {"estado_http": codigo, "resultado": contenido}

    return router
