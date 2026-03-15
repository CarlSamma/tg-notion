"""
State manager — job pendenti e flusso tag custom.

Job structure:
{
    "summary":       dict,      # output summarizer
    "source_url":    str,
    "source_type":   str,
    "file_name":     str,
    "tg_link":       str,
    "top_tags":      list[str], # cache top tag al momento della creazione
    "message_id":    int,       # ID messaggio keyboard
    "selected_tags": set[str],  # tag scelti dalla keyboard (AI + libreria)
    "custom_tags":   list[str], # tag scritti manualmente dall'utente
}

Modalità "awaiting_custom": bot aspetta che l'utente scriva tag in testo libero.
"""

from datetime import datetime, timedelta

_pending: dict = {}
_awaiting_custom: set = set()
JOB_TTL = 60  # minuti


def save_pending(chat_id: int, job: dict) -> None:
    job.setdefault("selected_tags", set())
    job.setdefault("custom_tags", [])
    _pending[chat_id] = {
        "job": job,
        "expires": datetime.utcnow() + timedelta(minutes=JOB_TTL),
    }


def get_pending(chat_id: int) -> dict | None:
    entry = _pending.get(chat_id)
    if not entry:
        return None
    if datetime.utcnow() > entry["expires"]:
        _pending.pop(chat_id, None)
        _awaiting_custom.discard(chat_id)
        return None
    return entry["job"]


def toggle_tag(chat_id: int, tag: str) -> set[str] | None:
    """Toggle tag nella keyboard. Restituisce set aggiornato o None se job scaduto."""
    job = get_pending(chat_id)
    if job is None:
        return None
    s = job["selected_tags"]
    if tag in s:
        s.discard(tag)
    else:
        s.add(tag)
    return s


def add_custom_tags(chat_id: int, tags: list[str]) -> bool:
    """Aggiunge tag custom. Restituisce True se OK."""
    job = get_pending(chat_id)
    if job is None:
        return False
    existing = {t.lower() for t in job["custom_tags"]} | {t.lower() for t in job["selected_tags"]}
    for t in tags:
        t = t.strip().lower()
        if t and t not in existing:
            job["custom_tags"].append(t)
            existing.add(t)
    return True


def set_awaiting_custom(chat_id: int, value: bool) -> None:
    if value:
        _awaiting_custom.add(chat_id)
    else:
        _awaiting_custom.discard(chat_id)


def is_awaiting_custom(chat_id: int) -> bool:
    return chat_id in _awaiting_custom


def clear_pending(chat_id: int) -> dict | None:
    _awaiting_custom.discard(chat_id)
    entry = _pending.pop(chat_id, None)
    return entry["job"] if entry else None


def get_final_tags(job: dict) -> list[str]:
    """
    Restituisce la lista finale di tag nell'ordine corretto:
    1. Tag AI (dal summarizer) — sempre prima
    2. Tag scelti dalla keyboard (libreria)
    3. Tag custom scritti dall'utente
    Deduplicati, max 15.
    """
    ai_tags   = job.get("summary", {}).get("tags", [])
    sel_tags  = list(job.get("selected_tags", set()))
    cust_tags = job.get("custom_tags", [])

    seen, result = set(), []
    for t in ai_tags + sel_tags + cust_tags:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result[:15]
