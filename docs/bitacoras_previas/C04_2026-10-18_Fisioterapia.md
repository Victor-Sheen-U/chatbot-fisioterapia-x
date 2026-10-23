---
tipo: bitacora-clase
curso: Electiva 2
periodo: EAM-2026II
equipo: Equipo_Sheen_castaneda_vargas
corte: 2
semana: 6
clase: 4
fecha: 2026-10-18
estado: completado
tags:
  - chatbots
  - bitacora
  - gradio
  - sqlite
  - disponibilidad
  - fastapi
  - transacciones
---
# Bitácora — Clase 08 y 09 (Gradio, SQLite y Disponibilidad por Profesional)

> [!tip] Cómo usar esta plantilla
> Duplica esta nota al finalizar cada clase y nómbrala `C##_AAAA-MM-DD_Tema`. Completa los campos entre corchetes y conserva enlaces verificables.

## 1. Datos de la sesión

| Campo | Registro |
|---|---|
| Tema | [Integración de Gradio, Persistencia Relacional en SQLite (`reservas.db`) y Control de Disponibilidad por Especialista] |
| Objetivo | [Hacer que el chatbot de VLFisioterapia funcione desde Gradio, conserve una conversación por sesión y guarde sus citas en SQLite a través de FastAPI, comprobando duración del servicio e intervalos ocupados por fisioterapeuta con control de concurrencia y transacciones atómicas] |
| Proyecto | [VLFisioterapia] |
| Inicio | [09:00 AM] |
| Cierre | [12:00 PM] |

## 2. Participación y responsabilidades

| Integrante | Asistió | Rol de la clase | Responsabilidad asumida | Aporte verificable |
|---|:---:|---|---|---|
| [ValentinCastanedaMarin] | Sí | [Observadora / QA] | [Diseño y ejecución de casos de prueba de cruces de agenda, concurrencia multihilo y verificación de la interfaz web en Gradio] | [Pruebas de cruce por profesional (Mariana vs Valeria), adyacencia exacta y documentación de evidencias en la bitácora técnica] |
| [VictorSheenAriasZuleta] | Sí | [Cabesilla / Arquitecto] | [Adaptación de `almacen_sqlite.py`, diseño del esquema de 16 columnas, soporte multiespecialista y orquestación con Gradio] | [Arquitectura de `AgendaSQLite`, constructor `desde_negocio`, control transaccional `BEGIN IMMEDIATE` y script de migración] |
| [SamuelRojasVargas] | Sí | [ManoDerecha / Backend Lead] | [Adaptación de la capa de almacenamiento en `main.py`, eliminación de JSON legacy, integración de `responder()` y actualización de entorno y contenedor] | [Reescritura de endpoints transaccionales en `main.py`, actualización de `probar_fisioterapia.py`, `docker-compose.yml` y `requirements.txt`] |

## 3. Reto aplicado al proyecto

### Funcionalidad trabajada

| Campo | Registro |
|---|---|
| Nombre del Chatbot | [VLFisioterapia] |
| Dominio | [Vl.FisioTerapia.com] |
| Problema | [El almacenamiento en JSON plano limita el escalamiento concurrente y el almacén genérico bloqueaba citas de diferentes fisioterapeutas en horarios simultáneos] |
| Usuario Objetivo | [Pacientes de la clínica que reservan turnos desde una UI web interactiva y administradores de fisioterapia] |
| Capacidad | [InterfazGradioSesion] \| [GestionPersistenciaSQLite] \| [ValidacionDisponibilidadPorFisio] \| [PrevencionCruceEspecialista] \| [AdyacenciaExactaTurnos] \| [MigracionIdempotente] \| [ToleranciaFallos503] |
| [Capacidades] | [Mantener sesiones independientes en Gradio, comprobar duración y bloqueos por profesional en `BEGIN IMMEDIATE`, migrar 14 registros históricos sin duplicidad, y responder con códigos HTTP deterministas (400, 404, 409, 422, 503)] |

### Criterios de aceptación

- [x] [Persistencia completa en SQLite (`reservas.db`) con tabla `reservas` de 16 columnas compatibles con `RegistroCita` y eliminación total de dependencias activas de `citas.json` en la API.]
- [x] [Comprobación de cruces y disponibilidad estrictamente por fisioterapeuta (las citas de Mariana no bloquean a Valeria ni a Carlos), respetando horarios diferenciados por día y adyacencia exacta.]
- [x] [Transaccionalidad atómica y prevención de condiciones de carrera con `BEGIN IMMEDIATE` garantizando que dos peticiones simultáneas sobre el mismo intervalo de un profesional admitan exactamente una (`201`) y rechacen la otra (`409`).]
- [x] [Migración fiel (14 filas históricas), idempotente (segunda ejecución reporta 14 ya existentes) y atómica ante datos corruptos.]
- [x] [Interfaz web interactiva funcional con Gradio 6 (`app_gradio.py`) respondiendo en el puerto 7860 y conectada al backend FastAPI en el puerto 8012.]
- [x] [Paso satisfactorio del 100% de la suite de pruebas unitarias e integración en `probar_fisioterapia.py` y compilación limpia de todos los módulos Python.]

