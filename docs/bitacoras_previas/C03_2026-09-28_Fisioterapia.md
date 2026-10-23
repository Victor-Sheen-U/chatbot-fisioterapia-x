---
tipo: bitacora-clase
curso: Electiva 2
periodo: EAM-2026II
equipo: Equipo_Sheen_castaneda_vargas
corte: 2
semana: 4
clase: 3
fecha: 2026-09-28
estado: completado
tags:
  - chatbots
  - bitacora
  - groq
  - fastapi
  - memoria-multiturno
  - llm
---
# Bitácora — Clase 06 y 07 (Conexión LLM, FastAPI y Memoria Conversacional)

> [!tip] Cómo usar esta plantilla
> Duplica esta nota al finalizar cada clase y nómbrala `C##_AAAA-MM-DD_Tema`. Completa los campos entre corchetes y conserva enlaces verificables.

## 1. Datos de la sesión

| Campo | Registro |
|---|---|
| Tema | [Conexión de FastAPI con Groq (Clase 06) y Memoria Conversacional Multi-Turno con Historial (Clase 07)] |
| Objetivo | [Construir la capa cliente en Python para interpretar intenciones con Groq, ejecutar operaciones en FastAPI y mantener historial acumulado en turnos sucesivos con comando de reinicio] |
| Proyecto | [VLFisioterapia] |
| Inicio | [09:00 AM] |
| Cierre | [12:00 PM] |

## 2. Participación y responsabilidades

| Integrante | Asistió | Rol de la clase | Responsabilidad asumida | Aporte verificable |
|---|:---:|---|---|---|
| [ValentinCastanedaMarin] | Sí | [Observadora / QA] | [Diseño de casos de prueba multi-turno, validación de retención de contexto y comando REINICIAR] | [Bitácora técnica, casos de prueba en 2 turnos y verificación de persistencia] |
| [VictorSheenAriasZuleta] | Sí | [Cabesilla / Arquitecto] | [Implementación de `consulta_llm.py` y `chatbot_memoria.py`, integración de prompts estructurados y conexión a Groq] | [Código de cliente Groq, extracción resiliente de JSON y gestión del historial de mensajes] |
| [SamuelRojasVargas] | Sí | [ManoDerecha / Backend Lead] | [Adaptación de endpoints en `main.py`, rutas de compatibilidad, normalización de servicios y suite de integración] | [Mapeo de rutas REST (`/citas`, `/servicios`), normalizador de servicios y script `test_integracion_completa.py`] |

## 3. Reto aplicado al proyecto

### Funcionalidad trabajada

|Nombre DelChatBot|[VLFisioterapia]|
|Dominio| [Vl.FisioTerapia.com]|
|Problema| [El modelo de lenguaje pierde el contexto entre preguntas consecutivas y requiere mapear lenguaje natural a rutas REST estrictas]|
|UsuarioObjetivo|[Pacientes que agendan consultas de rehabilitación o piden información por partes]|
|Capacidad|[InterpretarIntencion]|[ConsultarServicios]|[ConsultarDisponibilidad]|[AgendarEnVariosTurnos]|[ModificarCita]|[CancelarCita]|[ReiniciarConversacion]|  
|[Capacidades]|[Generar plan JSON estricto, acumular entidades entre turnos (`messages[]`), validar confirmación explícita y desacoplar memoria de la base de datos JSON]|

### Criterios de aceptación

- [x] [Generación de plan determinista por parte de Groq en formato JSON (`accion`, `cliente`, `servicio`, `fecha`, `hora`, `codigo`).]
- [x] [Mapeo exitoso de acciones hacia los endpoints reales de FastAPI (`/servicios`, `/disponibilidad`, `/citas`, `/citas/{codigo}/reprogramar`, `/citas/{codigo}`).]
- [x] [Conversación multi-turno acumulativa donde datos faltantes en el turno 1 (ej. hora) son recordados y completados en el turno 2.]
- [x] [Implementación del comando `REINICIAR` que limpia el historial del chat sin alterar las citas guardadas en `citas.json`.]
- [x] [Flujo estricto de confirmación previa `(s/n)` para acciones de escritura (crear, modificar, cancelar).]

### Archivos o componentes modificados

