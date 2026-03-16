"""
AItagger v2 — gestione tag completa.

Keyboard layout:
┌──────────────────────────────────────────┐
│  🤖 TAG AI (pre-selezionati, togglabili) │
│  [✅ llm-fine-tuning]  [✅ openai]       │
├──────────────────────────────────────────┤
│  ──── dalla tua libreria ────            │
│  [🏷️ startup]  [🏷️ design]             │
│  [🏷️ politica-italiana]                 │
├──────────────────────────────────────────┤
│  [✏️ Aggiungi tag personalizzato]        │
│  [✅ Archivia  (5 tag totali)]           │
└──────────────────────────────────────────┘

Regole ordine tag salvati su Notion:
  1. Tag AI (dal summarizer) — prima
  2. Tag scelti dalla libreria — dopo
  3. Tag custom inseriti dall'utente — in fondo
Deduplicati, max 15.
"""

import logging, re
from datetime import date
from collections import Counter
import httpx

logger = logging.getLogger(__name__)

_tag_cache: dict = {"date": "", "tags": []}
TOP_N = 8  # tag libreria mostrati nella keyboard


async def get_top_tags(notion_headers: dict, database_id: str) -> list[str]:
    """Top-N tag più usati nel database. Cache giornaliera."""
    global _tag_cache
    today = date.today().isoformat()
    if _tag_cache["date"] == today and _tag_cache["tags"]:
        return _tag_cache["tags"]

    logger.info("Refresh cache top tags...")
    try:
        tags = await _fetch_all_tags(notion_headers, database_id)
        top = [tag for tag, _ in Counter(tags).most_common(TOP_N)]
        _tag_cache = {"date": today, "tags": top}
        logger.info(f"Top tags aggiornati: {top}")
        return top
    except Exception as e:
        logger.error(f"Errore fetch top tags: {e}")
        return _tag_cache.get("tags", [])


async def _fetch_all_tags(notion_headers: dict, database_id: str) -> list[str]:
    """Pagina tutto il database raccogliendo tag."""
    all_tags, has_more, cursor = [], True, None
    async with httpx.AsyncClient(timeout=30) as client:
        while has_more:
            body: dict = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            resp = await client.post(
                f"https://api.notion.com/v1/databases/{database_id}/query",
                headers=notion_headers, json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            for page in data.get("results", []):
                for t in page.get("properties", {}).get("Tag", {}).get("multi_select", []):
                    n = t.get("name", "").strip()
                    if n:
                        all_tags.append(n)
            has_more = data.get("has_more", False)
            cursor = data.get("next_cursor")
    return all_tags


def build_tag_keyboard(
    ai_tags: list[str],
    top_tags: list[str],
    selected: set[str],
    custom_tags: list[str],
) -> dict:
    """
    Costruisce la keyboard completa con 3 sezioni:
    - Tag AI (pre-selezionati, togglabili con callback aitag:<nome>)
    - Tag libreria (off di default, callback tag:<nome>)
    - Pulsanti: Aggiungi tag + Archivia
    """
    buttons = []

    # ── Sezione 1: Tag AI ────────────────────────────────────────────────────
    ai_visible = ai_tags[:6]
    if ai_visible:
        for i in range(0, len(ai_visible), 2):
            row = []
            for tag in ai_visible[i:i+2]:
                is_on = tag in selected
                row.append({
                    "text": f"{'✅' if is_on else '☑️'} {tag}",
                    "callback_data": f"aitag:{tag}",
                })
            buttons.append(row)

    # ── Sezione 2: Libreria ───────────────────────────────────────────────────
    ai_set = {t.lower() for t in ai_tags}
    lib_tags = [t for t in top_tags if t.lower() not in ai_set][:6]

    if lib_tags:
        if ai_visible:
            buttons.append([{"text": "──── libreria ────", "callback_data": "tag:__noop__"}])
        for i in range(0, len(lib_tags), 2):
            row = []
            for tag in lib_tags[i:i+2]:
                is_on = tag in selected
                row.append({
                    "text": f"{'✅' if is_on else '🏷️'} {tag}",
                    "callback_data": f"tag:{tag}",
                })
            buttons.append(row)

    # ── Tag custom già aggiunti ───────────────────────────────────────────────
    if custom_tags:
        label = "  ".join(f"#{t}" for t in custom_tags)
        buttons.append([{"text": f"✏️ {label}", "callback_data": "tag:__noop__"}])

    # ── Pulsanti azione ───────────────────────────────────────────────────────
    buttons.append([{"text": "✏️ Aggiungi tag personalizzato", "callback_data": "tag:__add_custom__"}])

    total = _count_total(ai_tags, selected, custom_tags)
    label = f"✅ Archivia  ({total} tag)" if total else "✅ Archivia"
    buttons.append([{"text": label, "callback_data": "tag:__done__"}])

    return {"inline_keyboard": buttons}


def _count_total(ai_tags: list, selected: set, custom: list) -> int:
    seen = {t.lower() for t in ai_tags} | {t.lower() for t in selected} | {t.lower() for t in custom}
    return len(seen)


def parse_custom_tags(text: str) -> list[str]:
    """
    Parsa tag da testo libero.
    Supporta: #tag1 #tag2 | tag1, tag2 | tag1;tag2 | tag1 tag2
    """
    text = text.replace("#", " ")
    parts = re.split(r"[\s,;]+", text)
    tags = []
    for p in parts:
        p = re.sub(r"[^a-z0-9àèéìòùa-z\-_]", "", p.strip().lower().replace(" ", "-"))
        if 2 <= len(p) <= 60:
            tags.append(p)
    return list(dict.fromkeys(tags))[:10]
