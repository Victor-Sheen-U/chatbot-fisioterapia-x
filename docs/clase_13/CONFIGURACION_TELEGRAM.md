# Manual de Configuración y Puesta en Marcha · Canal Telegram (VLFisioterapia)

Este documento detalla **únicamente los pasos manuales** que el usuario debe realizar con sus propias cuentas, credenciales y terminal local de Linux (Fedora/Ubuntu/Debian con Bash).

> [!CAUTION] Reglas de Seguridad con Credenciales
> - Nunca compartas ni pegues tus tokens o claves privadas en el chat del asistente ni en capturas de pantalla.
> - Nunca confirmes cambios en Git que incluyan tu archivo `.env`.
> - Mantén permisos restringidos (`chmod 600 .env`) para que solo tu usuario pueda leer los secretos.

---

## 1. Crear el Bot en Telegram con @BotFather

1. Abre tu aplicación de Telegram (móvil, web o escritorio).
2. Busca el contacto oficial verificado: **[@BotFather](https://t.me/BotFather)**.
3. Envía el comando `/newbot`.
4. BotFather te solicitará el nombre visible del bot. Escribe:
   ```text
   VLFisioterapia Bot
   ```
5. Luego te solicitará un nombre de usuario único terminado en `bot` (por ejemplo: `VLFisioterapia_demo_bot` o `vlfisio_armenia_bot`).
6. BotFather confirmará la creación y te entregará un mensaje con el token de acceso HTTP API con este formato:
   ```text
   Use this token to access the HTTP API:
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
7. Copia ese token. Este valor será tu `TELEGRAM_BOT_TOKEN`.
8. *(Opcional)* Configura los comandos visibles en Telegram enviando `/setcommands` a BotFather:
   ```text
   start - Iniciar el asistente de VLFisioterapia
   help - Consultar comandos y ejemplos
   reserva - Consultar cita propia con su código
   estado - Verificar resultado de una operación
   reintentar - Reenviar operación con resultado incierto
   descartar - Retirar la propuesta pendiente
   reset - Reiniciar la conversación actual
   ```

---

## 2. Generar la Clave Privada de Servicio (`CHATBOT_API_KEY`)

Para autenticar las peticiones internas entre el proceso del bot (`bot_telegram.py`) y la API del negocio (`main.py`), se utiliza una clave simétrica compartida de alta entropía.

Ejecuta el siguiente comando en tu terminal Bash:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

*La terminal generará una cadena de 43 caracteres seguros (por ejemplo: `kX9z2_PqL81vN5...`). Copia esa cadena; ese valor será tu `CHATBOT_API_KEY`.*

---

## 3. Configurar el Archivo de Variables de Entorno (`.env`)

1. Ubícate en la raíz del repositorio:
   ```bash
   cd /home/victorsheen/chatbot-fisioterapia-x
   ```
2. Si no has creado el archivo `.env`, cópialo desde la plantilla:
   ```bash
   cp .env.example .env
   ```
3. Restringe los permisos del archivo para que nadie más en el sistema operativo pueda leerlo:
   ```bash
   chmod 600 .env
   ```
4. Abre `.env` con tu editor preferido (por ejemplo `nano .env` o `gedit .env`) y completa los campos:
   ```ini
   # 1. Credencial del Bot de Telegram (obtenida de BotFather)
   TELEGRAM_BOT_TOKEN=PEGA_AQUI_TU_TOKEN_DE_BOTFATHER

   # 2. Clave privada compartida FastAPI <-> Telegram (generada con secrets.token_urlsafe)
   CHATBOT_API_KEY=PEGA_AQUI_LA_CADENA_GENERADA_DE_AL_MENOS_16_CARACTERES

   # 3. Dirección local del servidor FastAPI
   CHATBOT_API_URL=http://127.0.0.1:8012

   # 4. Proveedor de LLM (Groq)
   GROQ_API_KEY=gsk_tu_clave_de_groq_aqui
   GROQ_MODEL=openai/gpt-oss-120b

   # 5. Configuración del servidor
   HOST=127.0.0.1
   PORT=8012
   ```
5. Guarda los cambios y cierra el editor.

---

## 4. Comandos de Arranque Local (Linux / Fedora Bash)

Para ejecutar el sistema completo en tu computador se requieren dos terminales independientes: una para el servidor backend (FastAPI) y otra para el adaptador conversacional de Telegram.

### Terminal 1: Iniciar la API del Negocio (FastAPI en puerto 8012)
```bash
cd /home/victorsheen/chatbot-fisioterapia-x
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8012 --reload
```
**Comprobación:**
- Abre tu navegador web en: `http://127.0.0.1:8012/docs`
- Debes ver la interfaz interactiva de Swagger con las rutas `/telegram` listadas bajo el tag **Telegram**.

### Terminal 2: Iniciar el Bot de Telegram (Long Polling)
```bash
cd /home/victorsheen/chatbot-fisioterapia-x
source .venv/bin/activate
python bot_telegram.py
```
**Comprobación:**
- La terminal imprimirá:
  ```text
  Bot de VLFisioterapia en ejecución por polling. Conectado a http://127.0.0.1:8012. Para detenerlo: Ctrl+C.
  ```
- **Nota importante:** Mantén un solo proceso del bot encendido por cada token. Si ejecutas dos procesos simultáneos, Telegram responderá con error `Conflict: terminated by other getUpdates request`.

### Detención de los servicios
Para detener cualquiera de los dos procesos, presiona `Ctrl + C` en su respectiva terminal.

---

## 5. Recorrido de Pruebas de Aceptación Manual en Vivo

Una vez encendidos ambos procesos, abre tu chat privado con el bot en Telegram y realiza el siguiente recorrido de verificación:

1. **Bienvenida e inicio:**
   - Envía `/start`.
   - *Respuesta esperada:* Mensaje de bienvenida oficial de VLFisioterapia presentando los servicios y orientando sobre cómo comenzar.
2. **Ayuda y comandos:**
   - Envía `/help`.
   - *Respuesta esperada:* Guía con todos los comandos y ejemplos clínicos de fisioterapia.
3. **Consulta de tratamientos y tarifas:**
   - Envía: `¿Qué tratamientos tienen y cuánto valen?`
   - *Respuesta esperada:* Listado de los 6 tratamientos con sus nombres, duraciones (45/60 min) y tarifas en pesos colombianos (`$80.000 COP`, etc.).
4. **Consulta de disponibilidad:**
   - Envía: `¿Hay disponibilidad para valoración el próximo lunes?` (usa una fecha futura laboral, ej: `2026-11-23`).
   - *Respuesta esperada:* Horarios libres reales calculados por la agenda según los especialistas asignados.
5. **Preparación de propuesta con resumen y botones:**
   - Envía: `Quiero agendar una valoración para Mariana Gómez el 2026-11-23 a las 10:00`.
   - *Respuesta esperada:* El bot responde con un **resumen inequívoco** indicando paciente, tratamiento, fecha, hora, referencia de solicitud y dos botones interactivos: `[Confirmar]` y `[Descartar]`.
6. **Prueba de descarte:**
   - Pulsa el botón `[Descartar]`.
   - *Respuesta esperada:* El bot retira los botones y confirma que la solicitud fue cancelada sin realizar cambios en la agenda.
7. **Creación y confirmación real:**
   - Prepara nuevamente la cita y pulsa el botón `[Confirmar]`.
   - *Respuesta esperada:* Mensaje de éxito con el código generado (ej: `VF-1A2B3C4D5E`), los datos registrados y la tarifa oficial.
8. **Consulta de la cita propia:**
   - Envía: `/reserva VF-1A2B3C4D5E` (reemplaza con tu código real devuelto).
   - *Respuesta esperada:* Ficha técnica completa de la cita con estado `ACTIVA` y especialista asignado.
9. **Reprogramación de cita propia:**
   - Envía: `Deseo reprogramar mi cita VF-1A2B3C4D5E para el 2026-11-23 a las 14:00`.
   - *Respuesta esperada:* Resumen de reprogramación. Pulsa `[Confirmar]`. La cita conserva su código `VF-1A2B3C4D5E` y se actualiza a las 14:00.
10. **Cancelación de cita propia:**
    - Envía: `Deseo cancelar mi cita VF-1A2B3C4D5E`.
    - *Respuesta esperada:* Resumen de cancelación. Pulsa `[Confirmar]`. El estado de la cita cambia a `CANCELADA` y el horario queda liberado.
11. **Prueba de aislamiento con dos cuentas de Telegram (Laura y Andrés):**
    - Pide a un compañero (o usa una segunda cuenta de Telegram) que intente consultar tu código: `/reserva VF-1A2B3C4D5E`.
    - *Respuesta esperada:* El sistema responde que la reserva no está disponible para ese usuario (HTTP 404 seguro).
12. **Prueba de tolerancia a fallos T24 (Respuesta perdida):**
    - Detén `bot_telegram.py` con `Ctrl+C`.
    - En la misma terminal ejecuta: `python simular_respuesta_perdida.py`.
    - Prepara y confirma una cita de prueba. El simulador ocultará la respuesta al bot simulando una caída de red.
    - El bot informará: *No pude verificar el resultado inmediatamente... Conservo la misma referencia: <REFERENCIA>*.
    - Envía `/estado`.
    - *Respuesta esperada:* El bot consulta la API, recupera el recibo guardado y entrega el código de cita sin duplicar el registro en la base de datos.
    - Detén el simulador con `Ctrl+C` y reinicia `bot_telegram.py`.
