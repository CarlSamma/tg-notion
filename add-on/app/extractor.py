"""
Estrazione contenuto da diverse sorgenti:
- URL web (articoli, YouTube, social)
- PDF (bytes)
- Immagini (bytes)
"""

import re
import base64
import logging
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Pattern per YouTube
YT_PATTERN = re.compile(
    r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
)


def classify_url(url: str) -> str:
    """Classifica il tipo di URL."""
    domain = urlparse(url).netloc.lower().replace("www.", "")
    if domain in ("youtube.com", "youtu.be"):
        return "youtube"
    if domain == "vimeo.com":
        return "vimeo"
    if domain in ("x.com", "twitter.com"):
        return "twitter"
    if domain == "threads.net":
        return "threads"
    if url.lower().endswith(".pdf"):
        return "pdf_url"
    return "web"


async def extract_url_content(url: str) -> dict:
    """Fetcha e restituisce contenuto grezzo da un URL."""
    url_type = classify_url(url)

    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NotionArchiver/1.0)"},
        follow_redirects=True,
    ) as client:
        if url_type == "pdf_url":
            resp = await client.get(url)
            resp.raise_for_status()
            raw = await extract_pdf_content(resp.content, url.split("/")[-1])
            raw["source_url"] = url
            return raw

        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    content = _strip_html(html)

    result = {
        "type": url_type,
        "source_url": url,
        "raw_text": content[:8000],  # max 8k chars per LLM
        "title": _extract_og_title(html) or _extract_title_tag(html) or url,
        "description": _extract_og_description(html) or "",
        "author": _extract_author(html) or "",
        "published_date": _extract_date(html) or "",
    }

    # Per YouTube aggiungi video ID per eventuale arricchimento futuro
    if url_type == "youtube":
        match = YT_PATTERN.search(url)
        if match:
            result["video_id"] = match.group(1)

    return result


async def extract_pdf_content(pdf_bytes: bytes, file_name: str = "documento.pdf") -> dict:
    """
    Estrae testo da bytes PDF usando pypdf.
    Fallback: restituisce placeholder se pypdf non disponibile.
    """
    try:
        import pypdf
        import io

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages_text.append(text)
            if i >= 49:  # max 50 pagine
                pages_text.append("[... documento troncato dopo 50 pagine ...]")
                break

        full_text = "\n\n".join(pages_text)
        meta = reader.metadata or {}

        return {
            "type": "pdf",
            "file_name": file_name,
            "raw_text": full_text[:10000],
            "title": meta.get("/Title") or file_name.replace(".pdf", ""),
            "author": meta.get("/Author") or "",
            "pages": len(reader.pages),
        }
    except ImportError:
        logger.warning("pypdf non installato, uso placeholder")
        return {
            "type": "pdf",
            "file_name": file_name,
            "raw_text": f"[PDF: {file_name} — testo non estratto, pypdf mancante]",
            "title": file_name.replace(".pdf", ""),
            "author": "",
            "pages": 0,
        }
    except Exception as e:
        logger.error(f"Errore estrazione PDF: {e}")
        return {
            "type": "pdf",
            "file_name": file_name,
            "raw_text": f"[Errore estrazione PDF: {e}]",
            "title": file_name.replace(".pdf", ""),
            "author": "",
            "pages": 0,
        }


async def extract_image_description(image_bytes: bytes, caption: str = "") -> dict:
    """
    Usa Claude vision (via Anthropic API) per descrivere un'immagine.
    """
    import os
    import json
    import httpx

    b64 = base64.standard_b64encode(image_bytes).decode()

    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Descrivi questa immagine in modo dettagliato. "
                            "Indica cosa mostra, eventuale testo visibile, contesto. "
                            + (f'Nota dell\'utente: "{caption}"' if caption else "")
                        ),
                    },
                ],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    description = data["choices"][0]["message"]["content"]

    return {
        "type": "image",
        "raw_text": description,
        "caption": caption,
        "title": caption[:60] if caption else "Immagine",
        "author": "",
    }


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    """Rimuove tag HTML e restituisce testo pulito."""
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def _extract_og_title(html: str) -> str:
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_og_description(html: str) -> str:
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_title_tag(html: str) -> str:
    m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_author(html: str) -> str:
    m = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_date(html: str) -> str:
    m = re.search(r'<meta[^>]+(?:name|property)=["\'](?:article:published_time|datePublished)["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1)[:10] if m else ""


async def transcribe_audio(audio_bytes: bytes, duration_seconds: int = 0) -> dict:
    """
    Trascrive una nota vocale usando Whisper API (OpenAI).
    Fallback: se OPENAI_API_KEY non è impostata, usa Claude per descrivere l'audio.

    Restituisce un dict compatibile con summarize_content().
    """
    import os

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    duration_str = f"{duration_seconds}s" if duration_seconds else "sconosciuta"

    if openai_key:
        # ── Whisper API ───────────────────────────────────────────────────────
        try:
            import io
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    files={"file": ("audio.ogg", io.BytesIO(audio_bytes), "audio/ogg")},
                    data={"model": "whisper-1", "response_format": "text"},
                )
                resp.raise_for_status()
                transcript = resp.text.strip()

            return {
                "type": "audio",
                "raw_text": transcript,
                "title": transcript[:60] + ("…" if len(transcript) > 60 else ""),
                "author": "",
                "duration": duration_str,
            }
        except Exception as e:
            logger.error(f"Errore Whisper API: {e}")
            # Fallback sotto

    # ── Fallback: nessuna trascrizione disponibile ─────────────────────────────
    logger.warning("OPENAI_API_KEY non impostata — audio non trascrivibile. Archiviato come placeholder.")
    return {
        "type": "audio",
        "raw_text": f"[Nota vocale — durata: {duration_str}. Trascrizione non disponibile: imposta OPENAI_API_KEY per abilitare Whisper.]",
        "title": f"Nota vocale ({duration_str})",
        "author": "",
        "duration": duration_str,
    }
