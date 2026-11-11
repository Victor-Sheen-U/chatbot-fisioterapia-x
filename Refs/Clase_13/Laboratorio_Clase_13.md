# Laboratorio. Operaciones de Telegram y pruebas finales

**Clase 13. Trabajo con el proyecto del equipo**

## Resultado que debemos demostrar

Dos personas podrán conversar con el bot desde sus cuentas de Telegram y preparar solicitudes independientes. Cada operación necesitará una confirmación vinculada a su resumen. La API comprobará la propiedad de la reserva, la disponibilidad y el estado actual antes de aplicar el cambio.

La evidencia debe permitir seguir el mensaje hasta el registro del negocio. Al terminar, el equipo completará su matriz de al menos 25 pruebas, registrará las correcciones y preparará la sustentación.

## 1. Archivos del paquete

| Archivo | Uso |
|---|---|
| `bot_telegram.py` | Reemplaza el adaptador anterior. Incluye propuestas por chat, botones, consulta por código y verificación de resultados. |
| `api_telegram.py` | Añade rutas protegidas para Telegram y la clase `AgendaTelegram`, que reutiliza las validaciones de `AgendaSQLite`. |
| `main_telegram_ejemplo.py` | Referencia completa de cómo conectar la ampliación con FastAPI. Utiliza una base de práctica independiente. |
| `requirements_telegram.txt` | Dependencias del canal y de la API. Se instalan en el entorno que ya tiene el equipo. |
| `Matriz_25_Pruebas.md` | Plantilla de resultados y evidencias. Los resultados reales los completa cada equipo. |
| `simular_respuesta_perdida.py` | Arranque opcional del bot para provocar una respuesta perdida de forma controlada en T24. |
| `referencia/` | Copia de los módulos originales y un catálogo de ejemplo para recuperar una base de práctica si hace falta. |

La carpeta `referencia` contiene `almacen_sqlite.py`, `consulta_llm.py` y `negocio_ejemplo.json`. Los módulos propios del equipo conservan sus adaptaciones. Si necesitan esos originales, cópienlos únicamente a una carpeta de práctica donde no existan archivos propios con esos nombres.

## 2. Colocar los archivos en el proyecto

Conserven una copia del `bot_telegram.py` anterior y coloquen la nueva versión en la carpeta del proyecto. Añadan `api_telegram.py` y la referencia de FastAPI.

```text
proyecto/
    bot_telegram.py              ← nueva versión
    api_telegram.py              ← archivo nuevo
    main_telegram_ejemplo.py     ← referencia de integración
    main.py                     ← FastAPI del equipo
    consulta_llm.py              ← módulo existente
    chatbot_memoria.py
    almacen_sqlite.py           ← módulo existente
    negocio.json
    ... datos y archivos del equipo
```

El nuevo bot reutiliza `GROQ_URL` y `peticion_json()` de `consulta_llm.py`. La clase `ClienteAPI`, dentro del nuevo `bot_telegram.py`, implementa las peticiones protegidas del canal. No hace falta modificar las acciones antiguas de `consulta_llm.py` para ejecutar este adaptador.

La interpretación para Telegram se encuentra en `interpretar()`. Su historial incluye la acción `consultar` y los resultados que llegaron después de pulsar los botones. La versión de Gradio puede conservar sus módulos actuales.

## 3. Integrar las rutas en FastAPI

Localicen dónde su `main.py` crea la agenda y la aplicación `app`. Mantengan sus rutas, su catálogo y los horarios del negocio. Añadan este import:

```python
import os
from api_telegram import AgendaTelegram, crear_router
```

En el lugar donde se construía `AgendaSQLite`, utilicen `AgendaTelegram` con la misma ruta de base y las mismas opciones. Por ejemplo:

```python
agenda = AgendaTelegram(
    BASE / "reservas.db",
    SERVICIOS,
    apertura="09:00",
    cierre="18:00",
)
```

Después de la creación de la aplicación que ya utilizan, añadan el router:

```python
app.include_router(
    crear_router(agenda, os.environ.get("CHATBOT_API_KEY", ""))
)
```

