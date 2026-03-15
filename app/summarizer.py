"""
Summarizer v4 — Claude API.
Genera: title, bullets, tags, categoria, language.
Sentiment: RIMOSSO.
"""

import os, json, logging, httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SOURCE_LABELS = {
    "youtube": "Video YouTube", "vimeo":   "Video Vimeo",
    "twitter": "Post Twitter/X","threads": "Post Threads",
    "web":     "Articolo Web",  "pdf":     "Documento PDF",
    "pdf_url": "Documento PDF", "image":   "Immagine",
    "note":    "Nota",
}

CHAR_LIMITS = {
    "web": 9000, "youtube": 9000, "vimeo": 9000,
    "twitter": 6000, "threads": 6000,
    "pdf": 10000, "pdf_url": 10000,
    "image": 6000, "note": 6000,
}

CATEGORIE = [
    "Tecnologia", "Intelligenza Artificiale", "Business & Startup",
    "Politica & Società", "Scienza & Ricerca", "Design & Creatività",
    "Economia & Finanza", "Salute & Benessere", "Cultura & Arte",
    "Sport", "Intrattenimento", "Altro",
]


def build_prompt(raw: dict, source_type: str) -> str:
    label = SOURCE_LABELS.get(source_type, "Contenuto")
    char_limit = CHAR_LIMITS.get(source_type, 6000)
    categorie_str = ", ".join(f'"{c}"' for c in CATEGORIE)

    parts = []
    if raw.get("title"):        parts.append(f"TITOLO ORIGINALE: {raw['title']}")
    if raw.get("author"):       parts.append(f"AUTORE: {raw['author']}")
    if raw.get("published_date"): parts.append(f"DATA: {raw['published_date']}")
    if raw.get("description"):  parts.append(f"DESCRIZIONE: {raw['description']}")
    if raw.get("caption"):      parts.append(f"CAPTION: {raw['caption']}")
    if raw.get("raw_text"):     parts.append(f"CONTENUTO:\n{raw['raw_text'][:char_limit]}")

    content_block = "\n\n".join(parts)

    return f"""Sei un archivista AI specializzato nella catalogazione di contenuti per un database Notion personale.

Analizza questo {label} e restituisci SOLO un oggetto JSON valido con questa struttura:

{{
  "title": "Titolo originale e descrittivo, max 80 caratteri. Non copiare il titolo originale verbatim.",
  "bullets": [
    "Punto 1: idea chiave specifica con dati/fatti concreti se disponibili",
    "Punto 2: idea chiave specifica con dati/fatti concreti se disponibili",
    "Punto 3: idea chiave specifica con dati/fatti concreti se disponibili"
  ],
  "tags": ["tag-specifico-1", "tag-specifico-2", "tag-specifico-3"],
  "categoria": "una categoria",
  "language": "it"
}}

REGOLE OBBLIGATORIE:
- title: max 80 caratteri. Cattura l'essenza in modo originale e informativo.
- bullets: 3-5 punti. Frasi complete con informazioni SPECIFICHE. Vietato: "Il video parla di...", genericità, ripetizioni.
- tags: 3-6 tag SPECIFICI senza #, in minuscolo, con trattini per le parole composte.
  OTTIMI: "llm-fine-tuning", "serie-a-calcio", "politica-italiana", "startup-fundraising", "react-hooks"
  VIETATI: "video", "articolo", "web", "news", "contenuto", "link", "post"
- categoria: scegli ESATTAMENTE una tra: {categorie_str}
- language: codice ISO 639-1 (it, en, es, fr, de, ...)
- Rispondi SOLO con il JSON. Zero testo prima o dopo. Zero markdown fence.

--- CONTENUTO ---
{content_block}
"""


async def summarize_content(raw: dict, source_type: str = "web") -> dict:
    prompt = build_prompt(raw, source_type)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()

    raw_text = resp.json()["content"][0]["text"].strip()

    # Pulizia fence markdown
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        raw_text = parts[1][4:] if parts[1].startswith("json") else parts[1]
    raw_text = raw_text.strip()

    try:
        summary = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e} | risposta: {raw_text[:300]}")
        summary = {
            "title": (raw.get("title") or "Contenuto archiviato")[:80],
            "bullets": ["Contenuto archiviato — vedi pagina Notion per i dettagli."],
            "tags": [source_type],
            "categoria": "Altro",
            "language": "it",
        }

    # Normalizza tag: lowercase, trattini, no caratteri strani
    import re
    clean_tags = []
    for t in summary.get("tags", []):
        t = re.sub(r"[^a-z0-9àèéìòùa-z\-_]", "", t.lower().replace(" ", "-"))
        if 2 <= len(t) <= 60:
            clean_tags.append(t)
    summary["tags"] = list(dict.fromkeys(clean_tags))[:6]

    # Validazione categoria
    if summary.get("categoria") not in CATEGORIE:
        summary["categoria"] = "Altro"

    # Metadati passthrough
    summary.update({
        "source_type":    source_type,
        "original_title": raw.get("title", ""),
        "source_url":     raw.get("source_url", ""),
        "author":         raw.get("author", ""),
        "published_date": raw.get("published_date", ""),
        "file_name":      raw.get("file_name", ""),
        "pages":          raw.get("pages", 0),
        "duration":       raw.get("duration", ""),
    })

    return summary
