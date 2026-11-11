# Matriz de pruebas. Clase 13

**Equipo:** ____________________  
**Repositorio y versión evaluada:** ____________________  
**Fecha de ejecución:** ____________________  
**Negocio y regla de disponibilidad:** ____________________

## Preparación

Usen datos de práctica y dos cuentas privadas del mismo bot. Elijan una fecha futura en que atienda el negocio. Identifiquen las reservas aceptadas por su código y cada intento por su referencia de solicitud.

Las tablas contienen expectativas; los resultados obtenidos y el cumplimiento se completan al ejecutar. Escriban «No ejecutado» si no pudieron probar un caso. No conviertan una expectativa en un resultado sin evidencia.

Antes de cada prueba registren las condiciones previas: cuenta, fecha, servicio, disponibilidad y registros que deben existir. Un caso que deja una reserva puede afectar al siguiente; utilicen horarios independientes o restablezcan datos de práctica de forma controlada.

## Casos mínimos

| Caso | Grupo | Entrada y pasos | Resultado esperado |
|---|---|---|---|
| T01 | Normal | Consultar servicios. | Datos que coincidan con el catálogo de la API. |
| T02 | Normal | Preguntar por el precio de un servicio existente. | Valor correspondiente al negocio, sin datos inventados. |
| T03 | Normal | Consultar disponibilidad de un servicio en una fecha válida. | Horarios obtenidos del servicio de disponibilidad. |
| T04 | Normal | Consultar una reserva propia por su código. | Estado y datos actuales de esa reserva autorizada. |
| T05 | Normal | Continuar una consulta después de confirmar una operación. | El contexto contiene el código y el resultado real devuelto por la API. |
| T06 | Normal | Consultar un precio mientras existe una propuesta pendiente. | Se responde la consulta y se conserva intacta la propuesta vigente. |
| T07 | Incompleta | Preparar una reserva sin fecha en una conversación nueva. | Se pide el dato; no se envía una escritura. |
| T08 | Incompleta | Preparar una reserva sin hora. | Se solicita completar o seleccionar la hora antes de presentar la confirmación final. |
| T09 | Incompleta | Solicitar modificar una reserva sin identificarla. | Se pide el código o se permite elegir entre las reservas autorizadas. |
| T10 | Ambigua | Pedir «cambia esa reserva» cuando hay varias referencias posibles. | Se aclara cuál es la reserva antes de construir una modificación. |
| T11 | Contexto | Alternar mensajes de dos cuentas con solicitudes diferentes. | Cada plan utiliza únicamente los datos de su conversación. |
| T12 | Estado | Reiniciar el chat de Laura mientras Andrés tiene una propuesta pendiente. | Se limpia el estado normal de Laura; la propuesta de Andrés y las reservas confirmadas se conservan. |
| T13 | Estado y permisos | Utilizar desde otra cuenta un código de reserva ajeno. | No se revelan sus datos ni se permite modificarla o cancelarla. |
| T14 | Estado | Pulsar un botón del resumen anterior después de reemplazar la propuesta. | Se rechaza el identificador antiguo y la propuesta nueva permanece sin ejecutar. |
| T15 | Fuera del dominio | Preguntar por un asunto ajeno al negocio. | Orientación sobre el alcance del bot, sin efectos en las reservas. |
| T16 | Fuera del dominio | Solicitar tokens o claves de acceso. | No se entregan credenciales ni se consulta un listado de secretos. |
| T17 | Fuera del dominio | Pedir una tarea técnica sin relación con el servicio del negocio. | Se mantiene el alcance de atención y no se generan acciones de negocio por esa petición. |
| T18 | Operación | Crear una reserva, confirmar y repetir la pulsación. | Un solo registro aceptado para esa solicitud; el segundo evento no repite la escritura. |
| T19 | Operación | Modificar una reserva propia a un horario disponible y confirmar. | Se conserva el código del registro modificado y se comprueban sus nuevos datos en la API. |
| T20 | Operación | Cancelar una reserva propia y confirmar. | El servicio devuelve su estado cancelado y deja de contarla como ocupación. |
| T21 | Operación | Descartar una propuesta completa. | No se ejecuta la operación y la propuesta deja de estar disponible para confirmar. |
| T22 | Operación | Intentar confirmar intervalos que se cruzan desde dos cuentas. | Se acepta como máximo la ocupación compatible con la regla del negocio. |
| T23 | Error | Detener FastAPI durante una consulta de lectura. | Aviso de conexión y ausencia de un resultado de negocio inventado. |
| T24 | Situación límite | Simular que se pierde la respuesta después de enviar una escritura. | Se informa el resultado incierto, se conserva su referencia y se comprueba antes de reenviar. |
| T25 | Error | Modificar una reserva hacia un horario que la API rechaza. | Se informa el rechazo y la reserva original permanece sin cambios. |

T12 se prueba sin una escritura incierta pendiente. La espera obligatoria hasta verificar ese resultado se revisa en T24.

T22 puede probarse primero con dos chats intercalados. Si afirman haber comprobado concurrencia, indiquen además cómo enviaron escrituras HTTP que se superpusieran; el bot procesa actualizaciones secuencialmente.

Para T24, sigan la sección «Resultado incierto» del laboratorio y utilicen `simular_respuesta_perdida.py` con datos de práctica. Para T23 basta detener FastAPI durante una consulta de lectura y volver a iniciarla después.

Si el proyecto utiliza pedidos u otro proceso, adapten los casos de agenda a una restricción real, como cupo o disponibilidad de un recurso. Conserven confirmación, propiedad, persistencia y verificación de errores.

## Resultados del equipo

En «Condiciones» incluyan el estado previo; en «Obtenido», la respuesta y el efecto real. En «Evidencia» enlacen la captura o registro correspondiente. El efecto de una escritura se contrasta con la API o SQLite.

| Caso | Condiciones previas | Resultado obtenido | Cumple: Sí / No / No ejecutado | Evidencia |
|---|---|---|---|---|
| T01 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T02 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T03 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T04 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T05 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T06 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T07 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T08 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T09 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T10 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T11 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T12 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T13 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T14 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T15 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T16 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T17 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T18 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T19 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T20 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T21 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T22 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T23 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T24 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |
| T25 | Por completar | Por ejecutar | No ejecutado | Por adjuntar |

## Registro de fallos y correcciones

Copien esta ficha por cada fallo encontrado:

### Caso y fallo observado

- **Caso:**
- **Resultado esperado y diferencia observada:**
- **Causa localizada en el proyecto:**
- **Corrección aplicada y archivo modificado:**
- **Repetición del caso y evidencia:**
- **Pruebas cercanas de regresión y resultado:**
- **Limitaciones pendientes:**

## Casos adicionales recomendados

Vencimiento de una propuesta; recibo recuperado después de reiniciar el proceso; reserva cambiada mientras se revisaba un resumen; mismo identificador con datos diferentes; confirmación válida después de corregir un botón antiguo.

La matriz final se incorpora al repositorio y se relaciona con la bitácora. Cada integrante debe poder explicar una prueba, el componente que valida su resultado y la evidencia utilizada.
