"""
Handler principale degli aggiornamenti Telegram.

Flusso aggiornato con AItagger:
1. Utente invia contenuto (URL / PDF / immagine / testo)
2. Bot estrae + sintetizza
3. Bot mostra i 5 tag più usati come inline keyboard
4. Utente seleziona 0+ tag e preme "Archivia"
5. Bot archivia su Notion con tag AI + tag scelti dall'utente
"""

import os
import re
import logging
import httpx

from app.extractor import extract_url_content, extract_pdf_content, extract_image_description
from app.summarizer import summarize_content
from app.notion import archive_to_notion, ensure_database_exists, NOTION_HEADERS, get_database_id
from app.telegram import send_message, send_typing, send_message_with_keyboard, edit_message_keyboard, answer_callback
from app.tagger import get_top_tags, build_tag_keyboard, build_tag_keyboard_with_selected
from app.state import save_pending, get_pending, update_selected_tags, clear_pending

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
URL_REGEX = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)


# ── Entry point ────────────────────────────────────────────────────────────────

async def handle_update(update: dict):
    """Dispatcher principale per aggiornamenti Telegram."""

    # Callback da inline keyboard (scelta tag)
    if update.get("callback_query"):
        await handle_callback(update["callback_query"])
        return

    message = update.get("message") or update.get("channel_post")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "") or message.get("caption", "")
    telegram_link = _build_telegram_link(message)

    await send_typing(chat_id)

    # 1. PDF allegato
    if message.get("document"):
        doc = message["document"]
        if doc.get("mime_type") == "application/pdf":
            await handle_pdf(chat_id, doc, text, telegram_link)
        else:
            await send_message(chat_id, "⚠️ Documento non supportato. Invia un PDF, un URL, un'immagine o testo.")
        return

    # 2. Immagine
    if message.get("photo"):
        photos = message["photo"]
        best = max(photos, key=lambda p: p.get("file_size", 0))
        await handle_image(chat_id, best["file_id"], text, telegram_link)
        return

    # 3. URL nel testo
    if text:
        urls = URL_REGEX.findall(text)
        if urls:
            await handle_urls(chat_id, urls, telegram_link)
            return
        await handle_note(chat_id, text, telegram_link)
        return

    await send_message(chat_id, "👋 Inviami un URL, un PDF, un'immagine o del testo libero e lo archivio su Notion!")


# ── Handlers per tipo di contenuto ────────────────────────────────────────────

async def handle_urls(chat_id: int, urls: list[str], telegram_link: str):
    for url in urls:
        await send_typing(chat_id)
        try:
            raw = await extract_url_content(url)
            summary = await summarize_content(raw, source_type=raw.get("type", "web"))
            await _ask_tags(chat_id, summary, source_url=url, source_type=raw.get("type", "web"), telegram_link=telegram_link)
        except Exception as e:
            logger.error(f"Errore URL {url}: {e}", exc_info=True)
            await send_message(chat_id, f"❌ Impossibile elaborare: `{url}`\n_{e}_", parse_mode="Markdown")


async def handle_pdf(chat_id: int, doc: dict, caption: str, telegram_link: str):
    try:
        pdf_bytes = await download_telegram_file(doc["file_id"])
        raw = await extract_pdf_content(pdf_bytes, doc.get("file_name", "documento.pdf"))
        raw["caption"] = caption
        summary = await summarize_content(raw, source_type="pdf")
        await _ask_tags(chat_id, summary, source_type="pdf", file_name=doc.get("file_name", ""), telegram_link=telegram_link)
    except Exception as e:
        logger.error(f"Errore PDF: {e}", exc_info=True)
        await send_message(chat_id, f"❌ Errore PDF: {e}")


async def handle_image(chat_id: int, file_id: str, caption: str, telegram_link: str):
    try:
        image_bytes = await download_telegram_file(file_id)
        raw = await extract_image_description(image_bytes, caption)
        summary = await summarize_content(raw, source_type="image")
        await _ask_tags(chat_id, summary, source_type="image", telegram_link=telegram_link)
    except Exception as e:
        logger.error(f"Errore immagine: {e}", exc_info=True)
        await send_message(chat_id, f"❌ Errore immagine: {e}")


async def handle_note(chat_id: int, text: str, telegram_link: str):
    try:
        raw = {"type": "note", "content": text, "title": text[:60] + ("…" if len(text) > 60 else "")}
        summary = await summarize_content(raw, source_type="note")
        await _ask_tags(chat_id, summary, source_type="note", telegram_link=telegram_link)
    except Exception as e:
        logger.error(f"Errore nota: {e}", exc_info=True)
        await send_message(chat_id, f"❌ Errore nota: {e}")


# ── AItagger flow ─────────────────────────────────────────────────────────────

