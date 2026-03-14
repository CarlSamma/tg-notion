# 📚 Telegram → Notion Archiver

Bot Telegram che riceve URL, PDF, immagini e note di testo, le analizza con Claude AI e le archivia automaticamente su Notion con titolo riformulato, bullet points, tag e metadati.

---

## Indice

- [Funzionalità](#funzionalità)
- [Architettura](#architettura)
- [Prerequisiti](#prerequisiti)
- [Setup locale](#setup-locale)
- [Configurazione Notion](#configurazione-notion)
- [Configurazione Telegram](#configurazione-telegram)
- [Variabili d'ambiente](#variabili-dambiente)
- [Avvio in locale con Ngrok](#avvio-in-locale-con-ngrok)
- [Debug con VS Code](#debug-con-vs-code)
- [Deploy su Railway](#deploy-su-railway)
- [Flusso utente](#flusso-utente)
- [Schema database Notion](#schema-database-notion)
- [Troubleshooting](#troubleshooting)
- [Suggerimenti di miglioramento](#suggerimenti-di-miglioramento)

---

## Funzionalità

| Input | Elaborazione |
|---|---|
| URL (YouTube, articoli, social) | Fetch contenuto, sintesi AI, archiviazione |
| PDF allegato | Estrazione testo (pypdf), sintesi AI, archiviazione |
| URL diretto a PDF | Download, estrazione testo, sintesi AI, archiviazione |
| Immagine | Descrizione con Claude Vision, archiviazione |
| Testo libero | Archiviazione come nota con sintesi AI |

Per ogni contenuto viene creata su Notion una pagina con:

- Titolo riformulato dall'AI (max 80 caratteri)
- 3–5 bullet points con i punti chiave
- Tag AI generati automaticamente
- Tag aggiuntivi scelti dall'utente via inline keyboard
- Metadati completi: autore, data, lingua, fonte, link al messaggio Telegram originale

---

## Architettura

```
app/
├── main.py        → FastAPI app, endpoint webhook, startup hook
├── handlers.py    → Dispatcher aggiornamenti Telegram, routing per tipo contenuto
├── extractor.py   → Estrazione contenuto da URL, PDF, immagini
├── summarizer.py  → Chiamata Claude API per titolo, bullets, tag
├── notion.py      → Creazione database e pagine Notion
├── tagger.py      → Recupero top-5 tag da Notion, costruzione keyboard inline
├── state.py       → State manager in memoria per sessioni utente (TTL 30 min)
└── telegram.py    → Helper per invio messaggi, keyboard, callback
```

### Flusso tecnico

```
Telegram → webhook POST /webhook/{token}
  → handle_update()
    → classificazione tipo contenuto
    → extract_*_content()
    → summarize_content() [Claude API]
    → _ask_tags() → get_top_tags() [Notion API, cache giornaliera]
    → send_message_with_keyboard() → utente seleziona tag
    → handle_callback() → archive_to_notion() [Notion API]
    → edit_message_keyboard() con link Notion
```

---

## Prerequisiti

- Python 3.11+
- Token bot Telegram (da [@BotFather](https://t.me/BotFather))
- Account Notion con Integration Token
- API Key Anthropic (Claude)
- Ngrok (per test locali del webhook)

---

## Setup locale

### 1. Clona il repository

```bash
git clone https://github.com/CarlSamma/tg-notion.git
cd tg-notion
```

### 2. Crea il virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 4. Copia e configura `.env`

```bash
cp .env.example .env
```

Poi modifica `.env` con i tuoi valori (vedi sezione [Variabili d'ambiente](#variabili-dambiente)).

### 5. Avvia il server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verifica che risponda:

```bash
curl http://localhost:8000/
# → {"status":"ok","service":"tg-notion-archiver"}
```

---

## Configurazione Notion

### Creare l'Integration

1. Vai su [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Clicca **"+ New integration"** → Internal Integration
3. Nome: `Telegram Archiver`
4. Permissions: ✅ Read, ✅ Update, ✅ Insert content
5. Copia il token — questo è il tuo `NOTION_TOKEN`

### Collegare l'Integration a una pagina

Se vuoi che il database venga creato dentro una pagina specifica:

1. Apri la pagina Notion target
2. Menu `...` in alto a destra → **"Add connections"** → seleziona `Telegram Archiver`
3. Copia l'ID dalla URL: `https://www.notion.so/<PAGE_ID>?v=...`
   Questo è il tuo `NOTION_PARENT_PAGE_ID`

Se non imposti `NOTION_PARENT_PAGE_ID`, il database viene creato nella workspace root.

---

## Configurazione Telegram

### Creare il bot

1. Apri [@BotFather](https://t.me/BotFather) su Telegram
2. Invia `/newbot` e segui le istruzioni
3. Copia il token — questo è il tuo `TELEGRAM_TOKEN`

### Canale vs chat privata

Per avere i link ai messaggi originali funzionanti, è necessario usare un **canale** o un **gruppo** (non la chat privata col bot):

**Canale privato (consigliato):**
1. Crea un canale privato su Telegram
2. Vai sulle impostazioni del canale → Amministratori → Aggiungi il bot
3. Permesso minimo: ✅ Leggi messaggi
4. Invia i contenuti da archiviare nel canale (il bot li riceve come `channel_post`)

I link generati avranno il formato `https://t.me/c/<id_numerico>/<message_id>` e funzioneranno per tutti i membri del canale.

---

## Variabili d'ambiente

| Variabile | Obbligatoria | Descrizione |
|---|---|---|
| `TELEGRAM_TOKEN` | ✅ | Token del bot da @BotFather |
| `NOTION_TOKEN` | ✅ | Integration token da notion.so/my-integrations |
| `ANTHROPIC_API_KEY` | ✅ | API key da console.anthropic.com |
| `NOTION_PARENT_PAGE_ID` | ❌ | ID pagina Notion dove creare il database |
| `WEBHOOK_SECRET` | ❌ | Stringa random per proteggere l'endpoint webhook |

Genera un `WEBHOOK_SECRET` sicuro con:
```bash
openssl rand -hex 20
```

---

## Avvio in locale con Ngrok

Telegram richiede un URL pubblico HTTPS per i webhook. Ngrok crea un tunnel locale.

### 1. Installa e avvia Ngrok

```bash
# macOS con Homebrew
brew install ngrok

# Oppure scarica da https://ngrok.com/download
ngrok http 8000
```

### 2. Copia l'URL HTTPS

```
Forwarding  https://abc123.ngrok.io → http://localhost:8000
```

### 3. Registra il webhook

Con il server in esecuzione, apri nel browser:

```
https://abc123.ngrok.io/setup-webhook
```

Risposta attesa:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

**Nota:** l'URL Ngrok cambia a ogni riavvio. Devi chiamare `/setup-webhook` ogni volta.

### 4. Testa il bot

Invia nel canale (o direttamente al bot):
```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

---

## Debug con VS Code

Il file `.vscode/launch.json` include tre configurazioni pronte:

- **Debug Server** — avvia uvicorn con debugger attaccato
- **Debug Server (Auto-reload)** — con hot reload (i breakpoint non persistono al reload)
- **Debug Current File** — esegue il file aperto

**Come aggiungere un breakpoint:**

1. Apri un file Python (es. `app/handlers.py`)
2. Clicca sul margine sinistro accanto al numero di riga
3. Premi `F5` → seleziona "Debug Server"
4. Invia un messaggio al bot: l'esecuzione si fermerà al breakpoint

**Comandi debugger:**

| Tasto | Azione |
|---|---|
| `F10` | Step over (riga successiva) |
| `F11` | Step into (entra nella funzione) |
| `F5` | Continua fino al prossimo breakpoint |
| `Shift+F5` | Ferma il debugger |

---

## Deploy su Railway

Vedi [RAILWAY.md](RAILWAY.md) per la guida completa al deploy.

---

## Flusso utente

```
Utente invia contenuto nel canale
    ↓
Bot mostra anteprima:
  📋 *Titolo riformulato*
  • Punto chiave 1
  • Punto chiave 2
  • Punto chiave 3
  🏷️ Tag AI: #machinelearning #python
  
  ➕ Vuoi aggiungere tag dalla tua libreria?
  [🏷️ tag1] [🏷️ tag2]
  [🏷️ tag3] [🏷️ tag4]
  [➡️ Archivia senza tag aggiuntivi]
    ↓
Utente seleziona tag (toggle: 🏷️ → ✅)
    ↓
Utente preme "Archivia"
    ↓
Bot archivia su Notion e aggiorna il messaggio:
  ✅ *Titolo*
  🏷️ #tag1 #tag2 #machinelearning
  🔗 Apri su Notion
```

---

## Schema database Notion

Il database "Archivio Telegram" viene creato automaticamente all'avvio con questo schema:

| Campo | Tipo | Descrizione |
|---|---|---|
| Nome | Title | Titolo riformulato dall'AI |
| URL | URL | Link alla fonte originale |
| Link Telegram | URL | Link diretto al messaggio originale |
| Tipo | Select | Categoria (YouTube, PDF, Articolo, ecc.) |
| Tag | Multi-select | Tag AI + tag scelti dall'utente |
| Autore | Rich text | Autore del contenuto (se disponibile) |
| Data Contenuto | Date | Data di pubblicazione originale |
| Data Archiviazione | Date | Data di archiviazione |
| Lingua | Select | Lingua rilevata dal contenuto |

---

## Troubleshooting

**Il bot non risponde**
- Verifica che il webhook sia registrato: `https://api.telegram.org/bot{TOKEN}/getWebhookInfo`
- Controlla i log del server per errori

**Notion 401 Unauthorized**
- Verifica che il `NOTION_TOKEN` inizi con `ntn_` o `secret_`
- Controlla che l'integration sia collegata alla pagina target

**Notion 400 Bad Request**
- Verifica che `NOTION_PARENT_PAGE_ID` sia corretto (32 caratteri hex)
- Assicurati che l'integration abbia accesso alla pagina padre

**Link Telegram non funziona**
- Usa un canale o un gruppo, non la chat privata col bot
- Il bot deve essere aggiunto come amministratore con permesso di lettura

**Errore JSON parse da Claude**
- Comportamento normale su contenuti molto brevi o malformati
- Il fallback usa il titolo originale con un bullet generico

**Ngrok URL scaduto**
- Riavvia Ngrok e chiama di nuovo `/setup-webhook`

---

## Suggerimenti di miglioramento

Vedi la sezione dedicata nel file [RAILWAY.md](RAILWAY.md) per il contesto di produzione, oppure leggi i dettagli tecnici di seguito.

### 1. Persistenza dello state con Redis

Attualmente `state.py` usa un dizionario in memoria. Questo significa che se il server si riavvia (cosa normale su Railway), tutti i job pendenti vengono persi. L'utente che stava selezionando i tag riceve un messaggio "sessione scaduta". Con Redis (disponibile come addon Railway) lo state sopravvive ai restart e scala su più istanze.

**File da modificare:** `app/state.py` — sostituire il dict `_pending` con chiamate a `redis.setex()` e `redis.get()`, serializzando i job in JSON. Il set `selected_tags` va convertito in lista per la serializzazione.

### 2. Supporto multi-URL in un singolo messaggio

Oggi se un messaggio contiene più URL (`URL_REGEX.findall(text)` in `handlers.py`), il bot li elabora tutti in sequenza ma crea una keyboard separata per ciascuno, generando confusione. Una soluzione migliore è raggruppare tutti gli URL in un unico job e presentare una singola schermata di riepilogo con tag condivisi.

**File da modificare:** `app/handlers.py` — modificare `handle_urls()` per raccogliere tutti i summary e presentarli in un unico messaggio compatto prima della keyboard tag.

### 3. Webhook su canale/gruppo: comando `/lista` per ricerca full-text

Oggi Notion è il solo punto di accesso all'archivio. Aggiungere un comando `/lista <query>` che chiama l'endpoint `POST /v1/databases/{id}/query` con il filtro `filter.rich_text.contains` permetterebbe di cercare nell'archivio direttamente da Telegram, senza aprire Notion.

**File da aggiungere:** `app/commands.py` — gestire i messaggi con `/` in `handlers.py` e reindirizzarli a un handler dedicato che esegue la query Notion e restituisce i risultati formattati.
