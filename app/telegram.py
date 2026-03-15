"""
Telegram API helpers.
"""

import os, logging
import httpx

logger = logging.getLogger(__name__)
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/sendMessage", json={
            "chat_id": chat_id, "text": text,
            "parse_mode": parse_mode, "disable_web_page_preview": True,
        })
    if r.status_code != 200:
        logger.warning(f"sendMessage failed: {r.text[:200]}")
    return r.json()


async def send_message_with_keyboard(chat_id: int, text: str, keyboard: dict,
                                      parse_mode: str = "Markdown") -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/sendMessage", json={
            "chat_id": chat_id, "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
            "reply_markup": keyboard,
        })
    if r.status_code != 200:
        logger.warning(f"sendMessage+keyboard failed: {r.text[:200]}")
    return r.json()


async def edit_message_text(chat_id: int, message_id: int, text: str,
                             parse_mode: str = "Markdown") -> None:
    """Sostituisce testo e rimuove keyboard (usato per conferma finale)."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/editMessageText", json={
            "chat_id": chat_id, "message_id": message_id,
            "text": text, "parse_mode": parse_mode,
            "disable_web_page_preview": True,
            "reply_markup": {"inline_keyboard": []},
        })
    if r.status_code != 200:
        logger.warning(f"editMessageText failed: {r.text[:200]}")


async def edit_message_keyboard(chat_id: int, message_id: int,
                                 keyboard: dict = None) -> None:
    """Aggiorna solo la keyboard (toggle tag)."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/editMessageReplyMarkup", json={
            "chat_id": chat_id, "message_id": message_id,
            "reply_markup": keyboard or {"inline_keyboard": []},
        })
    if r.status_code != 200:
        logger.warning(f"editMessageReplyMarkup failed: {r.text[:200]}")


async def answer_callback(callback_query_id: str, text: str = "") -> None:
    async with httpx.AsyncClient(timeout=5) as c:
        await c.post(f"{BASE}/answerCallbackQuery",
                     json={"callback_query_id": callback_query_id, "text": text})


async def send_typing(chat_id: int) -> None:
    async with httpx.AsyncClient(timeout=5) as c:
        await c.post(f"{BASE}/sendChatAction",
                     json={"chat_id": chat_id, "action": "typing"})
