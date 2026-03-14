# 🚂 Deploy su Railway — Guida completa

Guida passo passo per portare il bot in produzione su [Railway.app](https://railway.app).

---

## Indice

- [Prerequisiti](#prerequisiti)
- [Step 1 — Prepara il repository GitHub](#step-1--prepara-il-repository-github)
- [Step 2 — Crea il progetto Railway](#step-2--crea-il-progetto-railway)
- [Step 3 — Configura le variabili d'ambiente](#step-3--configura-le-variabili-dambiente)
- [Step 4 — Verifica il build](#step-4--verifica-il-build)
- [Step 5 — Genera il dominio pubblico](#step-5--genera-il-dominio-pubblico)
- [Step 6 — Registra il webhook Telegram](#step-6--registra-il-webhook-telegram)
- [Step 7 — Test end-to-end](#step-7--test-end-to-end)
- [Aggiornamenti successivi](#aggiornamenti-successivi)
- [Monitoraggio e log](#monitoraggio-e-log)
- [Costi Railway](#costi-railway)
- [Troubleshooting Railway](#troubleshooting-railway)

---

## Prerequisiti

Prima di iniziare assicurati di avere:

- Account [Railway.app](https://railway.app) (login con GitHub consigliato)
- Repository GitHub con il codice del progetto (può essere privato)
- Token bot Telegram attivo (da [@BotFather](https://t.me/BotFather))
- Notion Integration Token con accesso alla pagina target
- API Key Anthropic attiva

---

## Step 1 — Prepara il repository GitHub

Se non hai ancora un repo GitHub:

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create tg-notion --private --push
# oppure crea il repo manualmente su github.com e fai push
```

Assicurati che `.gitignore` includa `.env` (già presente nel progetto) — non committare mai i segreti.

---

## Step 2 — Crea il progetto Railway

### Opzione A — Da GitHub (consigliata)

1. Vai su [railway.app/new](https://railway.app/new)
2. Clicca **"Deploy from GitHub repo"**
3. Autorizza Railway ad accedere al tuo GitHub (prima volta)
4. Seleziona il repository `tg-notion`
5. Railway detecta automaticamente il `Dockerfile` e avvia il build

### Opzione B — Railway CLI

```bash
npm install -g @railway/cli
railway login
cd tg-notion
railway init          # crea nuovo progetto
railway up            # primo deploy
```

### Configurazione build

Il progetto include già `railway.toml` con la configurazione ottimale:

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

Railway imposta `$PORT` automaticamente — non aggiungerlo alle variabili.

---

## Step 3 — Configura le variabili d'ambiente

Nel pannello Railway del tuo progetto:

1. Clicca sul servizio → tab **"Variables"**
2. Aggiungi le seguenti variabili una per una (o usa "Raw Editor" per incollarle tutte):

| Variabile | Valore | Note |
|---|---|---|
| `TELEGRAM_TOKEN` | `123456:ABC-DEF...` | Da @BotFather |
| `NOTION_TOKEN` | `ntn_abc123...` | Da notion.so/my-integrations |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | Da console.anthropic.com |
| `NOTION_PARENT_PAGE_ID` | `316b88593c98...` | Opzionale: ID pagina Notion (32 char hex) |
| `WEBHOOK_SECRET` | stringa random | Opzionale ma consigliata |

**Genera WEBHOOK_SECRET sicuro:**
```bash
openssl rand -hex 20
```

**Come trovare NOTION_PARENT_PAGE_ID:**
Apri la pagina Notion nel browser. L'URL ha questa forma:
```
https://www.notion.so/Titolo-pagina-316b88593c988044b992f198ea858ed0
```
L'ID è la stringa di 32 caratteri alla fine (prima di eventuali `?v=...`).

⚠️ **Non aggiungere PORT** — Railway la gestisce internamente.

Dopo aver salvato le variabili, Railway riavvia automaticamente il servizio.

---

## Step 4 — Verifica il build

Nel tab **"Deployments"** puoi vedere i log del build in tempo reale.

Un build corretto termina con output simile a:

```
✅ Build successful
INFO:     Started server process
INFO:     Waiting for application startup
INFO:     ✅ Notion database pronto: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:XXXX
```

Se vedi errori come `TELEGRAM_TOKEN not found` o `NOTION_TOKEN not found`, verifica le variabili d'ambiente nello Step 3.

---

## Step 5 — Genera il dominio pubblico

1. Nel pannello del servizio → tab **"Settings"**
2. Sezione **"Networking"** → clicca **"Generate Domain"**
3. Railway assegna un URL tipo: `https://tg-notion-production.up.railway.app`

Verifica che il servizio risponda:
```bash
curl https://tg-notion-production.up.railway.app/
# → {"status":"ok","service":"tg-notion-archiver"}
```

---

## Step 6 — Registra il webhook Telegram

Con l'URL del servizio pronto, apri nel browser:

```
https://tg-notion-production.up.railway.app/setup-webhook
```

Risposta attesa:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

**Verifica il webhook registrato:**
```bash
curl "https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
```

La risposta deve mostrare `"url"` con il tuo dominio Railway e `"pending_update_count": 0`.

---

## Step 7 — Test end-to-end

Apri Telegram e nel canale (o chat col bot) invia:

```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Flusso atteso:

1. Il bot risponde con l'anteprima e la keyboard dei tag (entro 5–10 secondi)
2. Selezioni eventuali tag e premi "Archivia"
3. Il messaggio si aggiorna con il link Notion
4. Su Notion trovi la pagina nel database "Archivio Telegram"

Se non ricevi risposta entro 30 secondi, controlla i log su Railway → tab **"Logs"**.

---

## Aggiornamenti successivi

### Deploy automatico (consigliato)

Se hai collegato Railway al repo GitHub, ogni `git push` sul branch principale avvia automaticamente un nuovo deploy.

```bash
git add .
git commit -m "Fix: miglioramento estrazione PDF"
git push
```

Railway fa il build, poi sostituisce il container senza downtime (rolling deploy).

### Deploy manuale via CLI

```bash
railway up
```

### Rieseguire il setup webhook dopo cambio URL

Se cambi il dominio Railway (o lo rigeneri), devi ri-registrare il webhook:

```
https://nuovo-dominio.up.railway.app/setup-webhook
```

---

## Monitoraggio e log

### Log in tempo reale

Nel pannello Railway → tab **"Logs"** trovi i log dell'applicazione.

Filtra per livello:
- `INFO` — operazioni normali (database pronto, update ricevuti)
- `ERROR` — eccezioni gestite (errori API, parsing fallito)
- `WARNING` — situazioni anomale non critiche

### Metriche

Railway mostra automaticamente CPU, RAM e utilizzo rete nel tab **"Metrics"**.

### Health check

Railway esegue il health check su `GET /` ogni 30 secondi (configurato in `railway.toml`). Se fallisce 3 volte consecutive, il container viene riavviato.

---

## Costi Railway

Railway ha un piano gratuito con 500 ore/mese di esecuzione e 1 GB RAM.

Per uso personale continuo (bot sempre attivo):

| Piano | Costo | Adatto per |
|---|---|---|
| Hobby | $5/mese fisso | Uso personale, bot sempre attivo |
| Pro | $20/mese + usage | Team, più servizi, più risorse |

Il bot usa circa 100–150 MB RAM e ha pochissima CPU idle — il piano Hobby è sufficiente.

---

## Troubleshooting Railway

**Build fallisce con `ModuleNotFoundError`**
- Verifica che `requirements.txt` sia aggiornato
- Controlla che il Dockerfile non abbia istruzioni mancanti

**Il servizio si avvia ma il bot non risponde**
- Controlla i log per errori di connessione a Notion o Telegram
- Verifica che tutte le variabili d'ambiente siano impostate correttamente
- Esegui di nuovo `/setup-webhook`

**Errore `403 Invalid token` sui webhook**
- Il `TELEGRAM_TOKEN` nelle variabili Railway non corrisponde a quello in `WEBHOOK_SECRET`
- Rigenera le variabili e ri-fai il deploy

**Il database Notion non viene creato**
- Verifica che `NOTION_TOKEN` abbia i permessi corretti (Read + Insert + Update)
- Se usi `NOTION_PARENT_PAGE_ID`, verifica che l'integration sia connessa a quella pagina specifica
- Guarda i log per il messaggio `❌ Errore setup Notion database`

**Il bot risponde ma non archivia**
- Controlla i log per eccezioni in `archive_to_notion()`
- Verifica che il database ID non sia cambiato (può succedere se il database viene eliminato e ricreato)
- Come fix temporaneo: elimina il database su Notion e riavvia il servizio Railway per ricrearlo

**Job tag persi dopo restart**
- Comportamento atteso: lo state è in memoria e non persiste ai restart
- Soluzione: implementare Redis (vedi sezione Suggerimenti nel README)

---

## Checklist deploy

```
[ ] Repository GitHub aggiornato con il codice più recente
[ ] .env non committato (verificare .gitignore)
[ ] Progetto Railway creato e collegato al repo
[ ] Variabili d'ambiente impostate (TELEGRAM_TOKEN, NOTION_TOKEN, ANTHROPIC_API_KEY)
[ ] Build completato senza errori
[ ] Dominio pubblico generato
[ ] Health check risponde: GET / → {"status":"ok"}
[ ] Notion database creato (log di startup)
[ ] Webhook registrato via /setup-webhook
[ ] Test end-to-end con un URL di prova
[ ] Pagina su Notion creata correttamente
```
