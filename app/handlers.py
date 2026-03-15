"""
Handlers v4 — dispatcher Telegram completo.

Flusso per ogni contenuto:
1. Ricevi messaggio → estrai + sintetizza con AI
2. Mostra anteprima + keyboard tag (AI pre-selezionati + libreria + aggiungi custom)
3. Utente interagisce con i pulsanti:
   - Toggle tag AI o libreria (✅/☑️/🏷️)
   - "Aggiungi tag personalizzato" → bot chiede testo → utente scrive tag liberi
   - "Archivia" → salva su Notion con ordine: AI > libreria > custom
4. Conferma con titolo + tag usati + link Notion

Comandi speciali:
  /start   — messaggio di benvenuto
  /status  — statistiche database Notion
  /aiuto   — lista comandi
"""

import os, re, logging
import httpx

from app.extractor  import extract_url_content, extract_pdf_content, extract_image_description
from app.summarizer import summarize_content
from app.notion     import archive_to_notion, ensure_database_exists, NOTION_HEADERS, get_database_id, get_stats
from app.telegram   import (send_message, send_typing, send_message_with_keyboard,
                             edit_message_keyboard, edit_message_text, answer_callback)
from app.tagger     import get_top_tags, build_tag_keyboard, parse_custom_tags
from app.state      import (save_pending, get_pending, toggle_tag, add_custom_tags,
                             set_awaiting_custom, is_awaiting_custom, clear_pending, get_final_tags)

logger = logging.getLogger(__name__)
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
URL_REGEX = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)


# ── Entry point ────────────────────────────────────────────────────────────────

async def handle_update(update: dict):
    # Callback inline keyboard
    if update.get("callback_query"):
        await _handle_callback(update["callback_query"])
        return

    message = update.get("message") or update.get("channel_post")
    if not message:
        return

    chat_id      = message["chat"]["id"]
    text         = (message.get("text") or message.get("caption") or "").strip()
    tg_link      = _build_tg_link(message)

    # ── Modalità "attesa tag custom" ──────────────────────────────────────────
    # Se il bot aspetta tag liberi dall'utente, intercetta il testo prima di
    # qualsiasi altra logica.
    if is_awaiting_custom(chat_id) and text and not text.startswith("/"):
        await _receive_custom_tags(chat_id, text)
        return

    await send_typing(chat_id)

    # ── Comandi ───────────────────────────────────────────────────────────────
    if text.startswith("/"):
        await _handle_command(chat_id, text)
        return

    # ── Routing contenuto ─────────────────────────────────────────────────────
    if message.get("document"):
        doc = message["document"]
        if doc.get("mime_type") == "application/pdf":
            await _handle_pdf(chat_id, doc, text, tg_link)
        else:
            await send_message(chat_id, "⚠️ Documento non supportato. Invia un PDF, URL, immagine o testo.")
        return

    if message.get("voice") or message.get("audio"):
        await send_message(chat_id,
            "🎙️ Audio ricevuto. Trascrizione non ancora disponibile — "
            "inviami la nota vocale come testo o un link al contenuto.")
        return

    if message.get("photo"):
        photo = max(message["photo"], key=lambda p: p.get("file_size", 0))
        await _handle_image(chat_id, photo["file_id"], text, tg_link)
        return

    if text:
        urls = URL_REGEX.findall(text)
        if urls:
            await _handle_urls(chat_id, urls, tg_link)
        else:
            await _handle_note(chat_id, text, tg_link)
        return

    await send_message(chat_id,
        "👋 Inviami un *URL*, un *PDF*, un'*immagine* o una *nota testuale* "
        "e lo archivio su Notion!\n\n/aiuto per la lista comandi.",
        parse_mode="Markdown")


# ── Comandi ────────────────────────────────────────────────────────────────────

