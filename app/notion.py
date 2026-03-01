"""
Notion integration:
- ensure_database_exists(): crea il database se non esiste (chiamato all'avvio)
- archive_to_notion(): crea una pagina con il summary strutturato
- get_database_id(): restituisce l'ID del database corrente

Modifiche v2:
- Sentiment RIMOSSO da schema e da proprietà pagina
- extra_tags: tag scelti dall'utente via AItagger, uniti ai tag AI
- telegram_link: link al messaggio originale Telegram, salvato in pagina
"""

import os
import logging
from datetime import date
import httpx

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "")

_DATABASE_ID: str = ""

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

SOURCE_EMOJI = {
    "youtube": "🎬",
    "vimeo": "🎥",
    "twitter": "🐦",
    "threads": "🧵",
    "web": "🌐",
    "pdf": "📄",
    "pdf_url": "📄",
    "image": "🖼️",
    "note": "📝",
}


# ── Database setup ─────────────────────────────────────────────────────────────

async def get_database_id() -> str:
    """Restituisce l'ID del database (inizializzato all'avvio)."""
    return _DATABASE_ID


async def ensure_database_exists() -> str:
    global _DATABASE_ID

    if _DATABASE_ID:
        return _DATABASE_ID

    existing = await _search_database("Archivio Telegram")
    if existing:
        _DATABASE_ID = existing
        logger.info(f"Database Notion esistente: {_DATABASE_ID}")
        return _DATABASE_ID

    _DATABASE_ID = await _create_database()
    logger.info(f"Database Notion creato: {_DATABASE_ID}")
    return _DATABASE_ID