- `[consulta_llm.py]`: [Lógica base de la Clase 06: cliente Groq, extracción y normalización de JSON, llamado a endpoints de FastAPI y confirmación interactiva.]
- `[chatbot_memoria.py]`: [Módulo de la Clase 07: memoria conversacional con lista acumulada `messages[]`, roles `system`, `user`, `assistant` y comando `REINICIAR`.]
- `[main.py]`: [Ampliación de rutas de compatibilidad (`/api/...`), normalizador de nombres clínicos y soporte para pruebas interactivas de las diapositivas.]
- `[.env]`: [Actualización de credenciales de Groq (en variable `GROQ_API_KEY`), modelo habilitado (`openai/gpt-oss-120b`) y URL de API (`http://127.0.0.1:8012`).]
- `[test_integracion_completa.py]`: [Suite integral automatizada que valida el circuito completo: API ➔ Groq ➔ Memoria ➔ Base de datos.]

## 4. Decisiones técnicas

| Decisión | Razón | Alternativa descartada |
|---|---|---|
| [Historial en lista local de Python (`messages[]`)] | [Permite control total sobre qué turnos y datos se envían a Groq en cada solicitud, evitando costes innecesarios y fugas de contexto.] | [Delegar el historial al proveedor LLM o base de datos externa en esta fase.] |
| [Mapeo de normalización de servicios en cliente y backend] | [Permite que el paciente escriba *"fisioterapia deportiva"* o *"terapia manual"* y el sistema traduzca automáticamente a `deportiva` o `puncion_seca`, evitando errores 422 de Pydantic.] | [Exigir al usuario que conozca las claves técnicas exactas del JSON.] |
| [Desacoplamiento total entre historial de chat y base de datos] | [Garantiza que reiniciar una sesión de conversación (`REINICIAR`) no afecte ni borre las reservas formales almacenadas en `citas.json`.] | [Mezclar las reservas dentro de las variables de sesión del bot.] |
| [Forzado de resolución IPv4 y User-Agent compatible] | [Evita bloqueos HTTP 403 y tiempos de espera de 20s de Cloudflare en entornos Linux donde IPv6 no está enrutado.] | [Depender de la configuración de red predeterminada del sistema operativo.] |

## 5. Problemas y soluciones

| Problema encontrado | Causa identificada | Solución aplicada | ¿Cómo se verificó? |
|---|---|---|---|
| [Error HTTP 422 al intentar crear o modificar citas desde `consulta_llm.py`] | [Las rutas y nombres de campos de la plantilla genérica (`confirmada`, `PUT /api/reservas`) no coincidían con `main.py` (`confirmado`, `POST /citas`, `PATCH .../reprogramar`).] | [Se sincronizó `RUTAS` y los cuerpos JSON en `consulta_llm.py` y se agregaron rutas alias en `main.py`.] | [Pruebas exitosas con `test_integracion_completa.py` tanto en rutas nativas como de compatibilidad.] |
| [Error HTTP 403 y latencia en peticiones a `api.groq.com`] | [El User-Agent predeterminado de Python era bloqueado por Cloudflare, y Linux intentaba IPv6 antes que IPv4.] | [Se agregó User-Agent de navegador y se priorizó `socket.AF_INET` en `consulta_llm.py`.] | [Tiempo de respuesta de Groq reducido de >20s a 0.37 segundos con código 200 OK.] |
| [El LLM devolvía bloques markdown ````json ... ````] | [Modelos de lenguaje modernos envuelven las respuestas estructuradas en bloques de código markdown.] | [Se implementó la función `extraer_json()` que recorta encabezados markdown y extrae limpiamente entre `{` y `}`.] | [Decodificación 100% confiable sin errores `JSONDecodeError`.] |

## 6. Evidencias

| Tipo | Descripción | Enlace o ruta |
|---|---|---|
| Código | [Cliente Groq y ejecutor transaccional] | [`consulta_llm.py`] |
| Código | [Gestor de memoria multi-turno y reinicio] | [`chatbot_memoria.py`] |
| Código | [Backend FastAPI con capa de compatibilidad] | [`main.py`] |
| Test | [Suite de pruebas de integración completa] | [`test_integracion_completa.py`] |
| Documentación | [Guía rápida de arquitectura y configuración] | [`explicacion-clase-06-07.md`] |

## 7. Uso de inteligencia artificial