async def _handle_command(chat_id: int, text: str):
    cmd = text.split()[0].lower().split("@")[0]

    if cmd == "/start":
        await send_message(chat_id,
            "📚 *Telegram → Notion Archiver*\n\n"
            "Inviami qualsiasi cosa da archiviare:\n"
            "• 🔗 URL (YouTube, articoli, social)\n"
            "• 📄 PDF\n"
            "• 🖼️ Immagini\n"
            "• 📝 Testo libero\n\n"
            "L'AI analizza il contenuto, genera titolo, punti chiave e tag, "
            "poi ti chiede quali tag aggiungere prima di salvare su Notion.\n\n"
            "/aiuto — tutti i comandi\n"
            "/status — statistiche archivio",
            parse_mode="Markdown")

    elif cmd == "/aiuto":
        await send_message(chat_id,
            "📖 *Comandi disponibili*\n\n"
            "/start — benvenuto e istruzioni\n"
            "/status — statistiche del database Notion\n"
            "/aiuto — questo messaggio\n\n"
            "*Come funziona il tagger:*\n"
            "1. Invia un contenuto\n"
            "2. L'AI suggerisce tag (pre-selezionati ✅)\n"
            "3. Aggiungi tag dalla tua libreria 🏷️\n"
            "4. Scrivi tag personalizzati ✏️\n"
            "5. Premi Archivia ✅",
            parse_mode="Markdown")

    elif cmd == "/status":
        await send_typing(chat_id)
        try:
            stats = await get_stats()
            if not stats:
                await send_message(chat_id, "📊 Database ancora vuoto. Inizia ad archiviare!")
                return
            top_tags = " ".join(f"#{t}" for t in stats.get("top_tags", [])) or "—"
            top_cats = ", ".join(stats.get("top_categorie", [])) or "—"
            last = stats.get("last_title", "—")
            await send_message(chat_id,
                f"📊 *Statistiche Archivio*\n\n"
                f"📦 Contenuti totali: *{stats['total']}*\n"
                f"🏷️ Tag più usati: {top_tags}\n"
                f"📂 Categorie top: {top_cats}\n"
                f"🕐 Ultimo archiviato: _{escape(last)}_",
                parse_mode="Markdown")
        except Exception as e:
            await send_message(chat_id, f"❌ Errore statistiche: {e}")

    else:
        await send_message(chat_id, "❓ Comando non riconosciuto. /aiuto per la lista.")


# ── Content handlers ───────────────────────────────────────────────────────────

async def _handle_urls(chat_id: int, urls: list[str], tg_link: str):
    for url in urls:
        await send_typing(chat_id)
        try:
            raw = await extract_url_content(url)
            summary = await summarize_content(raw, source_type=raw.get("type", "web"))
            await _ask_tags(chat_id, summary, source_url=url,
                            source_type=raw.get("type", "web"), tg_link=tg_link)
        except Exception as e:
            logger.error(f"URL {url}: {e}", exc_info=True)
            await send_message(chat_id, f"❌ Errore elaborazione URL:\n`{url}`\n_{e}_",
                               parse_mode="Markdown")


async def _handle_pdf(chat_id: int, doc: dict, caption: str, tg_link: str):
    try:
        pdf_bytes = await _download_tg_file(doc["file_id"])
        raw = await extract_pdf_content(pdf_bytes, doc.get("file_name", "documento.pdf"))
        raw["caption"] = caption
        summary = await summarize_content(raw, source_type="pdf")
        await _ask_tags(chat_id, summary, source_type="pdf",
                        file_name=doc.get("file_name", ""), tg_link=tg_link)
    except Exception as e:
        logger.error(f"PDF: {e}", exc_info=True)
        await send_message(chat_id, f"❌ Errore elaborazione PDF: {e}")


async def _handle_image(chat_id: int, file_id: str, caption: str, tg_link: str):
    try:
        img_bytes = await _download_tg_file(file_id)
        raw = await extract_image_description(img_bytes, caption)
        summary = await summarize_content(raw, source_type="image")
        await _ask_tags(chat_id, summary, source_type="image", tg_link=tg_link)
    except Exception as e:
        logger.error(f"Immagine: {e}", exc_info=True)
        await send_message(chat_id, f"❌ Errore elaborazione immagine: {e}")