### Archivos o componentes modificados

- `[almacen_sqlite.py]`: [Adaptación de `AgendaSQLite` con constructor `desde_negocio()`, soporte para 3 especialistas (`mariana`, `carlos`, `valeria`), horarios semanales por día, zona horaria `America/Bogota`, 16 columnas tipadas y control `BEGIN IMMEDIATE`.]
- `[main.py]`: [Reemplazo de `leer_citas`/`guardar_citas` por `AgendaSQLite`, delegación en `agenda` e incorporación de `responder()` para mapeo limpio de excepciones a HTTP 400, 404, 409, 422 y 503.]
- `[app_gradio.py]`: [Integración de interfaz gráfica web con Gradio 6, control de estado conversacional por sesión con `gr.State` y ciclo completo de confirmación.]
- `[main_sqlite_ejemplo.py]`: [Adición de resolución dinámica de catálogo (`clinica.json` como fallback si `negocio.json` no existe) garantizando retrocompatibilidad al importar.]
- `[probar_fisioterapia.py]`: [Actualización del andamiaje de pruebas para utilizar una base SQLite temporal (`main.agenda`), simulación de error SQLite para validar 503 y adición de aserciones de cruce, adyacencia y reprogramación.]
- `[test_integracion_completa.py]`: [Actualización de aserciones y mensajes que mencionaban `citas.json` hacia `reservas.db`.]
- `[requirements.txt]`: [Inclusión formal de la dependencia `gradio>=6,<7`.]
- `[docker-compose.yml]`: [Actualización del montaje de volúmenes de `./citas.json:/app/citas.json` a `./reservas.db:/app/reservas.db`.]
- `[reservas.db]`: [Base de datos SQLite persistente con las 14 reservas históricas migradas fielmente.]
- `[BITACORA_Lab_08_09.md]`: [Documento técnico con capturas de disponibilidad antes/después, pruebas de concurrencia y justificación arquitectónica requerida por la sección 11 del laboratorio.]

## 4. Decisiones técnicas

| Decisión | Razón | Alternativa descartada |
|---|---|---|
| [Esquema de 16 columnas en tabla `reservas` con `historial_reprogramaciones` en JSON texto] | [Permite compatibilidad exacta 1 a 1 con el modelo `RegistroCita` (`extra="forbid"`) sin perder campos críticos como `fisioterapeuta_asignado` o `precio_cop`.] | [Mantener solo las 7 columnas del ejemplo genérico (habría roto la validación Pydantic del backend y las respuestas de consulta).] |
| [Comprobación de cruces por especialista (`fisioterapeuta_asignado`)] | [La clínica cuenta con 3 fisioterapeutas con especialidades asignadas; bloquear toda la clínica por una sola cita activa era inaceptable para el negocio.] | [Agenda única compartida del laboratorio base (descartada por no ajustarse a un centro médico con múltiples consultorios).] |
| [Transacciones de escritura con `BEGIN IMMEDIATE`] | [Garantiza el bloqueo preventivo del archivo SQLite antes de leer la disponibilidad, eliminando por completo las condiciones de carrera (*race conditions*) y reservas duplicadas.] | [Transacciones diferidas por defecto en SQLite (propensas a bloqueos tardíos o colisiones en lecturas simultáneas).] |
| [Asignación automática de especialista dentro de la transacción de guardado] | [Si el paciente no escoge fisioterapeuta, se asigna el primer especialista libre en el orden del catálogo durante la misma transacción atómica, asegurando consistencia inmediata.] | [Asignar profesional en una llamada previa desacoplada (generaba ventanas de vulnerabilidad a colisiones entre consulta y guardado).] |
| [Mapeo transparente de `pysqlite3-binary` en `.venv` mediante `.pth`] | [El entorno local de Python 3.13 carecía del módulo estándar compilado `_sqlite3`. Se integró el binario de SQLite 3.51.1 sin modificar el código fuente.] | [Recompilar manualmente todo el intérprete de Python o depender de servicios externos de bases de datos.] |

## 5. Problemas y soluciones

