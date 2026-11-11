---
tipo: bitacora-clase
curso: Electiva 2
periodo: EAM-2026II
equipo: Equipo_Sheen_castaneda_vargas
corte: 3
semana: 9
clase: 13
fecha: 2026-11-11
estado: completado
tags:
  - chatbots
  - bitacora
  - telegram
  - fastapi
  - sqlite
  - idempotencia
  - seguridad
  - transacciones
---
# Bitácora — Clase 13 (Integración de Telegram, Seguridad, Idempotencia y Cierre de Tercer Corte)

> [!tip] Cómo usar esta plantilla
> Duplica esta nota al finalizar cada clase y nómbrala `C##_AAAA-MM-DD_Tema`. Completa los campos entre corchetes y conserva enlaces verificables.

## 1. Datos de la sesión

| Campo | Registro |
|---|---|
| Tema | [Integración de Telegram como Segundo Canal Conversacional, Control de Propiedad por Usuario, Idempotencia en SQLite y Pruebas T01–T25] |
| Objetivo | [Auditar el estado del proyecto, implementar de extremo a extremo el adaptador de Telegram para VLFisioterapia reutilizando el backend existente de FastAPI y SQLite, aplicar confirmación explícita mediante botones, control de concurrencia y recuperación de operaciones inciertas] |
| Proyecto | [VLFisioterapia · Centro Integral de Fisioterapia y Rehabilitación] |
| Inicio | [09:00 AM] |
| Cierre | [01:00 PM] |

## 2. Participación y responsabilidades

| Integrante | Asistió | Rol de la clase | Responsabilidad asumida | Aporte verificable |
|---|:---:|---|---|---|
| [VictorSheenAriasZuleta] | Sí | [Cabecilla / Arquitecto] | [Auditoría arquitectónica, diseño de `AgendaTelegram`, montaje del router `/telegram` en `main.py` y control transaccional atómico con savepoints] | [Módulo `api_telegram.py`, adaptación de `main.py`, aislamiento de conexiones por hilo y esquema relacional de propiedad e idempotencia] |
| [ValentinCastanedaMarin] | Sí | [Observadora / QA] | [Diseño y ejecución de la suite automatizada de pruebas, matriz T01–T25, simulación de concurrencia real (T22) y respuesta perdida (T24)] | [Suite `test_telegram.py` (100% aprobada), simulación de hilos concurrentes, matriz de 25 casos en `Matriz_25_Pruebas.md` y evidencias sanitizadas] |
| [SamuelRojasVargas] | Sí | [Mano Derecha / Backend Lead] | [Adaptación del adaptador `bot_telegram.py` al dominio clínico de VLFisioterapia, formateador de moneda COP, gestión de dependencias y documentación] | [Módulo `bot_telegram.py`, `simular_respuesta_perdida.py`, actualización de `requirements.txt`, `.env.example`, `GUIA_DEL_PROYECTO.md` y `CONFIGURACION_TELEGRAM.md`] |

## 3. Reto aplicado al proyecto

### Funcionalidad trabajada

| Campo | Registro |
|---|---|
| Nombre del Chatbot | [VLFisioterapia] |
| Dominio | [Vl.FisioTerapia.com / Armenia, Quindío] |
| Problema | [La clínica operaba exclusivamente a través de la interfaz web de Gradio; era necesario incorporar Telegram como canal móvil directo manteniendo las mismas reglas de negocio, disponibilidad por profesional, catálogo y persistencia relacional en SQLite] |
| Usuario Objetivo | [Pacientes de la clínica que reservan, consultan, reprograman o cancelan turnos desde Telegram con seguridad e inmediatez] |
| Capacidad | [CanalTelegramPolling] \| [ConfirmacionBotonesInline] \| [PropiedadReservaTelegram] \| [IdempotenciaSolicitud] \| [OptimisticLockingHuella] \| [RecuperacionEstadoIncierto] \| [AislamientoCuentas] |
| [Capacidades] | [Consultar catálogo y disponibilidad real en pesos COP, generar propuestas con 10 min de vigencia, confirmar o descartar mediante botones interactivos, garantizar transacciones atómicas con `SAVEPOINT`, impedir cruces entre dos cuentas y recuperar recibos tras fallas de red] |

### Criterios de aceptación