> [!important] Registrar la IA no reemplaza la explicación técnica. El equipo debe verificar, adaptar y comprender cualquier resultado utilizado.

| Herramienta | Objetivo o pregunta | Qué se utilizó | Cómo se verificó | Qué se modificó |
|---|---|---|---|---|
| [Groq / openai/gpt-oss-120b] | Inferencia de lenguaje natural y extracción estructurada de entidades clínicas | Generación de planes JSON (`accion`, `cliente`, `servicio`, `fecha`, `hora`, `codigo`) a partir de mensajes libres del paciente | Validación mediante aserciones de esquema y tipos en `test_integracion_completa.py` | Prompt estricto del sistema que restringe al modelo a extraer datos sin inventar reservas |
| [Gemini 3.8 Flash] | Depuración de tiempos de red, normalización de contratos y pruebas de integración | Diagnóstico del bloqueo IPv6/User-Agent en urllib y diseño de la arquitectura desacoplada de memoria multi-turno | Ejecución de suite de pruebas unitarias y de integración pasando al 100% | Ajuste de funciones `peticion_json`, `interpretar_turno`, `procesar_turno` y compatibilidad en `main.py` |

## 8. Defensa técnica y retroalimentación

> [!important] Requerimiento de entrega de la Clase 07:
> *"Entreguen el archivo nuevo y una bitácora breve. Expliquen qué función consulta Groq, cuál llama a FastAPI y por qué reiniciar el chat no borra las reservas."*

| Campo | Registro |
|---|---|
| Integrante que defendió | [Victor Sheen Arias Zuleta / Equipo] |
| Pregunta recibida | [¿Qué función consulta Groq, cuál llama a FastAPI y por qué reiniciar el chat no borra las reservas?] |
| Respuesta resumida | **1. Función que consulta Groq:** `interpretar_turno()` (en `chatbot_memoria.py`) o `interpretar()` (en `consulta_llm.py`), las cuales arman el payload con el rol `system` y los mensajes acumulados, llamando a la URL de Groq mediante `peticion_json()`.<br>**2. Función que llama a FastAPI:** `ejecutar()` (en `consulta_llm.py`), que valida el plan devuelto por el modelo y realiza las peticiones HTTP (`GET /servicios`, `GET /disponibilidad`, `POST /citas`, `PATCH /citas/...`, `DELETE /citas/...`) contra los endpoints transaccionales.<br>**3. Por qué reiniciar el chat no borra las reservas:** Porque existe un **desacoplamiento arquitectónico estricto**. El comando `REINICIAR` restablece únicamente la lista en memoria volátil de Python (`historial = nuevo_historial()`, dejando solo el mensaje `system`). En cambio, las reservas confirmadas están persistidas en el disco dentro de `citas.json` a través de FastAPI con escritura atómica. El modelo de lenguaje ni el historial tienen acceso directo al archivo físico de almacenamiento. |
| Retroalimentación docente | [Excelente comprensión del desacoplamiento de capas entre el estado de la conversación y el estado del negocio.] |
| Mejora acordada | [Preparar las funciones `nuevo_historial()` y `procesar_turno()` para ser importadas como backend de la interfaz Gradio en la Clase 08.] |

## 9. Aprendizajes

- **Concepto comprendido:** [Cómo estructurar una memoria multi-turno pasando el contexto completo en la lista `messages[]` sin guardar estado en el servidor de inferencia del LLM, y la diferencia crítica entre la memoria conversacional volátil y la persistencia transaccional del negocio.]
- **Algo que aún genera duda:** [Cómo gestionar eficientemente historiales conversacionales muy extensos (estrategias de ventana deslizante o resumen semántico con embeddings) cuando se alcance el límite de ventana de contexto del modelo.]
- **Qué haríamos diferente:** [Haber establecido los contratos de nombres de campos (`confirmado` vs `confirmada`, nombres de servicios) en un archivo de constantes compartido desde el primer día para evitar desajustes entre módulos.]

## 10. Revisión antes de entregar

- [x] Todos los integrantes registraron un aporte verificable.
- [x] Los enlaces y rutas de evidencia funcionan.
- [x] Los criterios de aceptación están actualizados.
- [x] El uso de IA fue declarado y verificado.
- [x] El equipo puede explicar las decisiones registradas (qué función consulta Groq, cuál llama a FastAPI y por qué reiniciar el chat no borra las reservas).
