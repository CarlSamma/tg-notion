# 📚 Telegram → Notion Archiver

Bot Telegram che riceve URL, PDF, immagini e note di testo,  
le analizza con Claude AI e le archivia automaticamente su Notion.

---

## ✨ Funzionalità

| Input | Cosa fa |
|---|---|
| URL (YouTube, articoli, social) | Fetcha il contenuto, genera sintesi AI, archivia |
| PDF allegato | Estrae testo, genera sintesi AI, archivia |
| URL diretto a PDF | Scarica, estrae testo, genera sintesi AI, archivia |
| Immagine | Descrive con Claude Vision, archivia |
| Testo libero | Archivia come nota con sintesi |

Per ogni contenuto crea su Notion:
- Titolo riformulato dall'AI
- 3–5 bullet points dei punti chiave
- Sentiment (🟢 Positivo / 🟡 Neutro / 🔴 Negativo / 🟣 Misto)
- Tag specifici per ricerca futura
- Metadati (autore, data, lingua, fonte)
- Link originale

---

## 🚀 Deploy su Railway — Guida passo passo

### Prerequisiti

1. Account [Railway.app](https://railway.app)
2. Token Bot Telegram (da [@BotFather](https://t.me/BotFather))
3. Account Notion con Integration Token
4. API Key Anthropic (Claude)

---

### Step 1 — Crea l'Integration Notion

1. Vai su [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Clicca **"+ New integration"**
3. Nome: `Telegram Archiver`
4. Capabilities: ✅ Read content, ✅ Update content, ✅ Insert content
5. Copia il **"Internal Integration Token"** → è il tuo `NOTION_TOKEN`

> **Opzionale**: se vuoi che il database venga creato dentro una pagina specifica di Notion,
> apri quella pagina, clicca i `...` in alto a destra → **"Add connections"** → seleziona `Telegram Archiver`.
> Poi copia l'ID dalla URL della pagina (la stringa dopo l'ultimo `/` e prima di `?`).
> Questo sarà il tuo `NOTION_PARENT_PAGE_ID`.

---

### Step 2 — Deploy su Railway

#### Opzione A: da GitHub (consigliata)

1. Carica questa cartella su un repo GitHub (privato va benissimo)
2. Vai su [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Seleziona il repo
4. Railway detecta automaticamente il Dockerfile

#### Opzione B: Railway CLI

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

---

### Step 3 — Variabili d'ambiente su Railway

Nel tuo progetto Railway → tab **Variables** → aggiungi:

| Variabile | Valore | Obbligatoria |
|---|---|---|
| `TELEGRAM_TOKEN` | Il token del tuo bot Telegram | ✅ |
| `NOTION_TOKEN` | Il token dell'Integration Notion | ✅ |
| `ANTHROPIC_API_KEY` | La tua API key Anthropic | ✅ |
| `NOTION_PARENT_PAGE_ID` | ID pagina Notion (opzionale) | ❌ |
| `WEBHOOK_SECRET` | Stringa random per sicurezza (es. `openssl rand -hex 20`) | ❌ (consigliata) |

Railway imposta `PORT` automaticamente — non aggiungerlo tu.

---

### Step 4 — Registra il Webhook Telegram

Dopo che Railway ha completato il deploy e ti ha dato un URL pubblico (tipo `https://tuo-app.up.railway.app`):

Apri nel browser:
```
https://tuo-app.up.railway.app/setup-webhook
```

Dovresti vedere:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

✅ Il bot è attivo!

---

### Step 5 — Test

Apri Telegram, vai sul tuo bot e invia:
```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Dopo qualche secondo riceverai:
```
✅ Rick Astley e la Trappola Musicale Più Famosa della Storia
🔗 Apri su Notion
```

E troverai la pagina nel database "Archivio Telegram" su Notion.

---

## 🗂️ Struttura del progetto

```
tg-notion-archiver/
├── app/
│   ├── main.py          # FastAPI app + webhook endpoint
│   ├── handlers.py      # Routing messaggi Telegram
│   ├── extractor.py     # Estrazione contenuto (web, PDF, immagini)
│   ├── summarizer.py    # Sintesi AI con Claude
│   ├── notion.py        # Creazione database e pagine Notion
│   └── telegram.py      # Helper invio messaggi
├── Dockerfile
├── Procfile
├── railway.toml
├── requirements.txt
└── README.md
```

---

## 🔒 Sicurezza

- Il token Telegram è nell'URL del webhook — Railway lo gestisce via HTTPS
- Usa `WEBHOOK_SECRET` per proteggere l'endpoint da richieste esterne
- Non committare mai `.env` su Git (già in `.gitignore`)
- **Revoca e rigenera subito** qualsiasi token che hai condiviso accidentalmente

---

## 🐛 Troubleshooting

**Il bot non risponde:**
- Verifica che il webhook sia registrato: `https://api.telegram.org/bot{TOKEN}/getWebhookInfo`
- Controlla i logs su Railway → tab **Logs**

**Errore Notion:**
- Verifica che il `NOTION_TOKEN` sia corretto
- Se usi `NOTION_PARENT_PAGE_ID`, assicurati che l'integration abbia accesso a quella pagina

**Errore PDF:**
- `pypdf` è incluso nei requirements — verifica che il build sia andato a buon fine

**Re-registrare il webhook dopo cambio URL:**
- Richiama `/setup-webhook` ogni volta che l'URL Railway cambia
