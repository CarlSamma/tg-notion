"""
Summarizer: usa Claude API per generare titolo, bullet points e tag.
Sentiment RIMOSSO.
Limite URL/articoli aumentato a 9.000 caratteri.
"""

import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SOURCE_LABELS = {
    "youtube": "Video YouTube",
    "vimeo": "Video Vimeo",
    "twitter": "Post Twitter/X",
    "threads": "Post Threads",
    "web": "Articolo Web",
    "pdf": "Documento PDF",
    "pdf_url": "Documento PDF",
    "image": "Immagine",
    "note": "Nota",
}

# Limite caratteri per tipo sorgente
CHAR_LIMITS = {
    "web":     9000,
    "youtube": 9000,
    "vimeo":   9000,
    "twitter": 6000,
    "threads": 6000,
    "pdf":     10000,
    "pdf_url": 10000,
    "image":   6000,
    "note":    6000,
}


def build_prompt(raw: dict, source_type: str) -> str:
    label = SOURCE_LABELS.get(source_type, "Contenuto")
    char_limit = CHAR_LIMITS.get(source_type, 6000)

    content_parts = []
    if raw.get("title"):
        content_parts.append(f"TITOLO ORIGINALE: {raw['title']}")
    if raw.get("author"):
        content_parts.append(f"AUTORE: {raw['author']}")
    if raw.get("published_date"):
        content_parts.append(f"DATA: {raw['published_date']}")
    if raw.get("description"):
        content_parts.append(f"DESCRIZIONE: {raw['description']}")
    if raw.get("caption"):
        content_parts.append(f"CAPTION UTENTE: {raw['caption']}")
    if raw.get("raw_text"):
        content_parts.append(f"CONTENUTO:\n{raw['raw_text'][:char_limit]}")

    content_block = "\n\n".join(content_parts)

    return f"""Sei un assistente che archivia contenuti su Notion.
Analizza questo {label} e restituisci SOLO un JSON valido con questa struttura:

{{
  "title": "Titolo riformulato, accattivante, max 80 caratteri. Non copiare il titolo originale.",
  "bullets": [
    "Punto chiave 1 — frase completa e informativa",
    "Punto chiave 2 — frase completa e informativa",
    "Punto chiave 3 — frase completa e informativa"
  ],
  "tags": ["tag1", "tag2", "tag3"],
  "language": "it|en|es|fr|de|..."
}}

Regole:
- bullets: 3-5 punti, ognuno autonomo e specifico. Evita genericità.
- tags: 3-5 tag specifici senza #, es. "machinelearning", "politicaitaliana". No tag generici come "video" o "articolo".
- language: codice ISO 639-1 della lingua del contenuto originale.
- Rispondi SOLO con il JSON, nessun testo prima o dopo.

--- CONTENUTO DA ANALIZZARE ---
{content_block}
"""


async def summarize_content(raw: dict, source_type: str = "web") -> dict:
    prompt = build_prompt(raw, source_type)

    async with httpx.AsyncClient(timeout=45) as client:
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
        data = resp.json()

    raw_response = data["content"][0]["text"].strip()

    if raw_response.startswith("```"):
        raw_response = raw_response.split("```")[1]
        if raw_response.startswith("json"):
            raw_response = raw_response[4:]
    raw_response = raw_response.strip()

    try:
        summary = json.loads(raw_response)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nRisposta: {raw_response}")
        summary = {
            "title": raw.get("title", "Contenuto senza titolo")[:80],
            "bullets": ["Contenuto estratto — vedi pagina Notion per dettagli."],
            "tags": [source_type],
            "language": "it",
        }

    # Metadati aggiuntivi
    summary["source_type"] = source_type
    summary["original_title"] = raw.get("title", "")
    summary["source_url"] = raw.get("source_url", "")
    summary["author"] = raw.get("author", "")
    summary["published_date"] = raw.get("published_date", "")
    summary["file_name"] = raw.get("file_name", "")
    summary["pages"] = raw.get("pages", 0)

    return summary
