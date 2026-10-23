---
tipo: bitacora-clase
curso: Electiva 2
periodo: EAM-2026II
equipo: Equipo_Sheen_castaneda_vargas
corte: 1
semana: 1
clase: 1
fecha: 2026-08-31
estado: completado
tags:
  - chatbots
  - bitacora
  - definicion
  - requerimientos
---
# Bitácora — Clase 1 (Definición y Conceptualización de ReekBot)

> [!tip] Cómo usar esta plantilla
> Duplica esta nota al finalizar cada clase y nómbrala `C##_AAAA-MM-DD_Tema`. Completa los campos entre corchetes y conserva enlaces verificables.

## 1. Datos de la sesión

| Campo | Registro |
|---|---|
| Tema | [FisioTerapiaChatBot] |
| Objetivo | [Hacer un chatBot base para venderlo luego en un negocio real] |
| Proyecto | [FisioterapiaChins / VLFisioterapia] |
| Inicio | [09:00 AM] |
| Cierre | [12:00 PM] |

## 2. Participación y responsabilidades

| Integrante | Asistió | Rol de la clase | Responsabilidad asumida | Aporte verificable |
|---|:---:|---|---|---|
| [ValentinCastanedaMarin] | Sí | [Observadora] | [Levantamiento de requisitos y revisión de casos de uso para pacientes] | [Definición de requerimientos y casos de uso en el catálogo inicial] |
| [VictorSheenAriasZuleta] | Sí | [Cabesilla] | [Liderazgo del proyecto, definición del alcance y conceptualización general] | [Estructura base del proyecto y definición del dominio Vl.FisioTerapia.com] |
| [SamuelRojasVargas] | Sí | [ManoDerecha] | [Verificación de especificaciones técnicas y viabilidad de las capacidades] | [Diseño de capacidades del chatbot y verificación técnica inicial] |

## 3. Reto aplicado al proyecto

### Funcionalidad trabajada

| Campo | Registro |
|---|---|
| Nombre del Chatbot | [ReekBot] |
| Dominio | [Vl.FisioTerapia.com] |
| Problema | [FaltaDeAgendarCita] |
| Usuario Objetivo | [Dueño y pacientes de clínica de fisioterapia] |
| Capacidades | [AgendarTerapia, OrientacionAlUsuario, ConsultarDisponibilidad, ConsultarEstadoDeTerapia, ConsultarPrecio, HistorialTerapias, RecibirCuestionamientos] |

### Criterios de aceptación

- [x] [Definición clara del problema de agendamiento y orientación al paciente.]
- [x] [Delimitación de las 7 capacidades centrales del chatbot en el dominio de fisioterapia.]
- [x] [Identificación del usuario objetivo y requisitos funcionales del negocio.]

### Archivos o componentes modificados

- `[clinica.json]`: [Definición de los servicios de fisioterapia, tarifas en COP y horarios.]
- `[citas.json]`: [Estructura base de datos para almacenar el historial de citas.]
- `[prompt_sistema.txt]`: [Diseño del prompt base de orientación y bienvenida al usuario.]

## 4. Decisiones técnicas

| Decisión | Razón | Alternativa descartada |
|---|---|---|
| [Modelo de datos basado en JSON para la clínica] | [Permite iterar rápidamente el catálogo de servicios, precios y horarios sin requerir un SGBD complejo en fase inicial.] | [Base de datos relacional pesada desde el día uno.] |
| [Especialización en fisioterapia y rehabilitación] | [Asegura un nicho comercial claro y viable para resolver la falta de citas automáticas.] | [Chatbot de propósito general sin especialidad definida.] |

## 5. Problemas y soluciones

| Problema encontrado | Causa identificada | Solución aplicada | ¿Cómo se verificó? |
|---|---|---|---|
| [Definición ambigua de los servicios a ofrecer] | [Falta de un catálogo estructurado de tratamientos de rehabilitación.] | [Estructuración formal de 6 servicios con duraciones y tarifas en `clinica.json`.] | [Revisión y validación de las claves de servicio y compatibilidad horaria.] |
| [Riesgo de que el bot prometa diagnósticos médicos] | [Naturaleza abierta del modelo conversacional.] | [Delimitación estricta de las capacidades: solo agendamiento y orientación informativa.] | [Revisión de directrices en el prompt de sistema.] |

## 6. Evidencias

| Tipo | Descripción | Enlace o ruta |
|---|---|---|
| Commit | [Estructuración inicial del proyecto y catálogo clínico] | [Repositorio local del proyecto] |
| Archivo | [Catálogo de servicios y horarios de la clínica] | [`clinica.json`] |
| Archivo | [Diseño inicial del prompt de orientación] | [`prompt_sistema.txt`] |

## 7. Uso de inteligencia artificial

> [!important] Registrar la IA no reemplaza la explicación técnica. El equipo debe verificar, adaptar y comprender cualquier resultado utilizado.

| Herramienta | Objetivo o pregunta | Qué se utilizó | Cómo se verificó | Qué se modificó |
|---|---|---|---|---|
| [ChatGPT / Gemini] | Lluvia de ideas y estructuración de los requerimientos de un centro de fisioterapia | Estructura de servicios típicos de rehabilitación (deportiva, traumatológica, punción seca) | Comparación con centros de salud reales de fisioterapia | Adaptación a tarifas colombianas (COP) y políticas ficticias de atención |

## 8. Defensa técnica y retroalimentación

| Campo | Registro |
|---|---|
| Integrante que defendió | [Victor Sheen Arias Zuleta] |
| Pregunta recibida | [¿Cómo se proyecta la monetización y utilidad del chatbot en un entorno real?] |
| Respuesta resumida | [El bot automatiza la captación y agendamiento 24/7 de pacientes reduciendo la carga de recepción y eliminando citas perdidas por falta de respuesta rápida.] |
| Retroalimentación docente | [Enfoque viable y bien delimitado. Se recomienda aterrizar pronto la capa técnica de backend.] |
| Mejora acordada | [Comenzar el desarrollo de la API transaccional en FastAPI para soportar las capacidades definidas.] |

## 9. Aprendizajes

- **Concepto comprendido:** [La importancia de definir con precisión el dominio y las capacidades del chatbot antes de comenzar a programar.]
- **Algo que aún genera duda:** [Cómo conectar eficientemente el modelo de lenguaje con la base de datos sin generar respuestas inventadas.]
- **Qué haríamos diferente:** [Estructurar las tablas de evidencias y roles con mayor detalle desde el primer momento.]

## 10. Revisión antes de entregar

- [x] Todos los integrantes registraron un aporte verificable.
- [x] Los enlaces y rutas de evidencia funcionan.
- [x] Los criterios de aceptación están actualizados.
- [x] El uso de IA fue declarado y verificado.
- [x] El equipo puede explicar las decisiones registradas.
