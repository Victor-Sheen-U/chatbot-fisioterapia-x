"""Práctica T24: Simulación de respuesta perdida de red después de persistir en la API.

Ejecutar en lugar de bot_telegram.py, con la misma configuración de entorno.
La API de FastAPI (main.py) debe permanecer en ejecución.
El simulador intercepta la primera respuesta exitosa de escritura (/operaciones)
y lanza un TimeoutError fingiendo pérdida del paquete de respuesta.
El bot reportará estado incierto conservando la referencia.
El usuario verifica mediante `/estado` o `/estado <REFERENCIA>` que el recibo
fue registrado en SQLite sin crear una segunda cita.
"""

import bot_telegram


def main():
    original = bot_telegram.ClienteAPI.ejecutar
    pendiente = True

    def ejecutar_con_perdida(self, *args, **kwargs):
        nonlocal pendiente
        respuesta = original(self, *args, **kwargs)
        if pendiente:
            pendiente = False
            print("\n[SIMULACIÓN T24 ACTIVA]: La API de VLFisioterapia procesó y guardó la reserva.")
            print("[SIMULACIÓN T24 ACTIVA]: Se oculta la respuesta HTTP al bot lanzando TimeoutError.")
            raise TimeoutError("Simulación T24: Respuesta de red perdida después de guardar en base de datos.")
        return respuesta

    bot_telegram.ClienteAPI.ejecutar = ejecutar_con_perdida
    try:
        print("=" * 65)
        print("SIMULADOR T24 — VLFisioterapia (Respuesta de red perdida)")
        print("IMPORTANTE: Utilizar citas y fechas de práctica.")
        print("Al finalizar la prueba, detener con Ctrl+C y volver a bot_telegram.py")
        print("=" * 65)
        bot_telegram.main()
    finally:
        bot_telegram.ClienteAPI.ejecutar = original


if __name__ == "__main__":
    main()
