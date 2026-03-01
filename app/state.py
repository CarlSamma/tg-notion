"""
State manager per il flusso AItagger.

Quando un contenuto è pronto per essere archiviato ma aspetta
la scelta dei tag da parte dell'utente, salviamo il "job" in memoria.

Struttura di ogni job:
{
    "summary": {...},          # output del summarizer
    "source_url": str,
    "source_type": str,
    "file_name": str,
    "telegram_link": str,      # link al messaggio originale Telegram
    "selected_tags": set(),    # tag scelti dall'utente via keyboard
    "message_id": int,         # ID del messaggio keyboard inviato dal bot
}

Key: chat_id (int)
Nota: un solo job pendente per chat alla volta (sovrascrive il precedente).
"""

from datetime import datetime, timedelta

# { chat_id: { "job": {...}, "expires": datetime } }
_pending: dict = {}

JOB_TTL_MINUTES = 30  # job scade dopo 30 minuti senza risposta


def save_pending(chat_id: int, job: dict) -> None:
    """Salva un job in attesa per la chat specificata."""
    job.setdefault("selected_tags", set())
    _pending[chat_id] = {
        "job": job,
        "expires": datetime.utcnow() + timedelta(minutes=JOB_TTL_MINUTES),
    }


def get_pending(chat_id: int) -> dict | None:
    """Restituisce il job pendente per la chat, o None se assente/scaduto."""
    entry = _pending.get(chat_id)
    if not entry:
        return None
    if datetime.utcnow() > entry["expires"]:
        del _pending[chat_id]
        return None
    return entry["job"]


def update_selected_tags(chat_id: int, tag: str) -> set[str] | None:
    """
    Aggiunge o rimuove un tag dalla selezione (toggle).
    Restituisce il set aggiornato, o None se job non trovato.
    """
    job = get_pending(chat_id)
    if job is None:
        return None
    selected = job["selected_tags"]
    if tag in selected:
        selected.discard(tag)
    else:
        selected.add(tag)
    return selected


def clear_pending(chat_id: int) -> dict | None:
    """Rimuove e restituisce il job pendente."""
    entry = _pending.pop(chat_id, None)
    return entry["job"] if entry else None