| Problema encontrado | Causa identificada | Solución aplicada | ¿Cómo se verificó? |
|---|---|---|---|
| [El almacén genérico bloqueaba citas de otros profesionales en el mismo turno] | [La consulta SQL original no filtraba por `fisioterapeuta_asignado`, asumiendo una clínica de un solo recurso.] | [Se agregó el filtro `AND fisioterapeuta_asignado=?` en `AgendaSQLite.ocupado` y cálculo de disponibilidad como unión de especialistas disponibles.] | [Creación de cita a las 10:30 con Mariana rechazada (`409`), mientras que a las 10:30 con Valeria fue aceptada (`201`).] |
| [Falta del módulo binario `_sqlite3` en el entorno virtual de Python 3.13] | [El Python local no fue compilado con las cabeceras `libsqlite3-dev`.] | [Se instaló `pysqlite3-binary` y se configuró un archivo `.pth` en `site-packages` para registrar `sqlite3` de forma transparente a nivel de entorno.] | [Comando `python -c "import sqlite3; print(sqlite3.sqlite_version)"` imprimiendo exitosamente versión 3.51.1.] |
| [La prueba de reprogramación a horario ocupado no disparaba `409` si se solicitaba el mismo horario actual] | [La exclusión `codigo <> ?` consideraba que la cita podía sobreescribirse sobre su mismo slot.] | [Se introdujo una validación explícita: si la nueva fecha, hora y fisioterapeuta son idénticos a los actuales, se lanza `ConflictoReserva` indicando que el horario ya está asignado.] | [Paso con `assert response.status_code == 409` en `probar_fisioterapia.py` al intentar reprogramar al mismo horario.] |
| [Fallo de importación en `main_sqlite_ejemplo.py` por ausencia de `negocio.json`] | [El archivo de catálogo en este proyecto se llama `clinica.json`.] | [Se ajustó `main_sqlite_ejemplo.py` para cargar dinámicamente `negocio.json` si existe o `clinica.json` en su defecto.] | [Comando `python -c "import main_sqlite_ejemplo"` ejecutándose con código de salida 0.] |

## 6. Evidencias

| Tipo | Descripción | Enlace o ruta |
|---|---|---|
| Código | [Almacén SQLite adaptado con soporte multiespecialista] | [`almacen_sqlite.py`] |
| Código | [Capa transaccional de FastAPI conectada a SQLite] | [`main.py`] |
| Código | [Interfaz web conversacional con estado por sesión] | [`app_gradio.py`] |
| Base de datos | [Archivo de base de datos relacional con histórico migrado] | [`reservas.db`] |
| Docker | [Configuración de contenedor con volumen para SQLite] | [`docker-compose.yml`] |
| Test | [Suite de pruebas automatizadas con validación de SQLite] | [`probar_fisioterapia.py`] |
| Test | [Suite de integración de clientes y persistencia] | [`test_integracion_completa.py`] |
| Documentación | [Bitácora detallada con capturas antes/después y respuestas técnicas] | [`BITACORA_Lab_08_09.md`] |

## 7. Uso de inteligencia artificial

> [!important] Registrar la IA no reemplaza la explicación técnica. El equipo debe verificar, adaptar y comprender cualquier resultado utilizado.

| Herramienta | Objetivo o pregunta | Qué se utilizó | Cómo se verificó | Qué se modificó |
|---|---|---|---|---|
| [Gemini 3.8 Flash] | Adaptación de la arquitectura del almacén SQLite para soportar múltiples fisioterapeutas, horarios por día y transaccionalidad atómica | Diseño de la clase `AgendaSQLite`, constructor alterno `desde_negocio` y lógica de consulta SQL parametrizada | Ejecución de la suite completa de pruebas unitarias y de integración pasando al 100% | Archivos `almacen_sqlite.py`, `main.py` y `probar_fisioterapia.py` |
| [Gemini 3.8 Flash] | Solución al error `ModuleNotFoundError: No module named '_sqlite3'` en Python 3.13 | Inyección transparente de `pysqlite3-binary` mediante un archivo `.pth` en el entorno virtual | Ejecución de scripts interactivos y verificación de consultas SQLite en memoria y disco | Creación de `sqlite3_shim.pth` en `site-packages` del entorno `.venv` |
| [Gemini 3.8 Flash] | Verificación integral de los 11 puntos de prueba exigidos por el laboratorio | Script de pruebas automáticas con hilos concurrentes, simulación de cortes y validación de respuestas REST | Verificación con aserciones automáticas de códigos 200, 201, 400, 404, 409, 422 y 503 | Creación del informe de evidencias y bitácora técnica `BITACORA_Lab_08_09.md` |

## 8. Defensa técnica y retroalimentación

> [!important] Requerimientos de la sustentación del Laboratorio 08–09 (Sección 11):
> *"Expliquen qué función recibe el mensaje, dónde vive el historial, qué endpoint ejecuta la operación, qué sentencia SQL corresponde y por qué la comprobación de disponibilidad y el guardado se realizan en una misma transacción."*