async def _handle_note(chat_id: int, text: str, tg_link: str):
    try:
        raw = {
            "type": "note",
            "raw_text": text,
            "title": text[:60] + ("…" if len(text) > 60 else ""),
        }
        summary = await summarize_content(raw, source_type="note")
        await _ask_tags(chat_id, summary, source_type="note", tg_link=tg_link)
    except Exception as e:
        logger.error(f"Nota: {e}", exc_info=True)
        await send_message(chat_id, f"❌ Errore archiviazione nota: {e}")


# ── AItagger flow ──────────────────────────────────────────────────────────────

async def _ask_tags(
    chat_id: int, summary: dict,
    source_url: str = "", source_type: str = "",
    file_name: str = "", tg_link: str = "",
):
    """
    Mostra anteprima + keyboard tag.
    I tag AI sono pre-selezionati nel set selected_tags fin dall'inizio.
    """
    db_id    = await get_database_id()
    top_tags = await get_top_tags(NOTION_HEADERS, db_id) if db_id else []
    ai_tags  = summary.get("tags", [])

    # Pre-seleziona tutti i tag AI
    preselected = set(ai_tags)

    title   = summary.get("title", "…")
    bullets = summary.get("bullets", [])
    cat     = summary.get("categoria", "Altro")

    bullets_text = "\n".join(f"• {b}" for b in bullets[:4])
    ai_tags_text = "  ".join(f"#{t}" for t in ai_tags) or "—"

    preview = (
        f"📋 *{escape(title)}*\n"
        f"📂 _{escape(cat)}_\n\n"
        f"{escape(bullets_text)}\n\n"
        f"🤖 Tag AI: `{escape(ai_tags_text)}`\n\n"
        f"👇 Conferma, aggiungi o rimuovi tag:"
    )

    keyboard = build_tag_keyboard(ai_tags, top_tags, preselected, [])
    msg      = await send_message_with_keyboard(chat_id, preview, keyboard, parse_mode="Markdown")
    msg_id   = msg.get("result", {}).get("message_id")

    save_pending(chat_id, {
        "summary":       summary,
        "source_url":    source_url,
        "source_type":   source_type,
        "file_name":     file_name,
        "tg_link":       tg_link,
        "top_tags":      top_tags,
        "message_id":    msg_id,
        "selected_tags": preselected,  # AI già dentro
        "custom_tags":   [],
    })


async def _handle_callback(callback: dict):
    chat_id    = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    data       = callback.get("data", "")
    cb_id      = callback["id"]

    await answer_callback(cb_id)

    # ── No-op ─────────────────────────────────────────────────────────────────
    if data == "tag:__noop__" or data == "aitag:__noop__":
        return

    # ── Richiesta tag custom ───────────────────────────────────────────────────
    if data == "tag:__add_custom__":
        job = get_pending(chat_id)
        if not job:
            await send_message(chat_id, "⚠️ Sessione scaduta. Invia di nuovo il contenuto.")
            return
        set_awaiting_custom(chat_id, True)
        await send_message(chat_id,
            "✏️ Scrivi i tag da aggiungere, separati da spazio, virgola o #\n"
            "_Esempi: `react hooks`, `#politica, #economia`, `startup-italia`_",
            parse_mode="Markdown")
        return

    # ── Archivia ───────────────────────────────────────────────────────────────
    if data == "tag:__done__":
        job = clear_pending(chat_id)
        if not job:
            return
        await _do_archive(chat_id, message_id, job)
        return

    # ── Toggle tag AI ──────────────────────────────────────────────────────────
    if data.startswith("aitag:"):
        tag = data[6:]
        selected = toggle_tag(chat_id, tag)
        if selected is None:
            return
        await _refresh_keyboard(chat_id, message_id)
        return

    # ── Toggle tag libreria ────────────────────────────────────────────────────
    if data.startswith("tag:"):
        tag = data[4:]
        selected = toggle_tag(chat_id, tag)
        if selected is None:
            return
        await _refresh_keyboard(chat_id, message_id)
        return


