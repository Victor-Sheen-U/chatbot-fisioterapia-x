---
tipo: bitacora-clase
curso: Electiva 2
periodo: EAM-2026II
equipo: Equipo_Sheen_castaneda_vargas
corte: 1
semana: 2
clase: 2
fecha: 2026-09-07
estado: completado
tags:
  - chatbots
  - bitacora
  - fastapi
  - arquitectura-hibrida
---
# Bitácora — Clase 2 (Sesión Técnica Avanzada)

> [!tip] Cómo usar esta plantilla
> Duplica esta nota al finalizar cada clase y nómbrala `C##_AAAA-MM-DD_Tema`. Completa los campos entre corchetes y conserva enlaces verificables.

## 1. Datos de la sesión

| Campo | Registro |
|---|---|
| Tema | [Arquitectura y Desacoplamiento del Backend Transaccional para VLFisioterapia] |
| Objetivo | [Implementar la capa transaccional determinista en FastAPI y Pydantic, garantizando persistencia atómica y control de concurrencia para evitar alucinaciones del LLM] |
| Proyecto | [VLFisioterapia] |
| Inicio | [09:00 AM] |
| Cierre | [12:00 PM] |

## 2. Participación y responsabilidades

| Integrante | Asistió | Rol de la clase | Responsabilidad asumida | Aporte verificable |
|---|:---:|---|---|---|
| [ValentinCastanedaMarin] | Sí | [Observadora / QA] | [Diseño de casos de prueba y validación de flujos de interacción conversacional] | [Commit de validación de flujos y pruebas unitarias] |
| [VictorSheenAriasZuleta] | Sí | [Cabesilla / Arquitecto] | [Diseño de la arquitectura híbrida y configuración del motor de inferencia Groq / Flowise] | [Commit de integración con Groq y Flowise] |
| [SamuelRojasVargas] | Sí | [ManoDerecha / Backend Lead] | [Implementación del motor transaccional FastAPI, Pydantic v2 y seguridad con os.fsync] | [Commit del núcleo transaccional main.py y pruebas de concurrencia RLock] |

## 3. Reto aplicado al proyecto

### Funcionalidad trabajada

|Nombre DelChatBot|[VLFisioterapia]|
|Dominio| [Vl.FisioTerapia.com]|
|Problema| [Mitigación de alucinaciones en LLMs de salud y control de concurrencia en agendamiento clínico]|
|UsuarioObjetivo|[Pacientes de clínicas de rehabilitación y administradores médicos]|
|Capacidad|[AgendarTerapia]|[OrientacionAlUsuario]|[ConsultarDisponibilidad]|[ConsultarEstadoDeTerapia]|[ConsultarPrecio]|[HistorialTerapias]|[EscalamientoHumano]|  
|[Capacidades]|[Recibir cuestionamientos clínicos, validar esquemas con Pydantic, transaccionalidad atómica y triaje de banderas rojas]|

### Criterios de aceptación

- [x] [Desacoplamiento estricto entre la capa cognitiva (Flowise / Llama 3.3) y la capa transaccional (FastAPI).]
- [x] [Validación robusta de esquemas de entrada utilizando Pydantic v2 con restricciones estrictas (extra="forbid").]
- [x] [Control de concurrencia multihilo mediante un bloqueo de exclusión mutua (`RLock`) para prevenir reservas duplicadas en el mismo turno.]

### Archivos o componentes modificados

- `[main.py]`: [Implementación del backend en FastAPI, validación de esquemas, máquina de estados y persistencia atómica.]
- `[probar_fisioterapia.py]`: [Creación de la suite automatizada de pruebas para simular concurrencia, fallos de disco y ciclos conversacionales.]

## 4. Decisiones técnicas

| Decisión | Razón | Alternativa descartada |
|---|---|---|
| [Separación en dos capas (Cognitiva y Transaccional)] | [Evita que el LLM tenga acceso directo a la base de datos o tome decisiones de negocio críticas sin supervisión determinista.] | [Agentes autónomos de LangChain con Tool Calling nativo (descartados por impredecibles y propensos a bucles o inyecciones).] |
| [Uso de persistencia atómica con `os.fsync` y archivos `.tmp`] | [Garantiza tolerancia a fallos a nivel de kernel, evitando archivos corruptos o en 0 bytes ante cortes de energía.] | [Escritura directa síncrona sobre el archivo JSON (descartada por alto riesgo de corrupción de datos clínicos).] |
| [Requisito estricto de la palabra clave `CONFIRMAR`] | [Elimina ambigüedades interpretativas del LLM ante afirmaciones casuales del usuario ("sí", "dale", "bueno").] | [Permitir que el modelo autorice reservas basándose en el análisis semántico general del chat.] |

## 5. Problemas y soluciones

| Problema encontrado | Causa identificada | Solución aplicada | ¿Cómo se verificó? |
|---|---|---|---|
| [Colisiones de concurrencia en reservas simultáneas] | [Dos hilos intentando registrar el mismo turno en el mismo milisegundo.] | [Implementación de un `threading.RLock` en la sección crítica de lectura y escritura del JSON.] | [Ejecución de hilos simultáneos en `probar_fisioterapia.py` obteniendo respuestas `409 Conflict` correctas.] |
| [Riesgo de corrupción en el almacenamiento local] | [Escrituras interrumpidas dejaban el archivo de citas vacío.] | [Patrón de doble paso: escritura a archivo temporal (`.tmp`) seguida de reemplazo atómico con `os.replace`.] | [Pruebas unitarias simulando fallas de escritura durante el guardado.] |

