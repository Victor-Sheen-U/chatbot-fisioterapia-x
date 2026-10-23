# VLFisioterapia · Centro Integral de Fisioterapia y Rehabilitación

## 1. Identificación del proyecto

- **Nombre del proyecto:** VLFisioterapia · Centro Integral de Fisioterapia y Rehabilitación (Armenia, Quindío — datos ficticios).
- **Propósito:** Asistente conversacional para una clínica de fisioterapia que permite a los pacientes consultar tratamientos, tarifas y disponibilidad por especialista, así como agendar, consultar, reprogramar y cancelar citas médicas en varios turnos de conversación con confirmación explícita y persistencia relacional en SQLite.
- **Curso y periodo:** Electiva 2 (Creación de Chatbots) · Periodo EAM-2026II · Entrega del Segundo Corte.
- **Equipo:** `Equipo_Sheen_castaneda_vargas`
  - **Victor Sheen Arias Zuleta** — Cabecilla / Arquitecto (integración con Groq, memoria conversacional, diseño de `AgendaSQLite` y orquestación en Gradio).
  - **Valentín Castañeda Marín** — Observadora / QA (diseño de casos de prueba multi-turno, validación de cruces de agenda por profesional, concurrencia y documentación de evidencias).
  - **Samuel Rojas Vargas** — Mano Derecha / Backend Lead (implementación de endpoints transaccionales en FastAPI, modelos Pydantic v2, normalización de servicios y suite de pruebas).

---

## 2. Qué hace el sistema, límites y arquitectura

### Capacidades y límites
- **Qué hace:** Informa el catálogo de 6 servicios de fisioterapia (con duraciones de 45 o 60 minutos y precios en COP), calcula la disponibilidad real por fisioterapeuta (`mariana`, `carlos`, `valeria`) según el horario semanal, y ejecuta el ciclo completo de reservas (crear, consultar, modificar/reprogramar y cancelar) exigiendo confirmación explícita antes de cualquier cambio en la base de datos.
- **Límites del asistente:** No emite diagnósticos clínicos, no prescribe medicamentos ni atiende urgencias médicas hospitalarias vitales; ante consultas fuera del dominio responde con el mensaje `fuera_de_alcance` o deriva a recepción humana (`/escalar`).

### Diagrama de arquitectura en texto

```text
+-------------------------------------------------------------------------+
| 1. INTERFAZ WEB CONVERSACIONAL — Gradio 6 (app_gradio.py, puerto 7860)  |
|    • Estado aislado por sesión de navegador con gr.State(nuevo_estado)  |
|    • Botones: Enviar | Confirmar operación | Descartar | Reiniciar      |
+------------------------------------+------------------------------------+
                                     |
                                     | enviar(mensaje, estado)
                                     v
+-------------------------------------------------------------------------+
| 2. MEMORIA Y CLIENTE LLM — Python (chatbot_memoria.py + consulta_llm.py)|
|    • Acumula historial [system, user, assistant] por sesión             |
|    • Envía POST a https://api.groq.com/openai/v1/chat/completions       |
|    • Extrae el plan JSON: {accion, cliente, servicio, fecha, hora, ...} |
|    • Retiene acciones de escritura en pendiente hasta confirmar=True    |
+------------------------------------+------------------------------------+
                                     |
                                     | Petición HTTP REST (urllib)
                                     v
+-------------------------------------------------------------------------+
| 3. API DEL NEGOCIO — FastAPI + Pydantic v2 (main.py, puerto 8012)       |
|    • GET /servicios, GET /disponibilidad, POST /citas,                  |
|      GET /citas/{codigo}, PATCH /citas/{codigo}/reprogramar,            |
|      DELETE /citas/{codigo}?confirmado=true                             |
|    • Traduce errores del dominio a HTTP 400, 404, 409, 422 y 503        |
+------------------------------------+------------------------------------+
                                     |
                                     | AgendaSQLite (almacen_sqlite.py)
                                     v
+-------------------------------------------------------------------------+
| 4. PERSISTENCIA RELACIONAL — SQLite (reservas.db + clinica.json)        |
|    • Tabla `reservas` (16 columnas) + transacciones `BEGIN IMMEDIATE`   |
|    • Valida horarios por día, duración (45/60 min) y cruces por fisio   |
+-------------------------------------------------------------------------+
```