async def _receive_custom_tags(chat_id: int, text: str):
    """Riceve il testo con i tag custom e aggiorna keyboard."""
    tags = parse_custom_tags(text)
    if not tags:
        await send_message(chat_id,
            "⚠️ Nessun tag valido trovato. Riprova (min 2 caratteri, solo lettere/numeri/-/_)")
        return

    ok = add_custom_tags(chat_id, tags)
    set_awaiting_custom(chat_id, False)

    if not ok:
        await send_message(chat_id, "⚠️ Sessione scaduta. Invia di nuovo il contenuto.")
        return

    job = get_pending(chat_id)
    if not job:
        return

    added = "  ".join(f"#{t}" for t in tags)
    await send_message(chat_id, f"✅ Tag aggiunti: `{added}`\nOra premi *Archivia* nella scheda sopra.",
                       parse_mode="Markdown")

    # Aggiorna keyboard con i nuovi custom tag visibili
    await _refresh_keyboard(chat_id, job["message_id"])


async def _refresh_keyboard(chat_id: int, message_id: int):
    """Rigenera la keyboard con lo stato corrente del job."""
    job = get_pending(chat_id)
    if not job:
        return
    keyboard = build_tag_keyboard(
        ai_tags    = job["summary"].get("tags", []),
        top_tags   = job.get("top_tags", []),
        selected   = job["selected_tags"],
        custom_tags= job.get("custom_tags", []),
    )
    await edit_message_keyboard(chat_id, message_id, keyboard=keyboard)


async def _do_archive(chat_id: int, message_id: int, job: dict):
    """Esegue l'archiviazione finale su Notion e aggiorna il messaggio."""
    summary    = job["summary"]
    final_tags = get_final_tags(job)

    try:
        notion_url = await archive_to_notion(
            summary,
            source_url   = job.get("source_url", ""),
            source_type  = job.get("source_type", ""),
            file_name    = job.get("file_name", ""),
            all_tags     = final_tags,
            telegram_link= job.get("tg_link", ""),
        )
        title     = escape(summary.get("title", "Contenuto"))
        tags_text = "  ".join(f"#{t}" for t in final_tags) or "—"
        cat       = escape(summary.get("categoria", ""))

        await edit_message_text(
            chat_id, message_id,
            text = (
                f"✅ *{title}*\n"
                f"📂 _{cat}_\n"
                f"🏷️ `{tags_text}`\n"
                f"🔗 [Apri su Notion]({notion_url})"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Archiviazione: {e}", exc_info=True)
        # Error recovery: mostra il contenuto elaborato in chat
        title   = escape(summary.get("title", "Contenuto"))
        bullets = "\n".join(f"• {b}" for b in summary.get("bullets", []))
        await send_message(chat_id,
            f"❌ *Errore archiviazione Notion*\n\n"
            f"*{title}*\n{escape(bullets)}\n\n"
            f"_Riprova più tardi o contatta l'amministratore._",
            parse_mode="Markdown")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_tg_link(message: dict) -> str:
    chat      = message.get("chat", {})
    msg_id    = message.get("message_id")
    chat_id   = chat.get("id")
    username  = chat.get("username")
    chat_type = chat.get("type", "")

    if not msg_id:
        return ""
    if username:
        return f"https://t.me/{username}/{msg_id}"
    if chat_id and chat_type in ("group", "supergroup", "channel"):
        nid = str(abs(chat_id))
        if nid.startswith("100"):
            nid = nid[3:]
        return f"https://t.me/c/{nid}/{msg_id}"
    return ""


async def _download_tg_file(file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
            params={"file_id": file_id})
        r.raise_for_status()
        path = r.json()["result"]["file_path"]
        dl = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}")
        dl.raise_for_status()
        return dl.content


def escape(text: str) -> str:
    """Escape caratteri Markdown Telegram."""
    for ch in ["*", "_", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text