## 6. Evidencias

| Tipo | Descripción | Enlace o ruta |
|---|---|---|
| Commit | [Estructuración del backend FastAPI y control RLock] | [Historial Git local del proyecto] |
| Captura | [Documentación interactiva Swagger UI en `/docs`] | [`http://localhost:8012/docs`] |
| Demo | [Ejecución exitosa de la suite de pruebas] | [`python probar_fisioterapia.py`] |
| Código | [Lógica de escritura atómica con `os.fsync`] | [`main.py (Módulo de persistencia)`] |

## 7. Uso de inteligencia artificial

> [!important] Registrar la IA no reemplaza la explicación técnica. El equipo debe verificar, adaptar y comprender cualquier resultado utilizado.

| Herramienta        | Objetivo o pregunta                                                                                                                                                                                                                        | Qué se utilizó                                                                                                                                                                                                                                                                                                                                                                    | Cómo se verificó                                                                                                                                                                                                                                                                       | Qué se modificó                                                                                                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Gemini 3.8 Flash] | Preguntas y estructuracion de los metodos https para conectar mediante FastAPI                                                                                                                                                             | Se utilizaron los metodos https creados y se empezaron a organizar mediante un nuevo contenedor docker en el puerto 8012                                                                                                                                                                                                                                                          | Se aplico un test de pruebas "probar_fisioterapia.py" tambien generado por inteligencia artificial para verificar la integridad y correcto funcionamiento donde se verifican respuestas de la API como 200 para la correcta creacion de estos 404 para peticiones mal formados y demas | Se creo un nuevo contenedor docker donde se agregaron los metodos de la API creada                                                                                                                                             |
| [Gemini 3.8 Flash] | Creacion de un entorno de pruebas en python para verificar el estado del proyecto y el correcto funcionamiento tanto de la API como de respuestas formatos y guardado de informacion mediante el modelo de inteligencia artificial de Groq | Se creo un nuevo archivo python para probar el proyecto y verificarlo "probar_fisioterapia.py" este no modifica el proyecto como tal                                                                                                                                                                                                                                              | Este es un entorno de pruebas para verificar entonces al final se obtiene el estado del proyecto y el mismo indica si cumplio con las pruebas o no                                                                                                                                     | No modifica si no que simplemente agrega pruebas a el proyecto y poder verificar su funcionamiento                                                                                                                             |
| [Gemini 3.8 Flash] | Se hicieron preguntas de como poder estructurar correctamente la conexion de Groq, LLM Chain y FastApi usando la aplicacion de Flowise                                                                                                     | Se utilizaron los ejemplos del modelado en Flowise y se subieron ambos archivos .json generados con la opcion de load Chatflow para empezar a configurar y a estructurar correctamente el funcionamiento del chatbot se hicieron 2 versiones una simple sin integracion de FASTAPI y otra version en la que ya esta completo y si se incluye el uso de FASTAPI mediante LLM Chain | Lo Verificamos revisando los nodos y confirmando que estuvieran correctamente conectados entre ellos tambien verificamos que usara las tecnologias correctas como FASTAPI el modelo de inteligencia artificial Groq entre otras pruebas para verificar el estado del chatbot           | Se usaron tanto los modelados de "Fisioterapia_01_Groq_Memoria_FAQ.json" y "Fisioterapia_02_Flowise_FastAPI.json" para empezar a modelar y estructurar correctamente el chatbot mediante su memoria uso de FastApi entre otros |

Si no se utilizó IA, escribir: **No se utilizó inteligencia artificial en esta sesión.**

## 8. Defensa técnica y retroalimentación

| Campo | Registro |
|---|---|
| Integrante que defendió | [Victor Sheen Arias Zuleta] |
| Pregunta recibida | [¿Qué ocurre si dos pacientes intentan agendar la misma hora con el mismo especialista exactamente al mismo tiempo?] |
| Respuesta resumida | [La API protege la sección crítica mediante un `RLock`. El primer hilo adquiere el bloqueo y registra la cita (`201 Created`), mientras que el segundo hilo detecta el turno ocupado y emite un `409 Conflict`, verificado con pruebas de hilos simultáneos.] |
| Retroalimentación docente | [Excelente manejo de la concurrencia y prevención de alucinaciones médicas mediante arquitectura desacoplada.] |
| Mejora acordada | [Documentar los diagramas de secuencia de los hilos concurrentes para la sustentación final.] |

## 9. Aprendizajes

- **Concepto comprendido:** [La importancia de mantener la lógica transaccional y determinista separada del razonamiento probabilístico de los modelos de lenguaje en dominios críticos como la salud.] |
- **Algo que aún genera duda:** [Estrategias óptimas para escalar la persistencia a múltiples servidores distribuidos (PostgreSQL + Redis) manteniendo la misma seguridad transaccional.] |
- **Qué haríamos diferente:** [Implementar la suite de pruebas automatizadas desde la primera iteración de diseño de la API.] |

## 10. Revisión antes de entregar

- [x] Todos los integrantes registraron un aporte verificable.
- [x] Los enlaces y rutas de evidencia funcionan.
- [x] Los criterios de aceptación están actualizados.
- [x] El uso de IA fue declarado y verificado.
- [x] El equipo puede explicar las decisiones registradas.