- [x] [Integración completa de Telegram como adaptador sin duplicar la lógica de negocio ni crear una aplicación FastAPI paralela.]
- [x] [FastAPI existente en `main.py` incorpora el sub-router `/telegram` utilizando la misma instancia lógica de `AgendaTelegram` sobre `reservas.db`.]
- [x] [Gradio (`app_gradio.py`), puente Flowise (`/chat`) y endpoints heredados continúan funcionando sin ninguna regresión (100% en suites previas).]
- [x] [Telegram consulta servicios reales en COP, duraciones reales (45/60 min) y disponibilidad por especialista (`mariana`, `carlos`, `valeria`).]
- [x] [Toda operación de escritura (crear, modificar, cancelar) exige confirmación explícita mediante botones Inline; el LLM solo interpreta y nunca ejecuta directamente.]
- [x] [Control estricto de propiedad: citas creadas en Telegram quedan asociadas a su `usuario_id`; un usuario ajeno recibe HTTP 404 seguro y las citas de Gradio no son accesibles por Telegram.]
- [x] [Idempotencia garantizada: reenvíos con el mismo `solicitud_id` retornan el resultado persistido sin duplicar filas en la base de datos.]
- [x] [Bloqueo optimista con huella SHA-256: si una cita cambia de estado antes de confirmar un resumen, la operación es rechazada con HTTP 409.]
- [x] [Paso exitoso de la suite automatizada `test_telegram.py` y completitud de la matriz de 25 pruebas T01–T25.]

### Archivos o componentes modificados

- [`api_telegram.py`]: [Nuevo módulo con la clase `AgendaTelegram` (tablas `propietarios_telegram` y `operaciones_telegram`, `conexion` por hilo, savepoints, validación de huella) y el router `/telegram` con autenticación `X-API-Key` y autorización `X-Telegram-User`.]
- [`main.py`]: [Sustitución de `AgendaSQLite` por `AgendaTelegram.desde_negocio(BASE / "reservas.db", CLINICA)` e inclusión del router `/telegram` con tolerancia a arranque sin clave (HTTP 503 seguro).]
- [`bot_telegram.py`]: [Adaptador de Telegram para VLFisioterapia con long polling, comandos `/start`, `/help`, `/reserva`, `/estado`, `/reintentar`, `/descartar`, `/reset`, botones inline de confirmación, TTL de 10 min y formateo de tarifas en pesos COP.]
- [`simular_respuesta_perdida.py`]: [Script de práctica para simular timeout en la respuesta de la API tras guardar en base de datos (escenario T24).]
- [`requirements.txt`]: [Incorporación de `python-telegram-bot>=22,<23` manteniendo compatibilidad con `fastapi`, `pydantic` y `gradio 6`.]
- [`requirements_telegram.txt`]: [Archivo de dependencias secundario para el canal de Telegram.]
- [`.env.example`]: [Plantilla actualizada con `TELEGRAM_BOT_TOKEN`, `CHATBOT_API_KEY`, `CHATBOT_API_URL` (puerto 8012) y variables de Groq.]
- [`.gitignore`]: [Inclusión de exclusiones para respaldos (`*.backup*`), bases de práctica y temporales de SQLite.]
- [`test_telegram.py`]: [Suite completa de pruebas automatizadas que valida seguridad, catálogo, ciclo de reservas, idempotencia, concurrencia (T22) y respuesta perdida (T24).]
- [`docs/clase_13/Matriz_25_Pruebas.md`]: [Matriz técnica detallada con los 25 escenarios T01–T25, evidencias enlazadas y registro de fallos corregidos.]
- [`docs/clase_13/GUIA_DEL_PROYECTO.md`]: [Guía explicativa integral del proyecto, límites clínicos, flujo de datos y arquitectura.]
- [`docs/clase_13/CONFIGURACION_TELEGRAM.md`]: [Manual paso a paso para configurar BotFather, generar clave de API, variables de entorno y comandos de inicio en Linux/Bash.]
- [`docs/clase_13/evidencias/`]: [Directorio con registros sanitizados de pruebas automáticas y rutas OpenAPI.]

## 4. Decisiones técnicas