No deben crear una segunda variable `app` que deje desconectadas las rutas anteriores. `main_telegram_ejemplo.py` permite ver esta integración reunida en un archivo pequeño. Si su almacenamiento utiliza otra clase o métodos diferentes, adapten la conexión antes de trasladarla al proyecto.

Para probar la referencia sin tocar la base del proyecto pueden ejecutar `main_telegram_ejemplo:app`. Este archivo lee su `negocio.json` y crea `reservas_practica_telegram.db`. El catálogo debe tener servicios como diccionario y los campos `precio` y `duracion_minutos`; revisen el JSON de referencia si necesitan comparar la estructura.

## 4. Qué añade al almacenamiento

`AgendaTelegram` conserva la tabla de reservas y añade dos tablas:

- `propietarios_telegram`: relaciona el código de reserva con el identificador de usuario que la creó desde Telegram.
- `operaciones_telegram`: conserva el identificador de solicitud, los datos que se autorizaron y su respuesta. Permite reconocer un reenvío de la misma operación.

La comprobación del intervalo, el registro de la reserva, la propiedad y su recibo utilizan la misma transacción. La ampliación reutiliza los métodos del almacenamiento existente con la conexión de esa operación.

Una reserva antigua sin propietario de Telegram no queda asignada a quien escriba su código. Para esta práctica creen datos desde las cuentas que van a probar. El traslado de reservas anteriores requiere una asociación verificada por el equipo.

La API calcula también una referencia de los datos actuales. Si la reserva cambia después de preparar un resumen, la confirmación del resumen anterior recibe un rechazo. Se debe consultar de nuevo y presentar otra propuesta.

## 5. Preparar el entorno y la clave de la API

Desde PowerShell, en la carpeta del proyecto, instalen las dependencias con el ejecutable de su entorno:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements_telegram.txt
```

Si el entorno tiene otro nombre o ubicación, utilicen su ruta real. La ruta explícita permite ejecutarlo sin activar el entorno.

Esta integración añade `CHATBOT_API_KEY`: una clave privada compartida entre el bot y FastAPI. El equipo elige la misma clave para ambos procesos, con al menos 16 caracteres ASCII. Usen una combinación privada de letras, números y símbolos que no incluya tildes.

No es el token de BotFather ni la clave de Groq. Su función es permitir que la API reconozca al servicio del bot que envía la identidad de Telegram.

## 6. Terminal de FastAPI

Antes de iniciar la API, configuren su clave de forma privada:

```powershell
$claveApiEquipo = Read-Host "Clave privada de la API del equipo" -AsSecureString
$env:CHATBOT_API_KEY = [System.Net.NetworkCredential]::new('', $claveApiEquipo).Password

.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8011
```

Si van a probar la referencia, sustituyan únicamente `main:app` por `main_telegram_ejemplo:app`. Mantengan una sola API en ese puerto.

Abran `http://127.0.0.1:8011/docs` y comprueben que aparecen las rutas `/telegram`. La API rechazará llamadas sin su clave. En el cliente del bot se envía mediante `X-API-Key`; la identidad de quien actúa se envía mediante `X-Telegram-User`.

En esta práctica la API permanece local. Si se publica, deben revisar también la autenticación y exposición de todas las rutas anteriores. Agregar las rutas nuevas no protege automáticamente un endpoint antiguo que permita listar o cambiar reservas sin permiso.

## 7. Terminal del bot

En otra terminal, desde la carpeta del proyecto, configuren la dirección de FastAPI y el modelo que ya utiliza el equipo:

```powershell
$env:CHATBOT_API_URL = "http://127.0.0.1:8011"
$env:GROQ_MODEL = "ID_DEL_MODELO_HABILITADO_EN_SU_CUENTA"

$claveGroqEquipo = Read-Host "API key de Groq" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $claveGroqEquipo).Password

.\.venv\Scripts\python.exe bot_telegram.py
```

El programa solicitará el token de BotFather y la clave privada de FastAPI sin mostrarlos al escribir, salvo que ya estén definidos en `TELEGRAM_BOT_TOKEN` y `CHATBOT_API_KEY`. La clave de FastAPI debe ser exactamente la misma que usaron en la otra terminal.

