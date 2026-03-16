"""
Notion integration v4.

Schema database "Archivio Telegram":
  Nome, URL, Link Telegram, Tipo, Categoria, Tag,
  Autore, Data Contenuto, Data Archiviazione, Lingua

Nessun campo Sentiment.
archive_to_notion() riceve all_tags già ordinata (AI > libreria > custom).
"""

import os, logging
from datetime import date
from urllib.parse import urlparse
import httpx

logger = logging.getLogger(__name__)

NOTION_TOKEN          = os.environ["NOTION_TOKEN"]
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "")
_DATABASE_ID: str     = ""

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

SOURCE_EMOJI = {
    "youtube": "🎬", "vimeo": "🎥", "twitter": "🐦", "threads": "🧵",
    "web": "🌐", "pdf": "📄", "pdf_url": "📄", "image": "🖼️",
    "note": "📝", "audio": "🎙️",
}

CATEGORIA_EMOJI = {
    "Tecnologia": "💻", "Intelligenza Artificiale": "🤖",
    "Business & Startup": "🚀", "Politica & Società": "🏛️",
    "Scienza & Ricerca": "🔬", "Design & Creatività": "🎨",
    "Economia & Finanza": "📈", "Salute & Benessere": "🌿",
    "Cultura & Arte": "🎭", "Sport": "⚽", "Intrattenimento": "🎬",
    "Altro": "📌",
}


# ── Database ───────────────────────────────────────────────────────────────────

async def get_database_id() -> str:
    return _DATABASE_ID


async def ensure_database_exists() -> str:
    global _DATABASE_ID
    if _DATABASE_ID:
        return _DATABASE_ID
    existing = await _search_database("Archivio Telegram")
    if existing:
        _DATABASE_ID = existing
        logger.info(f"DB trovato: {_DATABASE_ID}")
        return _DATABASE_ID
    _DATABASE_ID = await _create_database()
    logger.info(f"DB creato: {_DATABASE_ID}")
    return _DATABASE_ID


async def _search_database(title: str) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post("https://api.notion.com/v1/search", headers=NOTION_HEADERS,
                         json={"query": title, "filter": {"value": "database", "property": "object"}})
        r.raise_for_status()
    for item in r.json().get("results", []):
        tp = item.get("title", [])
        if tp and tp[0].get("plain_text") == title:
            return item["id"]
    return ""


async def _create_database() -> str:
    from app.summarizer import CATEGORIE

    parent = ({"type": "page_id", "page_id": NOTION_PARENT_PAGE_ID}
              if NOTION_PARENT_PAGE_ID else {"type": "workspace", "workspace": True})

    schema = {
        "parent": parent,
        "icon": {"type": "emoji", "emoji": "📚"},
        "title": [{"type": "text", "text": {"content": "Archivio Telegram"}}],
        "properties": {
            "Nome":               {"title": {}},
            "URL":                {"url": {}},
            "Link Telegram":      {"url": {}},
            "Tipo": {"select": {"options": [
                {"name": "🎬 YouTube",      "color": "red"},
                {"name": "🎥 Vimeo",        "color": "blue"},
                {"name": "🐦 Twitter/X",    "color": "blue"},
                {"name": "🧵 Threads",      "color": "purple"},
                {"name": "🌐 Articolo Web", "color": "green"},
                {"name": "📄 PDF",          "color": "orange"},
                {"name": "🖼️ Immagine",    "color": "pink"},
                {"name": "📝 Nota",         "color": "gray"},
                {"name": "🎙️ Audio",       "color": "yellow"},
            ]}},
            "Categoria": {"select": {"options": [
                {"name": f"{CATEGORIA_EMOJI.get(c,'📌')} {c}"} for c in CATEGORIE
            ]}},
            "Tag":                {"multi_select": {"options": []}},
            "Fonte":              {"rich_text": {}},
            "Data Archiviazione": {"date": {}},
            "Lingua":             {"select": {"options": []}},
        },
    }

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://api.notion.com/v1/databases",
                         headers=NOTION_HEADERS, json=schema)
        if r.status_code != 200:
            logger.error(f"Create DB: {r.text[:300]}")
        r.raise_for_status()
    return r.json()["id"]


# ── Archiviazione ──────────────────────────────────────────────────────────────

async def archive_to_notion(
    summary: dict,
    source_url: str    = "",
    source_type: str   = "",
    file_name: str     = "",
    all_tags: list     = None,   # lista finale ordinata: AI > libreria > custom
    telegram_link: str = "",
) -> str:
    global _DATABASE_ID
    if not _DATABASE_ID:
        await ensure_database_exists()

    stype     = source_type or summary.get("source_type", "web")
    url       = source_url or summary.get("source_url", "")
    today     = date.today().isoformat()
    emoji     = SOURCE_EMOJI.get(stype, "📌")
    tipo      = _tipo_label(stype)
    categoria = summary.get("categoria", "Altro")
    cat_label = f"{CATEGORIA_EMOJI.get(categoria,'📌')} {categoria}"
    tags      = all_tags or summary.get("tags", [])
    domain    = _extract_domain(url)

    properties: dict = {
        "Nome":      {"title": [{"type": "text", "text": {"content": summary["title"][:2000]}}]},
        "Tipo":      {"select": {"name": tipo}},
        "Categoria": {"select": {"name": cat_label}},
        "Tag":       {"multi_select": [{"name": t[:100]} for t in tags[:15]]},
        "Data Archiviazione": {"date": {"start": today}},
        "Lingua": {"select": {"name": summary.get("language", "it")}},
    }
    if url:
        properties["URL"] = {"url": url}
    if telegram_link:
        properties["Link Telegram"] = {"url": telegram_link}
    if domain:
        properties["Fonte"] = {"rich_text": [{"type": "text", "text": {"content": domain}}]}

    children = _build_body(summary, stype, url, today, tags, emoji, telegram_link, categoria)

    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS,
                         json={"parent": {"database_id": _DATABASE_ID},
                               "icon": {"type": "emoji", "emoji": emoji},
                               "properties": properties,
                               "children": children})
        if r.status_code != 200:
            logger.error(f"Create page: {r.text[:300]}")
        r.raise_for_status()
    return r.json().get("url", "https://notion.so")