| Decisión | Razón | Alternativa descartada |
|---|---|---|
| [Adaptador Telegram desacoplado mediante llamadas HTTP autenticadas a `/telegram`] | [Mantiene a FastAPI como la única fuente de verdad y autoridad de negocio; el bot solo adapta la interfaz conversacional de Telegram sin acceder directamente a la base de datos.] | [Conectar el bot directamente al archivo SQLite (habría roto la encapsulación, el control de concurrencia y la validación centralizada).] |
| [Uso de `local()` (thread-local) en `AgendaTelegram` para transacciones compuestas] | [Permite reutilizar los métodos existentes de `AgendaSQLite` (`crear`, `modificar`, `cancelar`) dentro de una transacción inmediata compartida que también inserta en `propietarios_telegram` y `operaciones_telegram`.] | [Abrir múltiples conexiones anidadas en el mismo hilo (provocaba bloqueos `database is locked` en SQLite con transacciones inmediatas).] |
| [Bloqueo optimista mediante huella SHA-256 (`referencia`)] | [Garantiza que si una cita fue reprogramada o cancelada por otro canal (o por administración) mientras el usuario leía el resumen, la confirmación se rechaza con 409, evitando sobrescribir datos sin consentimiento.] | [Bloqueo pesimista de filas en lectura (SQLite no soporta SELECT FOR UPDATE nativo y degradaría el rendimiento de lectura).] |
| [Identificación de usuario basada exclusivamente en `update.effective_user.id`] | [Previene cualquier intento de suplantación de identidad; el ID proviene de la firma criptográfica de la Telegram Bot API y no del texto libre ni del LLM.] | [Extraer el usuario del texto del mensaje o permitir que el LLM deduzca el ID (vulnerable a inyecciones de prompt y spoofing).] |
| [Manejo de resultado incierto con estado `incierta` y comando `/estado`] | [Si la red falla tras la persistencia en el servidor, asumir error provocaría que el usuario intente agendar de nuevo, duplicando la cita. Almacenar la referencia permite recuperar el recibo de forma idempotente.] | [Reintentar automáticamente a ciegas con un nuevo UUID (generaría citas duplicadas y conflictos de horario).] |
| [Desactivación segura con HTTP 503 cuando falta `CHATBOT_API_KEY`] | [Permite que el proyecto y todas sus pruebas antiguas de Gradio/FastAPI sigan funcionando sin requerir variables de Telegram obligatorias, pero bloquea el acceso no autorizado a `/telegram`.] | [Lanzar un ValueError al importar `main.py` (habría roto la suite de pruebas del Segundo Corte).] |

## 5. Problemas y soluciones

| Problema encontrado | Causa identificada | Solución aplicada | ¿Cómo se verificó? |
|---|---|---|---|
| [Error `KeyError: 'precio'` al listar servicios desde Telegram] | [El código de referencia de clase usaba `valor['precio']` para un salón de belleza; en VLFisioterapia el campo es `precio_cop`.] | [Se implementó `formatear_pesos` y se adaptó `bot_telegram.py` para leer `info['precio_cop']` y formatear en pesos COP.] | [Ejecución en `test_telegram.py` verificando la presencia de `$80.000 COP` sin excepciones.] |
| [Importación de `main.py` fallaba si no existía `CHATBOT_API_KEY`] | [La función de referencia exigía de forma síncrona una clave de al menos 16 caracteres al inicializar el router.] | [Se implementó desactivación segura: si la clave está vacía, el router responde 503; si se provee, valida los 16 caracteres ASCII.] | [Ejecución exitosa de `probar_fisioterapia.py` sin variables de Telegram en el entorno.] |
| [Citas creadas desde Gradio o API no tenían dueño de Telegram] | [No existía registro en `propietarios_telegram` para citas históricas.] | [Se estableció que `_propia` lance `ReservaNoEncontrada` (404) si el código no pertenece al usuario de Telegram, protegiendo las citas históricas.] | [Caso de prueba automatizado en `test_telegram.py` intentando consultar una cita legacy desde Telegram.] |
| [Colisión en transacciones anidadas de SQLite con `SAVEPOINT`] | [Llamar a `self.crear` abría una segunda conexión `BEGIN IMMEDIATE` bloqueando el mismo hilo.] | [Se utilizó `self._hilo.conexion` para compartir la conexión activa del hilo, envolviendo la operación en un `SAVEPOINT cambio_reserva` con rollback selectivo.] | [Paso exitoso de pruebas de creación, modificación y concurrencia multihilo (T22).] |

## 6. Evidencias