Personalicen la bienvenida y la ayuda de `bot_telegram.py` con el nombre y el alcance de su negocio. Conserven un solo proceso de polling por token. Después de cambiar variables de entorno, detengan el proceso y vuelvan a iniciarlo desde la terminal configurada.

## 8. Recorrido de una reserva

En el chat privado del bot, envíen una solicitud de su negocio con cliente, servicio, fecha y hora. Usen una fecha futura en que atienda el negocio.

Para el catálogo de ejemplo pueden preparar un cepillado de 60 minutos a las 10:00 para Laura. El bot debe mostrar el resumen con una referencia de solicitud y los botones **Confirmar** y **Descartar**.

Antes de pulsar **Confirmar**, la propuesta solo está en el estado de ese chat. Al confirmar, la API registra la operación y devuelve un código de reserva. Comprueben ese código con:

```text
/reserva CODIGO_DEVUELTO
```

El código de reserva identifica el registro del negocio. La referencia de solicitud identifica la operación y permite consultar su resultado. Ambos datos aparecen en los mensajes y tienen funciones diferentes.

## 9. Comandos y decisiones del archivo

| Comando o control | Comportamiento |
|---|---|
| `/start` y `/help` | Bienvenida y orientación del negocio. |
| Botón **Confirmar** | Valida chat, usuario, identificador, estado y vigencia; después llama a la API. |
| Botón **Descartar** o `/descartar` | Retira la propuesta que aún no se ejecutó. |
| `/reserva CODIGO` | Consulta una reserva propia mediante la API. |
| `/estado` | Comprueba la operación pendiente o la última referencia de esta conversación. |
| `/estado REFERENCIA` | Recupera el recibo de una operación propia, incluso después de reiniciar el proceso, si el resultado quedó registrado. |
| `/reintentar` | Reenvía una operación incierta con el mismo identificador y los mismos datos. La API reconoce el reenvío. |
| `/reset` | Reinicia ese chat y retira su propuesta normal. Si el resultado es incierto, conserva la referencia hasta verificarlo. |

El resultado de `/estado` es el recibo de aquella operación. Para el estado actual de la reserva se utiliza `/reserva CODIGO`.

La vigencia de una propuesta es de diez minutos. Corregir sus datos presenta otro resumen con otro identificador. Si se quiere cambiar a una operación diferente mientras hay otra esperando, primero se confirma o se descarta la anterior.

Los mensajes anteriores pueden seguir visibles en Telegram después de `/reset`. Los botones antiguos deben quedar rechazados por el programa aunque su mensaje continúe en pantalla.

## 10. Modificar y cancelar

Pidan cambiar una reserva propia indicando su código y los nuevos datos. El bot recuperará el registro actual y presentará un resumen. Antes de confirmar, comprueben que el código corresponde a la reserva que desean modificar.

Si el nuevo horario es válido, la API actualiza el registro y conserva su código. Si lo rechaza, debe permanecer intacta la reserva anterior. Prueben ambos resultados.

Para cancelar, indiquen el código y revisen el resumen antes de confirmar. El estado cambia a `cancelada` y el intervalo deja de contar como ocupado. Descartar un resumen de cancelación conserva la reserva activa.

## 11. Prueba con dos cuentas

Utilicen dos cuentas privadas del mismo bot. Una persona trabaja como Laura y la otra como Andrés; no ejecuten dos procesos con el mismo token.

1. Laura prepara un servicio y Andrés prepara otro. Comparen los resúmenes y sus referencias.
2. Laura confirma un cepillado de 10:00 a 11:00.
3. Andrés intenta confirmar un corte que empezaría a las 10:30. La API debe rechazar el cruce.
4. Andrés intenta consultar, modificar o cancelar el código de Laura. El servicio debe rechazar el acceso.
5. Laura prepara otra propuesta y reinicia su chat. Su reserva registrada debe permanecer y la propuesta de Andrés debe seguir intacta.
6. Comprueben que una pulsación repetida o un botón anterior no crean otra operación.

Si su proyecto no utiliza agenda, adapten el conflicto a una condición real del negocio y expliquen qué restricción protege la API.

## 12. Resultado incierto y reinicio del proceso

Si se pierde la respuesta de una escritura, el bot conserva su referencia como `incierta`. Primero utilicen `/estado`. Si el recibo está registrado, el bot recupera el resultado sin crear otra reserva.

