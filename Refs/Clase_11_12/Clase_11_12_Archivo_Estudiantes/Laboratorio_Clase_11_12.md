# Laboratorio. Telegram como canal del chatbot

**Clase 11–12. Tercer corte**  
**Trabajo en los mismos equipos del proyecto**

## Qué vamos a lograr

Una persona podrá abrir el bot del equipo en Telegram, utilizar los comandos iniciales y consultar datos reales del negocio. El nuevo archivo recibirá el mensaje, llamará las funciones existentes y enviará la respuesta al mismo chat.

Esta entrega incluye consultas de servicios, precios y disponibilidad, según lo que admita su proyecto. La ejecución de reservas con confirmación desde Telegram se desarrollará en la siguiente sesión.

## 1. Preparar la carpeta del proyecto

El paquete contiene `bot_telegram.py` y esta guía. Copien el archivo de Python en la carpeta donde ya se encuentran los módulos del chatbot:

```text
proyecto/
    bot_telegram.py       ← archivo de esta sesión
    chatbot_memoria.py    ← módulo de la clase anterior
    consulta_llm.py       ← cliente del modelo y de FastAPI
    app_gradio.py
    main.py              ← FastAPI, si su equipo usa este nombre
    almacen_sqlite.py
    ... archivos del negocio
```

El código importa `nuevo_historial` y `procesar_turno` desde `chatbot_memoria`. Si cambiaron los nombres o la organización del proyecto, adapten ese import. La función que conecten debe recibir pregunta, historial, clave y modelo, y devolver resultado, historial actualizado y plan.

El archivo `bot_telegram.py` se ejecuta por separado. La FastAPI conserva sus rutas y su almacenamiento. La interfaz de Gradio puede permanecer cerrada durante esta práctica.

## 2. Utilizar el entorno del proyecto

Desde PowerShell, situados en la carpeta del proyecto, instalen la biblioteca en el entorno que ya utilizaban:

```powershell
.\.venv\Scripts\python.exe -m pip install "python-telegram-bot>=22,<23"
```

Si su entorno tiene otro nombre o está en otra carpeta, utilicen su ruta real. Al indicar el ejecutable completo no es necesario activar el entorno. Agreguen `python-telegram-bot>=22,<23` al archivo de dependencias de su proyecto.

Comprueben la instalación:

```powershell
.\.venv\Scripts\python.exe -c "import telegram; print(telegram.__version__)"
```

## 3. Registrar la cuenta del bot