| Tipo | Descripción | Enlace o ruta |
|---|---|---|
| Código | [Capa de API, propiedad e idempotencia de Telegram] | [`api_telegram.py`](file:///home/victorsheen/chatbot-fisioterapia-x/api_telegram.py) |
| Código | [Adaptador conversacional de Telegram para VLFisioterapia] | [`bot_telegram.py`](file:///home/victorsheen/chatbot-fisioterapia-x/bot_telegram.py) |
| Código | [Integración de rutas en FastAPI principal] | [`main.py`](file:///home/victorsheen/chatbot-fisioterapia-x/main.py) |
| Código | [Simulador de timeout y respuesta de red perdida] | [`simular_respuesta_perdida.py`](file:///home/victorsheen/chatbot-fisioterapia-x/simular_respuesta_perdida.py) |
| Test | [Suite completa de pruebas automatizadas del canal] | [`test_telegram.py`](file:///home/victorsheen/chatbot-fisioterapia-x/test_telegram.py) |
| Matriz | [Matriz de pruebas T01 a T25 adaptada al negocio] | [`Matriz_25_Pruebas.md`](file:///home/victorsheen/chatbot-fisioterapia-x/docs/clase_13/Matriz_25_Pruebas.md) |
| Guía | [Guía general del proyecto y arquitectura conceptual] | [`GUIA_DEL_PROYECTO.md`](file:///home/victorsheen/chatbot-fisioterapia-x/docs/clase_13/GUIA_DEL_PROYECTO.md) |
| Manual | [Guía de configuración manual y comandos de ejecución] | [`CONFIGURACION_TELEGRAM.md`](file:///home/victorsheen/chatbot-fisioterapia-x/docs/clase_13/CONFIGURACION_TELEGRAM.md) |
| Evidencia | [Salida de ejecución de la suite de pruebas de Telegram] | [`evidencia_test_telegram.txt`](file:///home/victorsheen/chatbot-fisioterapia-x/docs/clase_13/evidencias/evidencia_test_telegram.txt) |
| Evidencia | [Salida de ejecución de endpoints OpenAPI en FastAPI] | [`evidencia_rutas_api.txt`](file:///home/victorsheen/chatbot-fisioterapia-x/docs/clase_13/evidencias/evidencia_rutas_api.txt) |

## 7. Uso de inteligencia artificial

| Herramienta | Objetivo o pregunta | Qué se utilizó | Cómo se verificó | Qué se modificó |
|---|---|---|---|---|
| [Gemini 3.8 Flash] | Adaptación arquitectónica de `AgendaTelegram` para soportar el esquema multiespecialista de VLFisioterapia con savepoints | Diseño de conexión compartida por hilo (`self._hilo`), transacciones atómicas con `SAVEPOINT` e índices de optimización | Ejecución de `test_telegram.py` incluyendo concurrencia con `ThreadPoolExecutor` | Módulo `api_telegram.py` y `main.py` |
| [Gemini 3.8 Flash] | Adaptación de `bot_telegram.py` al dominio clínico, formato de moneda COP y manejo de estado incierto | Reescritura del formateador, prompts en español para fisioterapia y gestión de callbacks de botones inline | Ejecución de pruebas unitarias simulando respuestas de la API con dobles y timeouts | Módulo `bot_telegram.py` |
| [Gemini 3.8 Flash] | Diseño y ejecución de la suite automatizada para los 25 casos de prueba de la matriz | Estructuración de pruebas con base SQLite temporal, mocks controlados de red y aserciones de consistencia | 100% de casos aprobados en `test_telegram.py` | Módulo `test_telegram.py` y `Matriz_25_Pruebas.md` |

## 8. Defensa técnica y conclusiones

La integración del canal de Telegram en VLFisioterapia cumple con los más altos estándares de robustez, seguridad y consistencia en sistemas transaccionales:
1. **Desacoplamiento estricto:** El bot de Telegram actúa exclusivamente como un cliente del backend. Todas las comprobaciones de horarios, duraciones (45/60 min), disponibilidad de especialistas y políticas clínicas son evaluadas y decididas en la API y en `AgendaSQLite`.
2. **Seguridad y privacidad:** La comunicación servicio a servicio está autenticada con `X-API-Key` mediante comparación en tiempo constante (`secrets.compare_digest`). La identidad del usuario emana directamente del evento verificado de Telegram (`X-Telegram-User`) y nunca del texto interpretado por el LLM.
3. **Idempotencia y resiliencia:** Ante condiciones adversas de red o pérdida de paquetes (escenario T24), la base de datos conserva el recibo de la operación autorizada. El usuario puede recuperar el resultado exacto mediante `/estado` sin riesgo de agendamientos duplicados ni inconsistencias contables.
4. **Retrocompatibilidad intacta:** El ecosistema preexistente (Gradio 6, endpoints nativos de main.py, suite del Segundo Corte) mantiene una tasa de éxito del 100%, demostrando una arquitectura extensible y profesional lista para producción.