Si aún no hay un resultado verificable, el mensaje no demuestra que la escritura haya fallado. El comando `/reintentar` conserva los datos y el identificador de la operación previamente confirmada. La API incluida guarda los recibos y reconoce ese reenvío.

El historial y las propuestas del bot viven en memoria. Al reiniciar Python se pierde ese estado, pero las reservas y los recibos permanecen en la base de FastAPI. Conserven la referencia que aparece en el resumen para poder consultar `/estado REFERENCIA`.

La simulación de respuesta perdida en las diapositivas se realiza con datos de práctica. Las evidencias del equipo deben describir qué condición consiguieron probar; no deben declarar que simularon un fallo que nunca ejecutaron.

Para ejecutar T24 en su proyecto, detengan el bot normal y, con la misma configuración y la API funcionando, inicien:

```powershell
.\.venv\Scripts\python.exe simular_respuesta_perdida.py
```

Preparen y confirmen una reserva de práctica. El archivo deja que la API termine y oculta al bot la primera respuesta correcta de escritura. El bot debe informar el resultado incierto. Anoten la referencia y utilicen `/estado`: debe recuperar el recibo sin añadir otra reserva. Comprueben también `/reserva CODIGO` y el número de registros. Al terminar, detengan este proceso y vuelvan a iniciar `bot_telegram.py` de forma normal. El simulador afecta una sola respuesta por cada arranque suyo y no se incluye en la ejecución habitual.

## 13. Matriz y correcciones

Completen `Matriz_25_Pruebas.md` con los resultados del proyecto. La tabla ya contiene entradas y expectativas; cada equipo añade condiciones previas, resultado obtenido, evidencia y corrección cuando haga falta.

Una prueba de escritura debe contrastarse con la API o el almacenamiento. El texto «reserva registrada» por sí solo no demuestra que exista una fila. Un rechazo debe demostrar que el registro anterior quedó sin cambios.

Después de corregir un fallo, repitan su caso y los comportamientos cercanos. Por ejemplo, un cambio en los controles de confirmación requiere volver a probar el botón vigente, el antiguo, el descarte y el reinicio.

Dos chats intercalados comprueban aislamiento. Para afirmar que probaron escrituras concurrentes, deben generar peticiones que realmente se superpongan; el procesamiento secuencial del bot puede ocultar ese problema.

## 14. Qué debe quedar en la entrega

- Los archivos adaptados al negocio, sus dependencias y un README que permita iniciar la API y el bot.
- Evidencias de dos conversaciones independientes, una escritura confirmada, su consulta y las operaciones de modificación y cancelación.
- Pruebas del rechazo de cruces, acceso ajeno, resumen antiguo, reinicio y repetición de una confirmación.
- La matriz completa con al menos 25 casos y el registro de las correcciones.
- Una bitácora que explique qué añadió el canal, dónde se valida cada operación y cómo se comprobaron los resultados.

El repositorio y las capturas deben conservar fuera las credenciales. Usen datos de práctica para las evidencias que se compartirán.

## 15. Si la integración falla

| Síntoma | Primera comprobación |
|---|---|
| No encuentra `consulta_llm` o `almacen_sqlite` | Archivos existentes junto a los nuevos. Si faltan, recuperar la referencia en una carpeta de práctica. |
| FastAPI no inicia y menciona `CHATBOT_API_KEY` | Configurar la clave privada antes de iniciar la API. |
| HTTP 401 | El bot y FastAPI utilizan la misma clave privada. |
| Los botones aparecen pero no responden | `CallbackQueryHandler` registrado y `callback_query` incluido en `allowed_updates`. |
| Reserva no disponible para este usuario | Código correcto y relación de propiedad registrada desde esa cuenta. Las reservas antiguas no se asignan por conocer el código. |
| La reserva cambió antes de confirmar | Consultarla de nuevo y preparar otro resumen con su referencia actual. |
| HTTP 409 por horario | Comprobar la duración y las reservas activas; elegir otro intervalo. |
| Resultado incierto | Conservar la referencia y verificar `/estado` antes de intentar otra operación. |

La siguiente sesión queda dedicada a la sustentación final.