# ── Statistiche ────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    """Statistiche del database per /status."""
    global _DATABASE_ID
    if not _DATABASE_ID:
        return {}

    from collections import Counter
    total, all_tags, all_cats, last_title = 0, [], [], ""
    has_more, cursor = True, None

    async with httpx.AsyncClient(timeout=30) as c:
        while has_more:
            body: dict = {"page_size": 100,
                          "sorts": [{"timestamp": "created_time", "direction": "descending"}]}
            if cursor:
                body["start_cursor"] = cursor
            r = await c.post(f"https://api.notion.com/v1/databases/{_DATABASE_ID}/query",
                             headers=NOTION_HEADERS, json=body)
            r.raise_for_status()
            data = r.json()

            for page in data.get("results", []):
                total += 1
                props = page.get("properties", {})
                for t in props.get("Tag", {}).get("multi_select", []):
                    if n := t.get("name"):
                        all_tags.append(n)
                if cat := props.get("Categoria", {}).get("select"):
                    all_cats.append(cat.get("name", ""))
                if total == 1:
                    tp = props.get("Nome", {}).get("title", [])
                    last_title = tp[0].get("plain_text", "") if tp else ""

            has_more = data.get("has_more", False)
            cursor   = data.get("next_cursor")

    return {
        "total":         total,
        "top_tags":      [t for t, _ in Counter(all_tags).most_common(5)],
        "top_categorie": [c for c, _ in Counter(all_cats).most_common(3)],
        "last_title":    last_title,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """Estrae il nome di dominio fino al TLD (es. 'youtube.com', 'corriere.it')."""
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return ""


def _tipo_label(stype: str) -> str:
    return {
        "youtube": "🎬 YouTube",   "vimeo":   "🎥 Vimeo",
        "twitter": "🐦 Twitter/X", "threads": "🧵 Threads",
        "web":     "🌐 Articolo Web","pdf":    "📄 PDF",
        "pdf_url": "📄 PDF",       "image":   "🖼️ Immagine",
        "note":    "📝 Nota",      "audio":   "🎙️ Audio",
    }.get(stype, "🌐 Articolo Web")


def _rt(text: str) -> dict:
    return {"type": "text", "text": {"content": str(text)[:2000]}}


def _build_body(summary, stype, url, today, tags, emoji, tg_link, categoria) -> list:
    blocks = []

    # ── Punti chiave ──────────────────────────────────────────────────────────
    blocks.append({"object": "block", "type": "heading_2",
                   "heading_2": {"rich_text": [_rt("📌 Punti Chiave")]}})
    for b in summary.get("bullets", []):
        blocks.append({"object": "block", "type": "bulleted_list_item",
                       "bulleted_list_item": {"rich_text": [_rt(b)]}})

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # ── Metadati ──────────────────────────────────────────────────────────────
    blocks.append({"object": "block", "type": "heading_2",
                   "heading_2": {"rich_text": [_rt("ℹ️ Metadati")]}})

    cat_emoji = CATEGORIA_EMOJI.get(categoria, "📌")
    domain    = _extract_domain(url)
    meta = [
        f"Tipo: {_tipo_label(stype)}",
        f"Categoria: {cat_emoji} {categoria}",
        f"Tag: {', '.join('#' + t for t in tags)}",
        f"Lingua: {summary.get('language', 'it').upper()}",
        f"Archiviato il: {today}",
    ]
    if domain:
        meta.insert(0, f"Fonte: {domain}")
    if stype in ("pdf", "pdf_url") and summary.get("pages"):
        meta.append(f"Pagine: {summary['pages']}")
    if stype == "audio" and summary.get("duration"):
        meta.append(f"Durata: {summary['duration']}")

    for line in meta:
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": [_rt(line)]}})

    # Link fonte
    if url:
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": [
                           _rt("🔗 Fonte: "),
                           {"type": "text", "text": {"content": url, "link": {"url": url}}},
                       ]}})

    # Link Telegram
    if tg_link:
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": [
                           _rt("✈️ Messaggio Telegram: "),
                           {"type": "text", "text": {"content": tg_link, "link": {"url": tg_link}}},
                       ]}})

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    # Titolo originale
    orig = summary.get("original_title", "")
    if orig and orig != summary.get("title"):
        blocks.append({"object": "block", "type": "callout",
                       "callout": {
                           "icon": {"type": "emoji", "emoji": "💡"},
                           "rich_text": [_rt(f"Titolo originale: {orig}")],
                           "color": "gray_background",
                       }})
    return blocks