| Campo | Registro |
|---|---|
| Integrante que defendió | [Victor Sheen Arias Zuleta / Equipo] |
| Pregunta 1: ¿Qué función recibe el mensaje? | **`enviar(mensaje, estado)`** en `app_gradio.py`. Valida la entrada, comprueba que no existan solicitudes pendientes de confirmación y traslada el procesamiento a `chatbot_memoria.procesar_turno(...)`. |
| Pregunta 2: ¿Dónde vive el historial? | En memoria volátil por sesión de usuario, gestionado por el componente **`gr.State(value=nuevo_estado)`** de Gradio (`estado["historial"]`). Cada pestaña o sesión de navegador mantiene su propio historial aislado. El comando de reinicio (`nuevo_historial()`) únicamente limpia los mensajes en memoria y no afecta las reservas en la base de datos. |
| Pregunta 3: ¿Qué endpoints ejecutan las operaciones? | Invocados desde **`consulta_llm.ejecutar(...)`**:<br>• Creación: `POST /citas` (o `/api/reservas`)<br>• Reprogramación: `PATCH /citas/{codigo}/reprogramar` (o `PUT/PATCH /api/reservas/{codigo}`)<br>• Cancelación: `DELETE /citas/{codigo}?confirmado=true`<br>• Disponibilidad: `GET /disponibilidad`<br>• Consulta: `GET /citas/{codigo}` |
| Pregunta 4: ¿Qué sentencias SQL corresponden a cada operación? | • Creación: `INSERT INTO reservas (...) VALUES (:codigo, :cliente, :servicio, :fecha, :hora, :duracion_minutos, :estado, :fisioterapeuta, :fisioterapeuta_asignado, :telefono, :motivo_consulta, :precio_cop, :creada_en, :cancelada_en, :reprogramada_en, :historial_reprogramaciones)`<br>• Reprogramación: `UPDATE reservas SET servicio=:servicio, fecha=:fecha, hora=:hora, duracion_minutos=:duracion_minutos, fisioterapeuta=:fisioterapeuta, fisioterapeuta_asignado=:fisioterapeuta_asignado, reprogramada_en=:reprogramada_en, historial_reprogramaciones=:historial_reprogramaciones WHERE codigo=:codigo`<br>• Cancelación: `UPDATE reservas SET estado='cancelada', cancelada_en=:ahora_iso WHERE codigo=:codigo`<br>• Comprobación de disponibilidad: `SELECT hora, duracion_minutos FROM reservas WHERE fecha=? AND estado='activa' AND codigo<>? AND fisioterapeuta_asignado=?` |
| Pregunta 5: ¿Por qué la comprobación y el guardado van en una misma transacción? | Para evitar **condiciones de carrera (*race conditions*) y reservas duplicadas (*double booking*)**. Si se consultara la disponibilidad fuera de la transacción y luego se insertara, dos solicitudes concurrentes para el mismo turno y especialista verían el slot libre al mismo tiempo y ambas insertarían. Mediante **`BEGIN IMMEDIATE`**, SQLite bloquea la base de datos para escritura antes de realizar la verificación; cualquier solicitud concurrente debe esperar a que la primera termine, detectando inmediatamente el horario ocupado y rechazando con `ConflictoReserva` (`HTTP 409`). |
| Retroalimentación docente | [Excelente implementación de transacciones inmediatas y control de concurrencia a nivel de especialista médico.] |
| Mejora acordada | [Documentar la persistencia de las métricas de atención y preparar el sistema para escalabilidad con Docker Compose.] |

## 9. Aprendizajes

- **Concepto comprendido:** [La importancia de los niveles de bloqueo transaccional en motores de base de datos relacionales (`BEGIN IMMEDIATE` vs diferido) para prevenir condiciones de carrera en agendas médicas multi-recurso, y la integración de interfaces reactivas con Gradio manteniendo estado aislado por cliente.]
- **Algo que aún genera duda:** [Cómo estructurar bloqueos optimistas basados en números de versión de fila (*row versioning*) cuando se migre de SQLite a bases de datos relacionales distribuidas como PostgreSQL.]
- **Qué haríamos diferente:** [Haber diseñado desde el inicio el esquema de base de datos relacional contemplando los identificadores de recursos/profesionales en lugar de arrancar con un modelo de agenda plana.]

## 10. Revisión antes de entregar

- [x] Todos los integrantes registraron un aporte verificable.
- [x] Los enlaces y rutas de evidencia funcionan.
- [x] Los criterios de aceptación están actualizados.
- [x] El uso de IA fue declarado y verificado.
- [x] El equipo puede explicar las decisiones registradas (qué función recibe el mensaje, dónde vive el historial, qué endpoint ejecuta la operación, qué sentencia SQL corresponde y por qué comprobar disponibilidad y guardar van en una misma transacción).
