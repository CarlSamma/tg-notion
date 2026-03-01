"""
AItagger — gestione semi-autonoma dei tag.

Funzionalità:
- get_top_tags(): recupera i 5 tag più usati nel database Notion (cache giornaliera)
- Il risultato viene mostrato all'utente come inline keyboard Telegram
- L'utente può selezionare 0, 1 o più tag → vengono aggiunti ai tag AI
- La cache si aggiorna una volta al giorno
"""

import logging
from datetime import date, datetime
from collections import Counter

import httpx

logger = logging.getLogger(__name__)

# ── Cache in memoria ──────────────────────────────────────────────────────────
# { "date": "2025-01-15", "tags": ["tag1", "tag2", ...] }
_tag_cache: dict = {"date": "", "tags": []}


async def get_top_tags(notion_headers: dict, database_id: str) -> list[str]:
    """
    Restituisce i 5 tag più usati nel database Notion.
    Usa cache giornaliera — query Notion solo se la data è cambiata.
    """
    global _tag_cache

    today = date.today().isoformat()
    if _tag_cache["date"] == today and _tag_cache["tags"]:
        logger.debug("Tag cache hit")
        return _tag_cache["tags"]

    logger.info("Aggiorno cache top tags da Notion...")
    try:
        tags = await _fetch_all_tags(notion_headers, database_id)
        top5 = [tag for tag, _ in Counter(tags).most_common(5)]
        _tag_cache = {"date": today, "tags": top5}
        logger.info(f"Top 5 tags aggiornati: {top5}")
        return top5
    except Exception as e:
        logger.error(f"Errore fetch top tags: {e}")
        # Restituisce cache scaduta se disponibile, altrimenti lista vuota
        return _tag_cache.get("tags", [])


async def _fetch_all_tags(notion_headers: dict, database_id: str) -> list[str]:
    """
    Itera tutte le pagine del database e raccoglie tutti i tag usati.
    Gestisce la paginazione Notion (max 100 per chiamata).
    """
    all_tags = []
    has_more = True
    next_cursor = None

    async with httpx.AsyncClient(timeout=30) as client:
        while has_more:
            body: dict = {"page_size": 100}
            if next_cursor:
                body["start_cursor"] = next_cursor

            resp = await client.post(
                f"https://api.notion.com/v1/databases/{database_id}/query",
                headers=notion_headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                props = page.get("properties", {})
                tag_prop = props.get("Tag", {})
                for tag_obj in tag_prop.get("multi_select", []):
                    name = tag_obj.get("name", "").strip()
                    if name:
                        all_tags.append(name)

            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")

    return all_tags


def build_tag_keyboard(top_tags: list[str]) -> dict:
    """
    Costruisce inline keyboard Telegram con i top tag + pulsante "Nessuno / Continua".
    Ogni tag è un pulsante con callback_data = "tag:<nome>".
    """
    if not top_tags:
        return None

    buttons = []
    # Riga di tag (max 2 per riga per leggibilità)
    for i in range(0, len(top_tags), 2):
        row = []
        for tag in top_tags[i:i+2]:
            row.append({
                "text": f"🏷️ {tag}",
                "callback_data": f"tag:{tag}",
            })
        buttons.append(row)

    # Riga finale: conferma senza tag aggiuntivi
    buttons.append([{
        "text": "➡️ Archivia senza tag aggiuntivi",
        "callback_data": "tag:__none__",
    }])

    return {"inline_keyboard": buttons}


def build_tag_keyboard_with_selected(top_tags: list[str], selected: set[str]) -> dict:
    """
    Keyboard con tag già selezionati evidenziati (✅).
    """
    if not top_tags:
        return None

    buttons = []
    for i in range(0, len(top_tags), 2):
        row = []
        for tag in top_tags[i:i+2]:
            is_sel = tag in selected
            row.append({
                "text": f"✅ {tag}" if is_sel else f"🏷️ {tag}",
                "callback_data": f"tag:{tag}",
            })
        buttons.append(row)

    label = f"➡️ Archivia ({len(selected)} tag extra)" if selected else "➡️ Archivia senza tag aggiuntivi"
    buttons.append([{"text": label, "callback_data": "tag:__done__"}])

    return {"inline_keyboard": buttons}
