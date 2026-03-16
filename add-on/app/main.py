"""
FastAPI webhook server — Telegram → Notion Archiver
"""

import os, logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

from app.handlers import handle_update
from app.notion   import ensure_database_exists

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="TG Notion Archiver")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


@app.on_event("startup")
async def startup():
    try:
        db_id = await ensure_database_exists()
        logger.info(f"✅ Notion database: {db_id}")
    except Exception as e:
        logger.error(f"❌ Setup Notion: {e}")


@app.get("/")
async def health():
    return {"status": "ok", "service": "tg-notion-archiver"}


@app.get("/setup-webhook")
async def setup_webhook(request: Request):
    """Registra il webhook Telegram. Chiama una volta dopo il deploy."""
    base = str(request.base_url).rstrip("/")
    webhook_url = f"{base}/webhook/{TELEGRAM_TOKEN}"
    payload = {"url": webhook_url}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET

    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            json=payload, timeout=10)
    data = r.json()
    logger.info(f"Webhook setup: {data}")
    return data


@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    if WEBHOOK_SECRET:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid secret")

    update = await request.json()
    logger.info(f"Update #{update.get('update_id')}")

    try:
        await handle_update(update)
    except Exception as e:
        logger.error(f"handle_update error: {e}", exc_info=True)

    return JSONResponse(content={"ok": True})