---

## 3. Estructura del repositorio

Todos los comandos de preparación, pruebas, servidor FastAPI e interfaz Gradio **se ejecutan desde la carpeta raíz del repositorio**.

```text
chatbot-fisioterapia/
├── README.md                        # Guía de instalación, configuración, ejecución y verificación
├── requirements.txt                 # Dependencias de Python (FastAPI, Uvicorn, Gradio 6, Httpx, Pydantic, Tzdata)
├── .gitignore                       # Exclusión de entorno virtual, caché, respaldos y archivo .env
├── .env.example                     # Plantilla de variables de entorno (sin credenciales reales)
├── main.py                          # Servidor FastAPI con endpoints del negocio y validación Pydantic
├── app_gradio.py                    # Interfaz web en Gradio 6 con estado por sesión y botones de control
├── consulta_llm.py                  # Cliente HTTP hacia Groq y ejecutor de planes contra FastAPI
├── chatbot_memoria.py               # Gestión del historial multi-turno [system, user, assistant]
├── almacen_sqlite.py                # Clase AgendaSQLite: persistencia, disponibilidad y cruces en SQLite
├── clinica.json                     # Catálogo del negocio (6 servicios, 3 fisioterapeutas, horarios y FAQ)
├── reservas.db                      # Base de datos SQLite con 5 reservas ficticias de prueba
├── preparar_datos_prueba.py         # Script idempotente para crear o reiniciar las reservas ficticias
├── probar_fisioterapia.py           # Suite de pruebas automáticas con TestClient y SQLite temporal
├── test_integracion_completa.py     # Script de prueba de integración extremo a extremo con Groq real
└── docs/
    ├── Bitacora_Segundo_Corte.md    # Documentación técnica integral del Segundo Corte
    ├── Presentacion_Segundo_Corte.pdf # Presentación ejecutiva y técnica del proyecto
    ├── bitacoras_previas/           # Bitácoras de seguimiento de las sesiones C01 a C04
    └── evidencias/                  # Salidas reales de pruebas (.txt) y capturas de pantalla (.png)
```

---

## 4. Requisitos e instalación

- **Versión de Python verificada:** Python `3.13.9` (compatible con **Python 3.11 o superior**, requerido por `gradio>=6,<7` y `zoneinfo`).
- **Dependencias (`requirements.txt`):** `fastapi==0.115.12`, `uvicorn==0.34.2`, `httpx==0.28.1`, `tzdata>=2025.2`, `pydantic>=2.10.0`, `gradio>=6,<7`.

### Opción A: Linux / macOS (bash)

```bash
# 1. Ubicarse en la raíz del repositorio
cd chatbot-fisioterapia

# 2. Crear y activar el entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar las dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

### Opción B: Windows (PowerShell)

```powershell
# 1. Ubicarse en la raíz del repositorio
cd chatbot-fisioterapia

# 2. Crear y activar el entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instalar las dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Configuración de variables de entorno

El sistema lee las variables desde el entorno o desde un archivo `.env` en la raíz (cargado automáticamente por `cargar_env()` en [`consulta_llm.py`](consulta_llm.py)).

> **Advertencia de seguridad:** Nunca publiques tu archivo `.env` ni expongas tu clave `GROQ_API_KEY` en repositorios públicos, capturas de pantalla o documentos. El archivo `.gitignore` ya excluye `.env`.

