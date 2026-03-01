# 🛠️ Local Development Guide

Guida completa per eseguire e debuggare il bot Telegram → Notion Archiver in locale.

---

## 📋 Prerequisiti

- **Python 3.11+** installato
- **Account Telegram** e bot creato via [@BotFather](https://t.me/BotFather)
- **Account Notion** con Integration creata
- **Anthropic API Key** per Claude AI
- **Ngrok** (opzionale, per testare il webhook Telegram in locale)

---

## 🚀 Setup Iniziale

### 1. Clona il repository

```bash
git clone https://github.com/CarlSamma/tg-notion.git
cd tg-notion
```

### 2. Crea ambiente virtuale

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 4. Configura le variabili d'ambiente

Copia `.env.example` in `.env`:

```bash
cp .env.example .env
```

Poi modifica `.env` con i tuoi valori reali:

```env
TELEGRAM_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
NOTION_TOKEN="ntn_123456789abcdefghijklmnopqrstuvwxyz"
ANTHROPIC_API_KEY="sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
WEBHOOK_SECRET="random_secret_string_here"
NOTION_PARENT_PAGE_ID="your_notion_page_id_here"
```

**Come ottenere i token:**

- **TELEGRAM_TOKEN**:
  1. Vai su [@BotFather](https://t.me/BotFather)
  2. Invia `/newbot` e segui le istruzioni
  3. Copia il token che ti viene dato

- **NOTION_TOKEN**:
  1. Vai su [notion.so/my-integrations](https://www.notion.so/my-integrations)
  2. Clicca "+ New integration" → "Internal Integration"
  3. Copia il token dalla sezione "Secrets"
  4. IMPORTANTE: Vai sulla pagina Notion dove vuoi il database → `...` → "Connect to" → Seleziona la tua integration

- **ANTHROPIC_API_KEY**:
  1. Vai su [console.anthropic.com](https://console.anthropic.com)
  2. Crea un account e genera una API key

- **NOTION_PARENT_PAGE_ID** (opzionale):
  1. Apri la pagina Notion dove vuoi creare il database
  2. Copia il link della pagina
  3. Estrai l'ID dall'URL: `https://www.notion.so/316b88593c988044b992f198ea858ed0` → ID = `316b88593c988044b992f198ea858ed0`

---

## ▶️ Avvio del Server

### Modalità normale (senza debug)

```bash
# Con auto-reload (rileva modifiche ai file)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Senza auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Il server sarà disponibile su: **http://localhost:8000**

Verifica che funzioni:
```bash
curl http://localhost:8000/
# Risposta: {"status":"ok","service":"tg-notion-archiver"}
```

---

## 🐛 Debug con VS Code

### 1. Apri il progetto in VS Code

```bash
code .
```

### 2. Configurazione già pronta

Il file `.vscode/launch.json` è già configurato con due modalità di debug:

- **Debug Server** - Avvia il server con debugger attaccato
- **Debug Server (Auto-reload)** - Avvia con auto-reload (non supporta breakpoint durante il reload)

### 3. Come usare il debugger

1. Apri un file Python (es. `app/handlers.py`)
2. Clicca sul margine sinistro per aggiungere **breakpoint** (pallino rosso)
3. Premi `F5` o vai su `Run → Start Debugging`
4. Seleziona "Debug Server"
5. Il server si avvia con il debugger attaccato
6. Quando il codice raggiunge un breakpoint, l'esecuzione si ferma e puoi:
   - Ispezionare variabili
   - Eseguire codice nella console di debug
   - Fare step-by-step (`F10` = step over, `F11` = step into)

### 4. Debug dei webhook Telegram

Quando Telegram invia un messaggio al bot:
1. Il webhook viene ricevuto da `/webhook/{token}`
2. Se hai un breakpoint in `handlers.py`, il debugger si ferma lì
3. Puoi ispezionare il payload `update` ricevuto da Telegram

---

## 🌐 Test con Ngrok (per webhook Telegram)

Telegram richiede un URL pubblico HTTPS per i webhook. Ngrok crea un tunnel:

### 1. Avvia Ngrok

**Windows:**
```bash
./ngrok.exe http 8000
```

**macOS/Linux:**
```bash
ngrok http 8000
```

### 2. Copia l'URL HTTPS

Ngrok mostrerà qualcosa come:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

Copia l'URL HTTPS: `https://abc123.ngrok.io`

### 3. Registra il webhook

Apri nel browser:
```
https://abc123.ngrok.io/setup-webhook
```

Dovresti vedere:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

### 4. Testa il bot

Vai su Telegram, trova il tuo bot e invia:
- Un URL (es. `https://www.youtube.com/watch?v=dQw4w9WgXcQ`)
- Un PDF allegato
- Un'immagine
- Del testo libero

Il bot dovrebbe rispondere con un'anteprima e archiviare su Notion!

---

## 🔍 Troubleshooting

### Il server non parte

**Errore: `TELEGRAM_TOKEN not found`**
- Soluzione: Controlla che il file `.env` esista e contenga i token corretti
- Verifica che `python-dotenv` sia installato: `pip install python-dotenv`

**Errore: `Port 8000 already in use`**
- Soluzione: Cambia porta: `uvicorn app.main:app --port 8001`
- Oppure uccidi il processo sulla porta 8000

### Notion restituisce 401 Unauthorized

- Verifica che il token sia corretto (deve iniziare con `ntn_` o `secret_`)
- Controlla di aver connesso l'integration alla pagina Notion:
  - Vai sulla pagina → `...` → "Connect to" → Seleziona l'integration

### Notion restituisce 400 Bad Request

- Assicurati di aver impostato `NOTION_PARENT_PAGE_ID` nel `.env`
- Verifica che l'ID della pagina sia corretto (32 caratteri esadecimali)

### Il webhook non riceve messaggi

- Verifica che Ngrok sia in esecuzione
- Controlla che il webhook sia registrato: visita `/setup-webhook`
- Controlla i log di Ngrok per vedere se le richieste arrivano
- Verifica che il `TELEGRAM_TOKEN` sia corretto

### Debug non funziona

- Assicurati che VS Code abbia l'estensione Python installata
- Verifica che l'interprete Python sia quello del virtual environment (`.venv`)
- Controlla che il file `.vscode/launch.json` esista

---

## 📝 Comandi Utili

### Vedere i log del server
Il server stampa log automaticamente su console. Livello INFO di default.

### Controllare il webhook Telegram
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
```

### Rimuovere il webhook
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/deleteWebhook"
```

### Test manuale dell'endpoint
```bash
# Health check
curl http://localhost:8000/

# Setup webhook (cambia URL con quello di Ngrok)
curl http://localhost:8000/setup-webhook
```

---

## 🏗️ Struttura Progetto

```
tg-notion-archiver/
├── app/
│   ├── main.py          # FastAPI app + webhook endpoint
│   ├── handlers.py      # Routing messaggi Telegram
│   ├── extractor.py     # Estrazione contenuto (web, PDF, immagini)
│   ├── summarizer.py    # Sintesi AI con Claude
│   ├── notion.py        # Creazione database e pagine Notion
│   ├── tagger.py        # Sistema tag intelligente
│   ├── state.py         # State manager per sessioni utente
│   └── telegram.py      # Helper Telegram API
├── .vscode/
│   └── launch.json      # Configurazione debugger VS Code
├── .env                 # Variabili d'ambiente (NON committare!)
├── .env.example         # Template per .env
├── requirements.txt     # Dipendenze Python
├── CLAUDE.md            # Guida per Claude Code
├── LOCAL_DEVELOPMENT.md # Questa guida
└── README.md            # Documentazione principale
```

---

## 🎯 Best Practices

1. **Usa sempre il virtual environment** (`.venv`) per isolare le dipendenze
2. **Non committare mai `.env`** - contiene segreti!
3. **Usa `--reload`** durante lo sviluppo per auto-restart al cambio file
4. **Testa sempre localmente** prima di deployare su Railway
5. **Usa il debugger** invece di `print()` per ispezionare il codice
6. **Controlla i log** per capire cosa sta succedendo

---

## 🚀 Deploy su Railway

Quando sei pronto per il deploy in produzione, segui le istruzioni nel [README.md](README.md).

Railway supporta il deploy diretto da GitHub - basta collegare il repository!

---

## 💡 Tips

- **Ngrok URL cambia ogni restart**: Ogni volta che riavvii Ngrok, l'URL cambia. Devi registrare nuovamente il webhook.
- **Ngrok gratis ha limiti**: 40 connessioni/minuto. Per testing è sufficiente.
- **Logs dettagliati**: Usa `logging.DEBUG` in `app/main.py` per log più dettagliati.
- **Claude AI costa**: Ogni richiesta consuma crediti Anthropic. Testa con moderazione.

---

## 📚 Risorse

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Notion API](https://developers.notion.com/)
- [Anthropic API](https://docs.anthropic.com/)
- [Ngrok Docs](https://ngrok.com/docs)

---

**Buon coding! 🎉**
