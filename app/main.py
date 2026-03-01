"""
Telegram → Notion Archiver
Webhook handler per Railway deployment
"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing other modules
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

from app.handlers import handle_update
from app.notion import ensure_database_exists

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="TG Notion Archiver")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


@app.on_event("startup")
async def startup():
    """Crea il database Notion se non esiste ancora."""
    try:
        db_id = await ensure_database_exists()
        logger.info(f"✅ Notion database pronto: {db_id}")
    except Exception as e:
        logger.error(f"❌ Errore setup Notion database: {e}")


@app.get("/")
async def health():
    return {"status": "ok", "service": "tg-notion-archiver"}


@app.get("/setup-webhook")
async def setup_webhook(request: Request):
    """Registra il webhook Telegram. Chiama questo endpoint una volta dopo il deploy."""
    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhook/{TELEGRAM_TOKEN}"

    params = {"url": webhook_url}
    if WEBHOOK_SECRET:
        params["secret_token"] = WEBHOOK_SECRET

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            json=params,
            timeout=10,
        )
    data = resp.json()
    logger.info(f"Webhook setup: {data}")
    return data


@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """Riceve aggiornamenti da Telegram."""
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Verifica secret opzionale
    if WEBHOOK_SECRET:
        incoming_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming_secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid secret")

    update = await request.json()
    logger.info(f"Update ricevuto: {update.get('update_id')}")

    try:
        await handle_update(update)
    except Exception as e:
        logger.error(f"Errore handle_update: {e}", exc_info=True)

    # Telegram si aspetta sempre 200
    return JSONResponse(content={"ok": True})
