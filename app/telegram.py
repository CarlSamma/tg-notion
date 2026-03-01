"""
Helper per inviare messaggi e azioni Telegram.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{TG_BASE}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )
    if resp.status_code != 200:
        logger.warning(f"sendMessage failed: {resp.text}")
    return resp.json()


async def send_message_with_keyboard(chat_id: int, text: str, keyboard: dict, parse_mode: str = "Markdown") -> dict:
    """Invia un messaggio con inline keyboard allegata."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{TG_BASE}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            },
        )
    if resp.status_code != 200:
        logger.warning(f"sendMessage+keyboard failed: {resp.text}")
    return resp.json()


async def edit_message_keyboard(
    chat_id: int,
    message_id: int,
    text: str = None,
    keyboard: dict = None,
    parse_mode: str = "Markdown",
) -> None:
    """
    Modifica un messaggio esistente.
    - Se text è fornito: aggiorna testo + rimuove keyboard (usato per conferma finale)
    - Se solo keyboard: aggiorna la keyboard mantenendo il testo
    """
    async with httpx.AsyncClient(timeout=10) as client:
        if text is not None:
            # Sostituisce testo e rimuove keyboard
            resp = await client.post(
                f"{TG_BASE}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                    "reply_markup": {"inline_keyboard": []},
                },
            )
        else:
            # Aggiorna solo la keyboard (toggle tag)
            resp = await client.post(
                f"{TG_BASE}/editMessageReplyMarkup",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": keyboard or {"inline_keyboard": []},
                },
            )
    if resp.status_code != 200:
        logger.warning(f"editMessage failed: {resp.text}")


async def answer_callback(callback_query_id: str, text: str = "") -> None:
    """Risponde a un callback query (elimina spinner sul pulsante)."""
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(
            f"{TG_BASE}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
        )


async def send_typing(chat_id: int) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(
            f"{TG_BASE}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
        )