| Variable | Valor por defecto / Ejemplo | Descripción |
|---|---|---|
| `GROQ_API_KEY` | *(obligatoria para el chat)* | Clave de API obtenida en [console.groq.com](https://console.groq.com). |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Identificador del modelo de lenguaje en Groq. |
| `CHATBOT_API_URL` | `http://127.0.0.1:8012` | Dirección base donde escucha la API de FastAPI. |
| `PORT` / `HOST` | `8012` / `127.0.0.1` | Opcionales al ejecutar `python main.py` directamente. |

### Crear el archivo `.env`

**Linux / macOS (bash):**
```bash
cp .env.example .env
# Edita .env y reemplaza tu_clave_de_groq_aqui por tu clave real de Groq
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
# Abre .env en el bloc de notas o editor y coloca tu clave real en GROQ_API_KEY
```

También puedes exportar las variables directamente en la terminal antes de iniciar `app_gradio.py` (ver sección siguiente).

---

## 6. Preparación de datos y ejecución

### Paso 1: Preparar o reiniciar los datos ficticios en SQLite (`reservas.db`)

El repositorio incluye `reservas.db` con **5 reservas ficticias** (`Paciente Demo 1` a `Paciente Demo 5`) en días hábiles futuros: incluye reservas activas el mismo día a la misma hora con distintas fisioterapeutas (`mariana` y `valeria` a las `09:00`) y **1 reserva cancelada** (`Paciente Demo 3`).

Para verificar o regenerar desde cero los datos de prueba:

**Linux / macOS (bash):**
```bash
# Siembra idempotente (no duplica si ya existen)
./.venv/bin/python preparar_datos_prueba.py

# Para limpiar la tabla y volver al estado inicial de 5 reservas ficticias:
./.venv/bin/python preparar_datos_prueba.py --reiniciar
```

**Windows (PowerShell):**
```powershell
# Siembra idempotente
.\.venv\Scripts\python.exe preparar_datos_prueba.py

# Reiniciar la base de datos a las 5 reservas ficticias iniciales:
.\.venv\Scripts\python.exe preparar_datos_prueba.py --reiniciar
```

### Paso 2: Iniciar la API del negocio (Terminal 1)

Deja esta terminal abierta ejecutando FastAPI en el puerto **8012**:

**Linux / macOS (bash):**
```bash
source .venv/bin/activate
python -m uvicorn main:app --reload --port 8012
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8012
```

- Documentación interactiva (Swagger UI): `http://127.0.0.1:8012/docs`

### Paso 3: Iniciar la interfaz conversacional en Gradio (Terminal 2)

Abre una **segunda terminal** en la raíz del proyecto:

**Linux / macOS (bash):**
```bash
source .venv/bin/activate
export GROQ_API_KEY="tu_clave_de_groq_aqui"
export GROQ_MODEL="openai/gpt-oss-120b"
export CHATBOT_API_URL="http://127.0.0.1:8012"
python app_gradio.py
```
*(Si ya configuraste `.env`, `consulta_llm.py` carga el archivo automáticamente, pero `app_gradio.py` lee `GROQ_API_KEY` y `GROQ_MODEL` de `os.getenv` al importarse tras importar `consulta_llm`.)*

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
$env:GROQ_API_KEY="tu_clave_de_groq_aqui"
$env:GROQ_MODEL="openai/gpt-oss-120b"
$env:CHATBOT_API_URL="http://127.0.0.1:8012"
python app_gradio.py
```

- Interfaz web del chatbot en Gradio: `http://127.0.0.1:7860`

---

## 7. Comprobación del funcionamiento

### 7.1 Prueba rápida de la API (`GET /servicios`)

Con FastAPI encendida en el puerto `8012`, ejecuta en otra terminal:

```bash
curl http://127.0.0.1:8012/servicios
```

**Resultado esperado:** Un objeto JSON con las **6 claves de tratamientos** (`evaluacion`, `deportiva`, `traumatologica`, `puncion_seca`, `postural`, `neurologica`), incluyendo `nombre`, `precio_cop`, `duracion_minutos` (60 o 45) y `descripcion`.

### 7.2 Ejecución de la suite de pruebas automáticas

No requiere clave de Groq ni servidor encendido (utiliza `TestClient` de FastAPI y una base SQLite temporal que no altera `reservas.db`):

```bash
python probar_fisioterapia.py
```

**Salida real esperada:**
```text
Iniciando pruebas de VLFisioterapia...
Todas las pruebas pasaron satisfactoriamente (100% OK).
```

### 7.3 Recorrido corto en Gradio y verificación en SQLite

1. Abre `http://127.0.0.1:7860`.
2. **Turno 1:** Escribe `"Hola, me llamo Laura Gómez y quiero una cita de fisioterapia deportiva"` y pulsa **Enviar**. El asistente recordará tu nombre y servicio y te pedirá la fecha y la hora.
3. **Turno 2:** Escribe `"Para el 2026-10-28 a las 10:00"` y pulsa **Enviar**. El asistente mostrará el resumen (`Voy a crear la cita: servicio=deportiva, paciente=Laura Gómez... ¿Confirmas la operación?`).
4. **Confirmación:** Haz clic en el botón **Confirmar operación**. FastAPI creará la cita y devolverá el código `VF-...`.
5. **Verificar la fila guardada en SQLite:**

```bash
python -c "import sqlite3; con=sqlite3.connect('reservas.db'); print(con.execute('SELECT codigo, cliente, servicio, fecha, hora, estado, fisioterapeuta_asignado FROM reservas ORDER BY creada_en DESC LIMIT 5').fetchall())"
```

---

## 8. Errores frecuentes y solución

| Síntoma / Mensaje de error | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named '_sqlite3'` | El intérprete de Python con el que se creó el entorno virtual fue compilado desde código fuente sin las cabeceras de desarrollo de SQLite. | En Fedora Linux: instala `sudo dnf install sqlite-devel` y recompila/reinstala ese Python (p. ej. con `pyenv` o `asdf`), o crea el `.venv` usando el Python del sistema (`/usr/bin/python3 -m venv .venv`). |
| `ERROR: [Errno 98] Address already in use` (puerto 8012 o 7860) | Ya hay otra instancia de Uvicorn o Gradio ejecutándose en ese puerto. | Detén el proceso anterior (`pkill -f "uvicorn main:app"` o cierra la terminal previa) o cambia el puerto actualizando también `CHATBOT_API_URL`. |
| `Configura GROQ_API_KEY y GROQ_MODEL e inicia de nuevo.` | Las variables `GROQ_API_KEY` o `GROQ_MODEL` están vacías en `.env` y no fueron exportadas en la terminal antes de iniciar `app_gradio.py`. | Completa `.env` con valores válidos (sin dejar vacíos) o expórtalas en la terminal y reinicia `python app_gradio.py`. |
| `Error HTTP 401. Revisa Groq o FastAPI.` / `Error HTTP 429` | En `401`: la clave `GROQ_API_KEY` es inválida o expiró. En `429`: se alcanzó el límite de peticiones por minuto de la cuenta de Groq. | Verifica tu clave en la consola de Groq o espera unos segundos antes de enviar otro turno. |
| `No pude conectar con Groq o FastAPI.` | El servidor FastAPI (`main.py`) está apagado, escucha en un puerto distinto a `CHATBOT_API_URL`, o no hay salida a internet hacia `api.groq.com`. | Confirma que la Terminal 1 tenga `uvicorn main:app --port 8012` activo y que `CHATBOT_API_URL=http://127.0.0.1:8012`. |
| `TypeError: Chatbot.__init__() got an unexpected keyword argument 'buttons'` | Se instaló una versión antigua de Gradio (Gradio 4 o 5) en lugar de Gradio 6. | Ejecuta `pip install "gradio>=6,<7"` dentro del entorno virtual activo. |

---

## 9. Documentación y evidencias del Segundo Corte

Todos los documentos describen la misma versión del sistema (FastAPI en puerto `8012`, Gradio en puerto `7860` y persistencia en `reservas.db`):

- **Bitácora integral del Segundo Corte:** [`docs/Bitacora_Segundo_Corte.md`](docs/Bitacora_Segundo_Corte.md)
- **Presentación del Segundo Corte (PDF):** [`docs/Presentacion_Segundo_Corte.pdf`](docs/Presentacion_Segundo_Corte.pdf)
- **Carpeta de evidencias (pruebas `.txt` y capturas `.png`):** [`docs/evidencias/`](docs/evidencias/)
  - [`01_api_servicios_y_disponibilidad.txt`](docs/evidencias/01_api_servicios_y_disponibilidad.txt)
  - [`02_crear_modificar_cancelar.txt`](docs/evidencias/02_crear_modificar_cancelar.txt)
  - [`03_intervalo_ocupado_409.txt`](docs/evidencias/03_intervalo_ocupado_409.txt)
  - [`04_cancelacion_y_persistencia.txt`](docs/evidencias/04_cancelacion_y_persistencia.txt)
  - [`05_pruebas_automaticas_antes.txt`](docs/evidencias/05_pruebas_automaticas_antes.txt) y [`05b_pruebas_automaticas_despues.txt`](docs/evidencias/05b_pruebas_automaticas_despues.txt)
  - [`06_errores_controlados.txt`](docs/evidencias/06_errores_controlados.txt)
  - [`07_sesiones_y_reinicio_simulado.txt`](docs/evidencias/07_sesiones_y_reinicio_simulado.txt)
- **Bitácoras previas de seguimiento por clase:** [`docs/bitacoras_previas/`](docs/bitacoras_previas/)
  - [`C01_2026-08-31_Fisioterapia.md`](docs/bitacoras_previas/C01_2026-08-31_Fisioterapia.md)
  - [`C02_2026-09-07_Fisioterapia.md`](docs/bitacoras_previas/C02_2026-09-07_Fisioterapia.md)
  - [`C03_2026-09-28_Fisioterapia.md`](docs/bitacoras_previas/C03_2026-09-28_Fisioterapia.md)
  - [`C04_2026-10-18_Fisioterapia.md`](docs/bitacoras_previas/C04_2026-10-18_Fisioterapia.md)

---

## 10. Limitaciones conocidas

1. **Parche global de resolución IPv4 en `consulta_llm.py`:** Se reemplaza `socket.getaddrinfo` a nivel de proceso para forzar `socket.AF_INET` (IPv4) y evitar demoras de >20 segundos o bloqueos HTTP 403 frente a Cloudflare al conectar con `api.groq.com` desde entornos Linux sin enrutamiento IPv6.
2. **Historial conversacional solo en memoria de sesión (`gr.State`):** El historial de mensajes `[system, user, assistant]` vive en la sesión del navegador de Gradio y no se guarda en SQLite; cerrar la pestaña o pulsar *Reiniciar conversación* limpia el diálogo (aunque las citas confirmadas en `reservas.db` se conservan intactas).
3. **Crecimiento lineal del historial en conversaciones largas:** `interpretar_turno()` envía la lista completa de mensajes de la sesión a Groq en cada turno; no se ha implementado aún truncamiento por ventana deslizante.
4. **Coexistencia del endpoint `/chat` heredado de Flowise:** En `main.py` se conserva la ruta `POST /chat` (que usa el diccionario en memoria `SESIONES` y confirmación mediante la palabra `CONFIRMAR`) por compatibilidad con la suite de pruebas del primer corte, mientras que la interfaz principal del segundo corte (`app_gradio.py`) gestiona la sesión en `gr.State` y confirma mediante el botón **Confirmar operación**.
5. **Dependencia externa de Groq y pruebas de LLM manuales:** La interpretación de lenguaje natural depende de la disponibilidad de `api.groq.com`, de una clave válida en `.env` y del modelo configurado (`openai/gpt-oss-120b`). Para no consumir cuota ni escribir en la base real durante pruebas de regresión, `probar_fisioterapia.py` prueba determinísticamente la API y SQLite, mientras que las pruebas conversacionales con Groq se ejecutan de forma separada.