async def _ask_tags(
    chat_id: int,
    summary: dict,
    source_url: str = "",
    source_type: str = "",
    file_name: str = "",
    telegram_link: str = "",
):
    """
    Mostra anteprima del contenuto + inline keyboard con i 5 tag più usati.
    Salva il job in attesa nello state manager.
    """
    db_id = await get_database_id()
    top_tags = await get_top_tags(NOTION_HEADERS, db_id) if db_id else []

    ai_tags = summary.get("tags", [])
    title = summary.get("title", "…")
    bullets = summary.get("bullets", [])

    bullets_text = "\n".join(f"  • {b}" for b in bullets[:3])
    ai_tags_text = " ".join(f"#{t}" for t in ai_tags) or "—"

    preview = (
        f"📋 *{escape_md(title)}*\n\n"
        f"{escape_md(bullets_text)}\n\n"
        f"🏷️ Tag AI: {escape_md(ai_tags_text)}\n\n"
    )

    if top_tags:
        preview += "➕ *Vuoi aggiungere tag dalla tua libreria?*\nSeleziona uno o più, poi premi Archivia:"
    else:
        preview += "_Nessun tag in libreria ancora. Archivio direttamente._"

    keyboard = build_tag_keyboard(top_tags) if top_tags else None

    if keyboard:
        msg = await send_message_with_keyboard(chat_id, preview, keyboard, parse_mode="Markdown")
        keyboard_msg_id = msg.get("result", {}).get("message_id")
        save_pending(chat_id, {
            "summary": summary,
            "source_url": source_url,
            "source_type": source_type,
            "file_name": file_name,
            "telegram_link": telegram_link,
            "top_tags": top_tags,
            "message_id": keyboard_msg_id,
        })
    else:
        notion_url = await archive_to_notion(
            summary,
            source_url=source_url,
            source_type=source_type,
            file_name=file_name,
            extra_tags=[],
            telegram_link=telegram_link,
        )
        await send_message(chat_id, f"✅ *{escape_md(title)}*\n🔗 [Apri su Notion]({notion_url})", parse_mode="Markdown")


async def handle_callback(callback: dict):
    """Gestisce le pressioni sui pulsanti inline keyboard (scelta tag)."""
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    data = callback.get("data", "")
    callback_id = callback["id"]

    await answer_callback(callback_id)

    if not data.startswith("tag:"):
        return

    tag_value = data[4:]

    job = get_pending(chat_id)
    if not job:
        await send_message(chat_id, "⚠️ Sessione scaduta. Invia di nuovo il contenuto.")
        return

    # Conferma archiviazione
    if tag_value in ("__none__", "__done__"):
        job = clear_pending(chat_id)
        if not job:
            return

        extra_tags = list(job.get("selected_tags", set()))
        summary = job["summary"]

        try:
            notion_url = await archive_to_notion(
                summary,
                source_url=job.get("source_url", ""),
                source_type=job.get("source_type", ""),
                file_name=job.get("file_name", ""),
                extra_tags=extra_tags,
                telegram_link=job.get("telegram_link", ""),
            )
            title = escape_md(summary.get("title", "Contenuto"))
            all_tags = summary.get("tags", []) + extra_tags
            tags_text = " ".join(f"#{t}" for t in all_tags) or "—"

            await edit_message_keyboard(
                chat_id, message_id,
                text=f"✅ *{title}*\n🏷️ {escape_md(tags_text)}\n🔗 [Apri su Notion]({notion_url})",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Errore archiviazione da callback: {e}", exc_info=True)
            await send_message(chat_id, f"❌ Errore archiviazione: {e}")
        return

    # Toggle tag
    selected = update_selected_tags(chat_id, tag_value)
    if selected is None:
        return

    job = get_pending(chat_id)
    top_tags = job.get("top_tags", [])
    new_keyboard = build_tag_keyboard_with_selected(top_tags, selected)
    if new_keyboard:
        await edit_message_keyboard(chat_id, message_id, keyboard=new_keyboard)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_telegram_link(message: dict) -> str:
    """Costruisce link diretto al messaggio Telegram originale."""
    chat = message.get("chat", {})
    message_id = message.get("message_id")
    chat_id = chat.get("id")
    username = chat.get("username")
    chat_type = chat.get("type", "")

    if not message_id:
        return ""

    if username:
        return f"https://t.me/{username}/{message_id}"
    elif chat_id and chat_type in ("group", "supergroup", "channel"):
        # ID privato gruppo/canale: formato t.me/c/<id_senza_-100>/<msg_id>
        numeric_id = str(abs(chat_id))
        if numeric_id.startswith("100"):
            numeric_id = numeric_id[3:]
        return f"https://t.me/c/{numeric_id}/{message_id}"
    # Chat privata 1:1: nessun link pubblico disponibile
    return ""


async def download_telegram_file(file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
            params={"file_id": file_id},
        )
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]
        dl = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}")
        dl.raise_for_status()
        return dl.content


def escape_md(text: str) -> str:
    for ch in ["*", "_", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text