async def _search_database(title: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.notion.com/v1/search",
            headers=NOTION_HEADERS,
            json={"query": title, "filter": {"value": "database", "property": "object"}},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

    for r in results:
        title_prop = r.get("title", [])
        if title_prop and title_prop[0].get("plain_text", "") == title:
            return r["id"]
    return ""


async def _create_database() -> str:
    """Crea il database 'Archivio Telegram' — senza campo Sentiment."""

    parent = (
        {"type": "page_id", "page_id": NOTION_PARENT_PAGE_ID}
        if NOTION_PARENT_PAGE_ID
        else {"type": "workspace", "workspace": True}
    )

    schema = {
        "parent": parent,
        "icon": {"type": "emoji", "emoji": "📚"},
        "title": [{"type": "text", "text": {"content": "Archivio Telegram"}}],
        "properties": {
            "Nome": {"title": {}},
            "URL": {"url": {}},
            "Link Telegram": {"url": {}},
            "Tipo": {
                "select": {
                    "options": [
                        {"name": "🎬 YouTube",      "color": "red"},
                        {"name": "🎥 Vimeo",        "color": "blue"},
                        {"name": "🐦 Twitter/X",    "color": "blue"},
                        {"name": "🧵 Threads",      "color": "purple"},
                        {"name": "🌐 Articolo Web", "color": "green"},
                        {"name": "📄 PDF",          "color": "orange"},
                        {"name": "🖼️ Immagine",    "color": "pink"},
                        {"name": "📝 Nota",         "color": "gray"},
                    ]
                }
            },
            "Tag": {"multi_select": {"options": []}},
            "Autore": {"rich_text": {}},
            "Data Contenuto": {"date": {}},
            "Data Archiviazione": {"date": {}},
            "Lingua": {"select": {"options": []}},
        },
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://api.notion.com/v1/databases",
            headers=NOTION_HEADERS,
            json=schema,
        )
        if resp.status_code != 200:
            logger.error(f"Notion create DB error: {resp.text}")
        resp.raise_for_status()

    return resp.json()["id"]


# ── Archiviazione pagina ───────────────────────────────────────────────────────

async def archive_to_notion(
    summary: dict,
    source_url: str = "",
    source_type: str = "",
    file_name: str = "",
    extra_tags: list = None,
    telegram_link: str = "",
) -> str:
    """
    Crea una pagina Notion nel database con il summary.
    extra_tags: tag aggiuntivi scelti dall'utente via AItagger.
    telegram_link: link diretto al messaggio Telegram originale.
    Restituisce l'URL della pagina creata.
    """
    global _DATABASE_ID

    if not _DATABASE_ID:
        await ensure_database_exists()

    stype = source_type or summary.get("source_type", "web")
    url = source_url or summary.get("source_url", "")
    today = date.today().isoformat()
    pub_date = summary.get("published_date", "")
    emoji = SOURCE_EMOJI.get(stype, "📌")
    tipo_label = _tipo_label(stype)

    # Unisce tag AI + tag scelti dall'utente (deduplicati, max 10)
    ai_tags = summary.get("tags", [])
    user_tags = extra_tags or []
    all_tags = list(dict.fromkeys(ai_tags + user_tags))[:10]  # preserva ordine, deduplica

    properties: dict = {
        "Nome": {
            "title": [{"type": "text", "text": {"content": summary["title"][:2000]}}]
        },
        "Tipo": {"select": {"name": tipo_label}},
        "Tag": {
            "multi_select": [{"name": t[:100]} for t in all_tags]
        },
        "Data Archiviazione": {"date": {"start": today}},
        "Lingua": {"select": {"name": summary.get("language", "it")}},
    }

    if url:
        properties["URL"] = {"url": url}

    if telegram_link:
        properties["Link Telegram"] = {"url": telegram_link}

    if summary.get("author"):
        properties["Autore"] = {
            "rich_text": [{"type": "text", "text": {"content": summary["author"][:2000]}}]
        }

    if pub_date:
        try:
            properties["Data Contenuto"] = {"date": {"start": pub_date[:10]}}
        except Exception:
            pass

    bullets = summary.get("bullets", [])
    children = _build_page_content(summary, stype, url, today, bullets, emoji, all_tags, telegram_link)

    payload = {
        "parent": {"database_id": _DATABASE_ID},
        "icon": {"type": "emoji", "emoji": emoji},
        "properties": properties,
        "children": children,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json=payload,
        )
        if resp.status_code != 200:
            logger.error(f"Notion create page error: {resp.text}")
        resp.raise_for_status()

    return resp.json().get("url", "https://notion.so")


def _tipo_label(stype: str) -> str:
    return {
        "youtube": "🎬 YouTube",
        "vimeo":   "🎥 Vimeo",
        "twitter": "🐦 Twitter/X",
        "threads": "🧵 Threads",
        "web":     "🌐 Articolo Web",
        "pdf":     "📄 PDF",
        "pdf_url": "📄 PDF",
        "image":   "🖼️ Immagine",
        "note":    "📝 Nota",
    }.get(stype, "🌐 Articolo Web")


def _rt(text: str) -> dict:
    return {"type": "text", "text": {"content": text[:2000]}}


def _build_page_content(
    summary: dict,
    stype: str,
    url: str,
    today: str,
    bullets: list,
    emoji: str,
    all_tags: list,
    telegram_link: str,
) -> list:
    blocks = []

    # Punti Chiave
    blocks.append({
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [_rt("📌 Punti Chiave")]},
    })
    for b in bullets:
        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [_rt(b)]},
        })

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # Metadati
    blocks.append({
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [_rt("ℹ️ Metadati")]},
    })

    meta_lines = [
        f"Tipo: {_tipo_label(stype)}",
        f"Tag: {', '.join('#' + t for t in all_tags)}",
        f"Lingua: {summary.get('language', 'it').upper()}",
        f"Archiviato il: {today}",
    ]
    if summary.get("author"):
        meta_lines.insert(0, f"Autore: {summary['author']}")
    if summary.get("published_date"):
        meta_lines.append(f"Data pubblicazione: {summary['published_date'][:10]}")
    if stype in ("pdf", "pdf_url") and summary.get("pages"):
        meta_lines.append(f"Pagine PDF: {summary['pages']}")

    for line in meta_lines:
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [_rt(line)]},
        })

    # Link fonte originale
    if url:
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": "🔗 Fonte originale: "}},
                    {"type": "text", "text": {"content": url, "link": {"url": url}}},
                ]
            },
        })

    # Link messaggio Telegram
    if telegram_link:
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": "✈️ Messaggio Telegram: "}},
                    {"type": "text", "text": {"content": telegram_link, "link": {"url": telegram_link}}},
                ]
            },
        })

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # Titolo originale (se diverso)
    orig_title = summary.get("original_title", "")
    if orig_title and orig_title != summary["title"]:
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "💡"},
                "rich_text": [_rt(f"Titolo originale: {orig_title}")],
                "color": "gray_background",
            },
        })

    return blocks
