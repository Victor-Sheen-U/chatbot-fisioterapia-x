"""Reservas SQLite para una agenda. Cada operación utiliza su propia conexión."""

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


class ConflictoReserva(ValueError):
    pass


class ReservaNoEncontrada(ValueError):
    pass


class CitaCancelada(ValueError):
    pass


def minutos(hora):
    if not isinstance(hora, str) or not re.fullmatch(r"\d{2}:\d{2}", hora):
        raise ValueError("Usa una hora HH:MM")
    horas, minutos_hora = map(int, hora.split(":"))
    if not 0 <= horas <= 23 or not 0 <= minutos_hora <= 59:
        raise ValueError("Hora inválida")
    return horas * 60 + minutos_hora


def texto_hora(valor):
    return f"{valor // 60:02d}:{valor % 60:02d}"


ALIAS_SERVICIOS = {
    "corte": "evaluacion",
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
    if not isinstance(clave_servicio, str):
        return ""
    clave = (
        clave_servicio.strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    return ALIAS_SERVICIOS.get(clave, clave)


class AgendaSQLite:
    def __init__(
        self,
        ruta,
        servicios,
        apertura="09:00",
        cierre="18:00",
        dias=(0, 1, 2, 3, 4, 5),
        paso=30,
        horarios=None,
        profesionales=None,
        zona=None,
    ):
        self.ruta = Path(ruta).resolve()
        self.servicios = servicios
        self.apertura, self.cierre = minutos(apertura), minutos(cierre)
        self.dias, self.paso = tuple(dias), paso
        self.horarios = horarios
        self.profesionales = profesionales
        if isinstance(zona, str):
            self.zona = ZoneInfo(zona)
        elif isinstance(zona, ZoneInfo):
            self.zona = zona
        else:
            self.zona = None

        if self.apertura >= self.cierre or not isinstance(paso, int) or paso <= 0:
            raise ValueError("Revisa el horario y el paso de la agenda")

        with self.conexion(escritura=True) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS reservas (
                codigo TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                servicio TEXT NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                duracion_minutos INTEGER NOT NULL CHECK (duracion_minutos > 0),
                estado TEXT NOT NULL CHECK (estado IN ('activa', 'cancelada', 'reprogramada')),
                fisioterapeuta TEXT,
                fisioterapeuta_asignado TEXT NOT NULL DEFAULT '',
                telefono TEXT,
                motivo_consulta TEXT,
                precio_cop INTEGER NOT NULL DEFAULT 0,
                creada_en TEXT NOT NULL DEFAULT '',
                cancelada_en TEXT,
                reprogramada_en TEXT,
                historial_reprogramaciones TEXT NOT NULL DEFAULT '[]'
            )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_fecha_estado ON reservas(fecha, estado)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_fisio_fecha ON reservas(fisioterapeuta_asignado, fecha, estado)")

            # Asegurar compatibilidad si la tabla fue creada previamente con menos columnas
            columnas = {fila["name"] for fila in con.execute("PRAGMA table_info(reservas)").fetchall()}
            columnas_extra = [
                ("fisioterapeuta", "TEXT"),
                ("fisioterapeuta_asignado", "TEXT NOT NULL DEFAULT ''"),
                ("telefono", "TEXT"),
                ("motivo_consulta", "TEXT"),
                ("precio_cop", "INTEGER NOT NULL DEFAULT 0"),
                ("creada_en", "TEXT NOT NULL DEFAULT ''"),
                ("cancelada_en", "TEXT"),
                ("reprogramada_en", "TEXT"),
                ("historial_reprogramaciones", "TEXT NOT NULL DEFAULT '[]'"),
            ]
            for col_nombre, col_tipo in columnas_extra:
                if col_nombre not in columnas:
                    con.execute(f"ALTER TABLE reservas ADD COLUMN {col_nombre} {col_tipo}")

    @classmethod
    def desde_negocio(cls, ruta, negocio_dict):
        if isinstance(negocio_dict, (str, Path)):
            negocio_dict = json.loads(Path(negocio_dict).read_text(encoding="utf-8-sig"))
        servicios = negocio_dict.get("servicios", {})
        horarios = negocio_dict.get("horarios")
        profesionales = negocio_dict.get("fisioterapeutas")
        paso = negocio_dict.get("paso_minutos", 30)
        zona_str = negocio_dict.get("zona_horaria")
        zona = ZoneInfo(zona_str) if zona_str else None
        return cls(
            ruta=ruta,
            servicios=servicios,
            horarios=horarios,
            profesionales=profesionales,
            zona=zona,
            paso=paso,
        )

    @contextmanager
    def conexion(self, escritura=False):
        con = sqlite3.connect(self.ruta, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            if escritura:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if escritura:
                con.commit()
        except Exception:
            if escritura:
                con.rollback()
            raise
        finally:
            con.close()

    def duracion(self, servicio):
        srv = self.servicios.get(servicio)
        if not srv:
            clave_norm = normalizar_clave_servicio(servicio)
            srv = self.servicios.get(clave_norm)
        if not srv:
            opciones = ", ".join(self.servicios.keys())
            raise ValueError(f"Servicio no reconocido. Tratamientos válidos: {opciones}")
        valor = srv.get("duracion_minutos")
        if type(valor) is not int or valor <= 0:
            raise ValueError("El catálogo debe indicar duracion_minutos como entero positivo")
        return valor

    def obtener_ahora(self):
        return datetime.now(self.zona) if self.zona else datetime.now()

    def validar_fecha(self, fecha, permitir_pasado=False):
        try:
            valor = date.fromisoformat(fecha)
        except Exception as err:
            raise ValueError("Usa fecha AAAA-MM-DD") from err
        if valor.isoformat() != fecha:
            raise ValueError("Usa fecha AAAA-MM-DD")
        ahora = self.obtener_ahora()
        if not permitir_pasado and valor < ahora.date():
            raise ValueError("La fecha seleccionada ya pasó. Seleccione una fecha futura.")
        if self.horarios is not None:
            if str(valor.weekday()) not in self.horarios:
                raise ValueError("El negocio está cerrado ese día")
        else:
            if valor.weekday() not in self.dias:
                raise ValueError("El negocio está cerrado ese día")
        return valor

    def validar_intervalo(self, fecha, hora, duracion, permitir_pasado=False):
        fecha_valida = self.validar_fecha(fecha, permitir_pasado)
        inicio = minutos(hora)
        if self.horarios is not None:
            horario_dia = self.horarios.get(str(fecha_valida.weekday()))
            if not horario_dia:
                raise ValueError("El negocio está cerrado ese día")
            apertura = minutos(horario_dia[0])
            cierre = minutos(horario_dia[1])
        else:
            apertura = self.apertura
            cierre = self.cierre

        if inicio < apertura or inicio + duracion > cierre:
            raise ValueError("La atención debe terminar dentro del horario del negocio")
        if (inicio - apertura) % self.paso:
            raise ValueError(f"Selecciona una hora en pasos de {self.paso} minutos")

        if not permitir_pasado:
            ahora = self.obtener_ahora()
            if fecha_valida == ahora.date():
                hora_slot = time(inicio // 60, inicio % 60)
                dt_slot = datetime.combine(fecha_valida, hora_slot, self.zona) if self.zona else datetime.combine(fecha_valida, hora_slot)
                if dt_slot <= ahora:
                    raise ValueError("El horario seleccionado ya pasó")

        return inicio

    def ocupado(self, con, fecha, inicio, duracion, fisioterapeuta=None, excluir=""):
        if fisioterapeuta:
            filas = con.execute(
                "SELECT hora, duracion_minutos FROM reservas WHERE fecha=? AND estado='activa' AND codigo<>? AND fisioterapeuta_asignado=?",
                (fecha, excluir, fisioterapeuta),
            ).fetchall()
        else:
            filas = con.execute(
                "SELECT hora, duracion_minutos FROM reservas WHERE fecha=? AND estado='activa' AND codigo<>?",
                (fecha, excluir),
            ).fetchall()
        return any(
            inicio < minutos(fila["hora"]) + fila["duracion_minutos"]
            and inicio + duracion > minutos(fila["hora"])
            for fila in filas
        )

    def disponibilidad(self, fecha, servicio, fisioterapeuta=None, excluir=""):
        try:
            fecha_valida = date.fromisoformat(fecha)
        except Exception as err:
            raise ValueError("Usa fecha AAAA-MM-DD") from err
        if fecha_valida.isoformat() != fecha:
            raise ValueError("Usa fecha AAAA-MM-DD")
        ahora = self.obtener_ahora()
        if fecha_valida < ahora.date():
            raise ValueError("La fecha seleccionada ya pasó. Seleccione una fecha futura.")

        clave_srv = normalizar_clave_servicio(servicio)
        duracion = self.duracion(clave_srv)

        dia_semana = str(fecha_valida.weekday())
        if self.horarios is not None:
            horario_dia = self.horarios.get(dia_semana)
            if not horario_dia:
                return {
                    "fecha": fecha,
                    "servicio": clave_srv,
                    "fisioterapeuta": fisioterapeuta or "cualquiera",
                    "duracion_minutos": duracion,
                    "horarios_disponibles": [],
                    "horas": [],
                }
            apertura = minutos(horario_dia[0])
            cierre = minutos(horario_dia[1])
        else:
            if fecha_valida.weekday() not in self.dias:
                return {
                    "fecha": fecha,
                    "servicio": clave_srv,
                    "fisioterapeuta": fisioterapeuta or "cualquiera",
                    "duracion_minutos": duracion,
                    "horarios_disponibles": [],
                    "horas": [],
                }
            apertura = self.apertura
            cierre = self.cierre

        if fisioterapeuta:
            fisio_key = fisioterapeuta.strip().lower()
            if self.profesionales:
                if fisio_key not in self.profesionales:
                    validos = ", ".join(self.profesionales.keys())
                    raise ValueError(f"Fisioterapeuta '{fisioterapeuta}' no encontrado. Disponibles: {validos}")
                if clave_srv not in self.profesionales[fisio_key].get("servicios_asignados", []):
                    nombre = self.profesionales[fisio_key]["nombre"]
                    srv_nom = self.servicios.get(clave_srv, {}).get("nombre", clave_srv)
                    raise ValueError(f"{nombre} no atiende el servicio '{srv_nom}'.")
            candidatos = [fisio_key]
        elif self.profesionales:
            candidatos = [
                k for k, v in self.profesionales.items()
                if clave_srv in v.get("servicios_asignados", [])
            ]
        else:
            candidatos = [None]

        slots_libres = set()
        with self.conexion() as con:
            for inicio in range(apertura, cierre - duracion + 1, self.paso):
                if fecha_valida == ahora.date():
                    hora_slot = time(inicio // 60, inicio % 60)
                    dt_slot = datetime.combine(fecha_valida, hora_slot, self.zona) if self.zona else datetime.combine(fecha_valida, hora_slot)
                    if dt_slot <= ahora:
                        continue

                for cand in candidatos:
                    if not self.ocupado(con, fecha, inicio, duracion, fisioterapeuta=cand, excluir=excluir):
                        slots_libres.add(texto_hora(inicio))
                        break

        horas = sorted(list(slots_libres))
        return {
            "fecha": fecha,
            "servicio": clave_srv,
            "fisioterapeuta": fisioterapeuta or "cualquiera",
            "duracion_minutos": duracion,
            "horarios_disponibles": horas,
            "horas": horas,
        }

    def _formatear_fila(self, fila):
        if fila is None:
            return None
        d = dict(fila)
        hist = d.get("historial_reprogramaciones")
        if isinstance(hist, str):
            try:
                d["historial_reprogramaciones"] = json.loads(hist)
            except Exception:
                d["historial_reprogramaciones"] = []
        elif hist is None:
            d["historial_reprogramaciones"] = []
        return d

    def listar(self):
        with self.conexion() as con:
            filas = con.execute("SELECT * FROM reservas ORDER BY fecha, hora, codigo").fetchall()
            return [self._formatear_fila(fila) for fila in filas]

    def obtener(self, con, codigo):
        cod = str(codigo).strip().upper()
        fila = con.execute("SELECT * FROM reservas WHERE UPPER(codigo)=?", (cod,)).fetchone()
        if fila is None:
            raise ReservaNoEncontrada(f"No se encontró ninguna cita con el código {cod}.")
        return self._formatear_fila(fila)

    def consultar(self, codigo):
        with self.conexion() as con:
            return self.obtener(con, codigo)

    def crear(self, cliente, servicio, fecha, hora, fisioterapeuta=None, telefono=None, motivo_consulta=None):
        if not isinstance(cliente, str) or len(cliente.strip()) < 2:
            raise ValueError("Indica el nombre del cliente")
        clave_srv = normalizar_clave_servicio(servicio)
        duracion = self.duracion(clave_srv)
        inicio = self.validar_intervalo(fecha, hora, duracion)

        srv_info = self.servicios.get(clave_srv, {})
        precio_cop = srv_info.get("precio_cop", 0)

        with self.conexion(escritura=True) as con:
            if self.profesionales:
                if fisioterapeuta:
                    fisio_key = fisioterapeuta.strip().lower()
                    if fisio_key not in self.profesionales:
                        validos = ", ".join(self.profesionales.keys())
                        raise ValueError(f"Fisioterapeuta '{fisioterapeuta}' no encontrado. Disponibles: {validos}")
                    if clave_srv not in self.profesionales[fisio_key].get("servicios_asignados", []):
                        nombre = self.profesionales[fisio_key]["nombre"]
                        srv_nombre = srv_info.get("nombre", clave_srv)
                        raise ValueError(f"{nombre} no atiende el servicio '{srv_nombre}'.")
                    if self.ocupado(con, fecha, inicio, duracion, fisioterapeuta=fisio_key):
                        raise ConflictoReserva("El horario o profesional seleccionado no está disponible en esa fecha y hora.")
                    fisio_asignado = fisio_key
                else:
                    fisio_asignado = None
                    for k, v in self.profesionales.items():
                        if clave_srv in v.get("servicios_asignados", []):
                            if not self.ocupado(con, fecha, inicio, duracion, fisioterapeuta=k):
                                fisio_asignado = k
                                break
                    if not fisio_asignado:
                        raise ConflictoReserva("El horario o profesional seleccionado no está disponible en esa fecha y hora.")
            else:
                if self.ocupado(con, fecha, inicio, duracion):
                    raise ConflictoReserva("El intervalo solicitado se cruza con una reserva activa")
                fisio_asignado = ""

            codigo = "VF-" + uuid4().hex[:10].upper() if self.profesionales else uuid4().hex[:8].upper()
            ahora_iso = self.obtener_ahora().isoformat()

            con.execute(
                """INSERT INTO reservas (
                    codigo, cliente, servicio, fecha, hora, duracion_minutos, estado,
                    fisioterapeuta, fisioterapeuta_asignado, telefono, motivo_consulta,
                    precio_cop, creada_en, cancelada_en, reprogramada_en, historial_reprogramaciones
                ) VALUES (
                    :codigo, :cliente, :servicio, :fecha, :hora, :duracion_minutos, :estado,
                    :fisioterapeuta, :fisioterapeuta_asignado, :telefono, :motivo_consulta,
                    :precio_cop, :creada_en, :cancelada_en, :reprogramada_en, :historial_reprogramaciones
                )""",
                {
                    "codigo": codigo,
                    "cliente": cliente.strip(),
                    "servicio": clave_srv,
                    "fecha": fecha,
                    "hora": hora,
                    "duracion_minutos": duracion,
                    "estado": "activa",
                    "fisioterapeuta": fisioterapeuta or (fisio_asignado if fisio_asignado else None),
                    "fisioterapeuta_asignado": fisio_asignado,
                    "telefono": telefono,
                    "motivo_consulta": motivo_consulta,
                    "precio_cop": precio_cop,
                    "creada_en": ahora_iso,
                    "cancelada_en": None,
                    "reprogramada_en": None,
                    "historial_reprogramaciones": "[]",
                },
            )
            return self.obtener(con, codigo)

    def modificar(self, codigo, *args, **kwargs):
        servicio = kwargs.get("servicio")
        fecha = kwargs.get("fecha") or kwargs.get("nueva_fecha")
        hora = kwargs.get("hora") or kwargs.get("nueva_hora")
        fisioterapeuta = kwargs.get("fisioterapeuta")

        if args:
            if len(args) == 3:
                servicio, fecha, hora = args
            elif len(args) == 2:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(args[0])):
                    fecha, hora = args
                else:
                    servicio, fecha = args
            elif len(args) == 1:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(args[0])):
                    fecha = args[0]
                else:
                    servicio = args[0]

        cod = str(codigo).strip().upper()
        with self.conexion(escritura=True) as con:
            actual = self.obtener(con, cod)
            if actual["estado"] == "cancelada":
                raise CitaCancelada("No se puede reprogramar una cita cancelada.")
            if actual["estado"] != "activa":
                raise ConflictoReserva("La reserva ya no está activa")

            if servicio is None:
                clave_srv = actual["servicio"]
                duracion = actual["duracion_minutos"]
            else:
                clave_srv = normalizar_clave_servicio(servicio)
                duracion = self.duracion(clave_srv)

            nueva_fecha = fecha or actual["fecha"]
            nueva_hora = hora or actual["hora"]
            fisio = fisioterapeuta or actual.get("fisioterapeuta_asignado") or actual.get("fisioterapeuta")

            inicio = self.validar_intervalo(nueva_fecha, nueva_hora, duracion)

            fisio_actual = actual.get("fisioterapeuta_asignado") or actual.get("fisioterapeuta")
            if nueva_fecha == actual["fecha"] and nueva_hora == actual["hora"] and (fisio is None or fisio == fisio_actual):
                raise ConflictoReserva(f"La nueva fecha {nueva_fecha} a las {nueva_hora} no está disponible.")

            if self.profesionales and fisio:
                fisio_key = fisio.strip().lower()
                if fisio_key not in self.profesionales:
                    raise ValueError(f"Fisioterapeuta '{fisio}' no encontrado.")
                if clave_srv not in self.profesionales[fisio_key].get("servicios_asignados", []):
                    nombre = self.profesionales[fisio_key]["nombre"]
                    srv_nombre = self.servicios.get(clave_srv, {}).get("nombre", clave_srv)
                    raise ValueError(f"{nombre} no atiende el servicio '{srv_nombre}'.")
                if self.ocupado(con, nueva_fecha, inicio, duracion, fisioterapeuta=fisio_key, excluir=cod):
                    raise ConflictoReserva(f"La nueva fecha {nueva_fecha} a las {nueva_hora} no está disponible.")
                fisio_asig = fisio_key
            else:
                if self.ocupado(con, nueva_fecha, inicio, duracion, excluir=cod):
                    raise ConflictoReserva(f"La nueva fecha {nueva_fecha} a las {nueva_hora} no está disponible.")
                fisio_asig = ""

            historial = actual.get("historial_reprogramaciones", [])
            if isinstance(historial, str):
                historial = json.loads(historial)
            ahora_iso = self.obtener_ahora().isoformat()
            historial.append({
                "fecha_anterior": actual["fecha"],
                "hora_anterior": actual["hora"],
                "modificada_en": ahora_iso,
            })

            con.execute(
                """UPDATE reservas SET
                    servicio = :servicio,
                    fecha = :fecha,
                    hora = :hora,
                    duracion_minutos = :duracion_minutos,
                    fisioterapeuta = :fisioterapeuta,
                    fisioterapeuta_asignado = :fisioterapeuta_asignado,
                    reprogramada_en = :reprogramada_en,
                    historial_reprogramaciones = :historial_reprogramaciones
                WHERE codigo = :codigo""",
                {
                    "codigo": cod,
                    "servicio": clave_srv,
                    "fecha": nueva_fecha,
                    "hora": nueva_hora,
                    "duracion_minutos": duracion,
                    "fisioterapeuta": fisioterapeuta or (fisio_asig if fisio_asig else None),
                    "fisioterapeuta_asignado": fisio_asig,
                    "reprogramada_en": ahora_iso,
                    "historial_reprogramaciones": json.dumps(historial, ensure_ascii=False),
                },
            )
            return self.obtener(con, cod)

    def cancelar(self, codigo):
        cod = str(codigo).strip().upper()
        with self.conexion(escritura=True) as con:
            actual = self.obtener(con, cod)
            if actual["estado"] == "activa":
                ahora_iso = self.obtener_ahora().isoformat()
                con.execute(
                    "UPDATE reservas SET estado='cancelada', cancelada_en=? WHERE codigo=?",
                    (ahora_iso, cod),
                )
                return self.obtener(con, cod)
            return actual

    def importar_json(self, ruta):
        registros = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
        if isinstance(registros, dict):
            registros = registros.get("reservas") or registros.get("citas")
        if not isinstance(registros, list):
            raise ValueError("Adapta el JSON a una lista de reservas o a {'reservas': [...]}")
        nuevos = existentes = 0
        with self.conexion(escritura=True) as con:
            for registro in registros:
                if not isinstance(registro, dict):
                    raise ValueError("Cada reserva debe ser un objeto")
                for campo_req in ("codigo", "cliente", "servicio", "fecha", "hora", "estado"):
                    if campo_req not in registro:
                        raise ValueError(f"Adapta el campo que falta: {campo_req}")
                    if not isinstance(registro[campo_req], str) or not registro[campo_req].strip():
                        raise ValueError(f"El campo '{campo_req}' debe ser un texto no vacío")

                codigo = registro["codigo"].strip().upper()
                cliente = registro["cliente"].strip()
                servicio = registro["servicio"].strip()
                fecha_str = registro["fecha"].strip()
                hora = registro["hora"].strip()
                estado = registro["estado"].strip()

                if estado not in {"activa", "cancelada"}:
                    raise ValueError("Adapta el estado a activa o cancelada")

                try:
                    fecha_obj = date.fromisoformat(fecha_str)
                    if fecha_obj.isoformat() != fecha_str:
                        raise ValueError()
                except Exception as err:
                    raise ValueError("Fecha inválida en el JSON") from err

                duracion = registro.get("duracion_minutos")
                if duracion is None:
                    duracion = self.duracion(servicio)
                if type(duracion) is not int or duracion <= 0:
                    raise ValueError("Duración inválida en el JSON")

                inicio = minutos(hora)
                if inicio + duracion > 24 * 60:
                    raise ValueError("La reserva histórica termina fuera del día")

                fisio = registro.get("fisioterapeuta")
                fisio_asig = registro.get("fisioterapeuta_asignado") or fisio or ""
                telefono = registro.get("telefono")
                motivo = registro.get("motivo_consulta")
                precio = registro.get("precio_cop")
                if precio is None:
                    precio = self.servicios.get(servicio, {}).get("precio_cop", 0)
                creada_en = registro.get("creada_en") or self.obtener_ahora().isoformat()
                cancelada_en = registro.get("cancelada_en")
                reprogramada_en = registro.get("reprogramada_en")
                historial = registro.get("historial_reprogramaciones", [])
                historial_str = json.dumps(historial, ensure_ascii=False) if isinstance(historial, list) else str(historial)

                previa = con.execute("SELECT * FROM reservas WHERE codigo=?", (codigo,)).fetchone()
                if previa is not None:
                    prev_d = dict(previa)
                    prev_hist = json.loads(prev_d.get("historial_reprogramaciones") or "[]")
                    cur_hist = json.loads(historial_str)
                    es_igual = (
                        prev_d["codigo"] == codigo
                        and prev_d["cliente"] == cliente
                        and prev_d["servicio"] == servicio
                        and prev_d["fecha"] == fecha_str
                        and prev_d["hora"] == hora
                        and prev_d["duracion_minutos"] == duracion
                        and prev_d["estado"] == estado
                        and (prev_d.get("fisioterapeuta_asignado") or "") == fisio_asig
                        and prev_hist == cur_hist
                    )
                    if not es_igual:
                        raise ConflictoReserva("El código ya existe con datos distintos; revisa la migración")
                    existentes += 1
                    continue

                if estado == "activa" and self.ocupado(con, fecha_str, inicio, duracion, fisioterapeuta=fisio_asig or None):
                    raise ConflictoReserva("El JSON contiene un intervalo activo que se cruza con otro")

                con.execute(
                    """INSERT INTO reservas (
                        codigo, cliente, servicio, fecha, hora, duracion_minutos, estado,
                        fisioterapeuta, fisioterapeuta_asignado, telefono, motivo_consulta,
                        precio_cop, creada_en, cancelada_en, reprogramada_en, historial_reprogramaciones
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        codigo,
                        cliente,
                        servicio,
                        fecha_str,
                        hora,
                        duracion,
                        estado,
                        fisio,
                        fisio_asig,
                        telefono,
                        motivo,
                        precio,
                        creada_en,
                        cancelada_en,
                        reprogramada_en,
                        historial_str,
                    ),
                )
                nuevos += 1

        return {"importadas": nuevos, "ya_existentes": existentes}


if __name__ == "__main__":
    import argparse
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Importar reservas JSON a SQLite")
    parser.add_argument("--migrar", required=True, type=Path)
    parser.add_argument("--negocio", type=Path, default=base / "clinica.json" if (base / "clinica.json").exists() else base / "negocio.json")
    parser.add_argument("--base", type=Path, default=base / "reservas.db")
    args = parser.parse_args()
    negocio_dict = json.loads(args.negocio.read_text(encoding="utf-8-sig"))
    agenda = AgendaSQLite.desde_negocio(args.base, negocio_dict)
    try:
        print(json.dumps(agenda.importar_json(args.migrar), ensure_ascii=False, indent=2))
    except ValueError as error:
        parser.exit(1, f"Migración detenida: {error}\n")
