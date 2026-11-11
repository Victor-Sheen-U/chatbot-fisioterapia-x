"""API de referencia para probar la integración antes de adaptarla al main.py."""

import json
import os
from pathlib import Path

from fastapi import FastAPI

from api_telegram import AgendaTelegram, crear_router

BASE = Path(__file__).resolve().parent
SERVICIOS = json.loads((BASE / "negocio.json").read_text(encoding="utf-8-sig"))["servicios"]
agenda = AgendaTelegram(BASE / "reservas_practica_telegram.db", SERVICIOS)
app = FastAPI(title="Proyecto del equipo. Canal Telegram")
app.include_router(crear_router(agenda, os.environ.get("CHATBOT_API_KEY", "")))