1. Abran el contacto oficial [@BotFather](https://t.me/BotFather).
2. Envíen `/newbot`.
3. Escriban el nombre visible de su negocio.
4. Elijan un nombre de usuario disponible que termine en `bot`.
5. Conserven el token de manera privada.
6. Abran el enlace del bot creado y pulsen **Iniciar**.

El bot comenzará a responder con las funciones del proyecto cuando el proceso Python esté funcionando. Si todavía no lo han iniciado, es normal que no aparezca la bienvenida del proyecto.

Pueden usar `/setcommands` en BotFather para mostrar este menú:

```text
start - Iniciar el asistente
help - Ver ayuda y ejemplos
reset - Reiniciar la conversación
```

El menú permite descubrir los comandos. Su ejecución depende de los handlers registrados en Python.

## 4. Personalizar el archivo entregado

En `bot_telegram.py`, cambien `BIENVENIDA` y `AYUDA` por el nombre, el alcance y los ejemplos de su negocio. La ayuda debe mencionar acciones que realmente estén implementadas.

Revisen `formatear_resultado()`. El ejemplo admite un catálogo de servicios con precio y duración y un resultado de disponibilidad con una lista `horas`. Si su FastAPI devuelve otra estructura, ajusten esa presentación a su respuesta real.

En el módulo anterior comprueben que `procesar_turno()` conserva la confirmación previa a cualquier escritura. El adaptador de esta sesión nunca debe llamar a `ejecutar(..., confirmar=True)`. Cuando recibe un resultado de tipo `confirmacion`, informa que la operación quedó sin ejecutar. No promete guardar una reserva ni acepta un «sí» como autorización para hacerlo en esta versión.

## 5. Encender FastAPI

En una primera terminal, desde la carpeta de la API, ejecuten el comando que ya usa su equipo. Si el archivo se llama `main.py` y la aplicación se llama `app`, un ejemplo es:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8011
```

Abran `http://127.0.0.1:8011/docs` y prueben el catálogo o la disponibilidad. Si su API utiliza otro puerto, mantengan el suyo y actualicen la dirección en el cliente.

## 6. Configurar el proceso de Telegram

En una segunda terminal, desde la carpeta de `bot_telegram.py`, indiquen la dirección de la API y el modelo que ya utiliza el proyecto:

```powershell
$env:CHATBOT_API_URL = "http://127.0.0.1:8011"
$env:GROQ_MODEL = "ID_DEL_MODELO_HABILITADO_EN_SU_CUENTA"

$claveGroqProyecto = Read-Host "API key de Groq" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $claveGroqProyecto).Password
```

Estos nombres corresponden a los módulos entregados en la clase anterior. Si su proyecto utiliza otra configuración, mantengan coherencia con ella. Verifiquen también que las rutas de `consulta_llm.py` coincidan con las de FastAPI.

Ahora ejecuten:

```powershell
.\.venv\Scripts\python.exe bot_telegram.py
```

El programa solicitará el token de BotFather sin mostrarlo mientras lo escriben. También admite leerlo desde `TELEGRAM_BOT_TOKEN` si ya configuraron esa variable de forma privada.

La clave de Groq y el token de Telegram pertenecen a servicios diferentes. Conserven ambos fuera del repositorio, las capturas y la bitácora. Si cambian variables de entorno, detengan el bot y vuelvan a iniciarlo desde la terminal donde las definieron.

Para un mismo token mantengan un solo proceso de polling. Detengan el programa con `Ctrl+C` antes de iniciarlo en otro equipo.

## 7. Seguir el recorrido de un mensaje

Identifiquen estas partes en su código:

| Parte | Responsabilidad |
|---|---|
| `Application` | Reúne la configuración y los manejadores. |
| `CommandHandler` | Dirige un comando a su función. |
| `MessageHandler` y su filtro | Seleccionan las preguntas de texto de chats privados. |
| `Update` | Aporta el mensaje, el chat y la persona del evento. |
| `context.chat_data` | Conserva el historial utilizado por esta conversación. |
| `asyncio.to_thread()` | Ejecuta la función síncrona del proyecto sin bloquear directamente el bucle de eventos. |
| `reply_text()` | Envía el resultado al chat por Telegram. |
| `run_polling()` | Mantiene el proceso recogiendo actualizaciones. |

La conexión de esta sesión usa long polling. El computador del bot establece la conexión con Telegram. FastAPI puede seguir en `127.0.0.1` cuando ambos procesos se ejecutan en ese mismo computador.

## 8. Pruebas que deben realizar

| Prueba | Resultado que deben comprobar |
|---|---|
| Enviar `/start` | Presenta el negocio y orienta cómo comenzar. |
| Enviar `/help` | Muestra comandos y ejemplos válidos. |
| Consultar servicios o precios | La respuesta coincide con los datos actuales de FastAPI. |
| Consultar disponibilidad indicando servicio y fecha | La respuesta utiliza el servicio y la fecha solicitados. |
| Dejar un dato pendiente y completarlo en otro mensaje | La consulta continúa con el contexto del mismo chat. |
| Enviar `/start` en medio de la consulta | Muestra la bienvenida y permite continuar con el historial existente. |
| Enviar `/reset` y luego solo el dato que antes faltaba | El contexto anterior ya no completa la solicitud. |
| Enviar un comando que no existe | Orienta hacia `/start`, `/help` y `/reset`. |
| Enviar una foto | Solicita un mensaje de texto. |
| Detener FastAPI y repetir una consulta que la necesite | Informa el fallo de conexión. No inventa un resultado. |

Para las fechas de disponibilidad, utilicen un día futuro en que su negocio atienda. Si la consulta queda incompleta, la respuesta debe pedir el dato que falta.

Al terminar la prueba de fallo, vuelvan a encender FastAPI y repitan la consulta. Los comandos `/start` y `/help` se resuelven en el adaptador y no necesitan consultar el modelo ni el negocio.

## 9. Qué deben entregar

- El archivo `bot_telegram.py` adaptado y la actualización de las dependencias en el repositorio del equipo.
- El nombre público o enlace del bot y las instrucciones para ejecutar el proceso. El computador que lo atiende debe permanecer encendido durante la demostración.
- Evidencias de los comandos, una consulta real contrastada con FastAPI y la continuación de una consulta en otro turno.
- Una entrada de bitácora con el recorrido del mensaje, las funciones reutilizadas y un problema de integración con su solución o estado actual.

La explicación debe permitir localizar la función que recibe la pregunta, la llamada al módulo anterior y el método que entrega la respuesta. Una captura del nombre del bot, por sí sola, no demuestra la integración.

## 10. Si algo falla

| Síntoma | Primera comprobación |
|---|---|
| `ModuleNotFoundError: telegram` | Instalar la dependencia con el mismo Python que ejecuta el archivo. |
| No encuentra `chatbot_memoria` | Colocar el archivo junto al módulo o corregir el import del proyecto. |
| El bot aparece pero no responde a `/start` | Proceso encendido, token correcto y conexión con Telegram. |
| `InvalidToken` | Revisar el token de BotFather. |
| `Conflict` | Detener otra instancia que use ese token y comprobar la configuración de recepción. |
| Los comandos responden pero las consultas fallan | Configuración de Groq, función `procesar_turno()` y dirección de FastAPI. |
| HTTP de error en una consulta | Revisar la respuesta de la API, sus campos, sus rutas y los datos enviados. |
| La respuesta es demasiado extensa | Resumirla o dividirla en bloques. El ejemplo envía hasta 4000 caracteres por mensaje. |

## Referencias

- [Creación de bots y BotFather](https://core.telegram.org/bots/tutorial).
- [Recepción de actualizaciones](https://core.telegram.org/bots/api#getting-updates).
- [Ejemplo oficial de python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/examples.echobot.html).
- [Filtros de mensajes](https://docs.python-telegram-bot.org/en/stable/telegram.ext.filters.html).
- [Datos asociados al chat](https://docs.python-telegram-bot.org/en/stable/telegram.ext.callbackcontext.html#telegram.ext.CallbackContext.chat_data).
- [asyncio.to_thread](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread).
