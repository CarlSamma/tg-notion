# Technical Guide — Local Development

Step-by-step guide to run the **Telegram → Notion Archiver** bot locally.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended (matches Docker) |
| Git | any | to clone the repo |
| Telegram account | — | bot created via @BotFather |
| Notion account | — | integration created at notion.so/my-integrations |
| Anthropic account | — | API key from console.anthropic.com |
| ngrok *(optional)* | any | only needed to receive real Telegram messages locally |

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/CarlSamma/tg-notion.git
cd tg-notion
```

Switch to the active development branch:

```bash
git checkout DB-set
```

---

## Step 2 — Create a virtual environment

**Windows (Git Bash / PowerShell):**
```bash
python -m venv .venv
source .venv/Scripts/activate        # Git Bash
# or: .venv\Scripts\Activate.ps1    # PowerShell
# or: .venv\Scripts\activate.bat    # CMD
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

Verify the venv is active — the prompt should show `(.venv)`.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

Installed packages:
- `fastapi` — web framework for the webhook server
- `uvicorn[standard]` — ASGI server
- `httpx` — async HTTP client (Telegram, Notion, Anthropic calls)
- `pypdf` — PDF text extraction
- `python-multipart` — multipart form support
- `python-dotenv` — loads `.env` file automatically

---

## Step 4 — Configure environment variables

Copy the template:

```bash
cp .env.example .env
```

Open `.env` and fill in your real values:

```env
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WEBHOOK_SECRET=any_random_string_you_choose
NOTION_PARENT_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # optional
```

### How to get each token

**TELEGRAM_TOKEN**
1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the token provided (format: `123456789:ABCdef...`)

**NOTION_TOKEN**
1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **+ New integration** → give it a name → save
3. Copy the token from the **Secrets** section (starts with `ntn_`)
4. **Critical:** open the Notion page where the database will live → click `...` (top right) → **Connect to** → select your integration

**ANTHROPIC_API_KEY**
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Navigate to **API Keys** → **Create Key**
3. Copy the key (starts with `sk-ant-api03-`)

**NOTION_PARENT_PAGE_ID** *(optional)*
1. Open the Notion page where you want the database created
2. Copy the page URL: `https://www.notion.so/My-Page-316b8859...`
3. The ID is the last 32-character hex string in the URL

**WEBHOOK_SECRET** *(optional but recommended)*
```bash
openssl rand -hex 20
```
Use the output as your secret. It validates that webhook calls come from Telegram.

---

## Step 5 — Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected startup output:
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO      HTTP Request: POST https://api.notion.com/v1/search "HTTP/1.1 200 OK"
INFO      DB trovato: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
INFO      ✅ Notion database pronto: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

If Notion returns `401 Unauthorized` at startup, the token is wrong or the integration is not connected to the page. The server still starts and the health check works, but archival will fail.

---

## Step 6 — Verify the server is running

```bash
curl http://localhost:8000/
```

Expected response:
```json
{"status": "ok", "service": "tg-notion-archiver"}
```

---

## Step 7 — Test the webhook locally (no ngrok needed)

You can simulate any Telegram message by sending a POST directly to the local webhook endpoint. This bypasses the need for a public URL during development.

### Send a URL message

```bash
curl -s -X POST "http://localhost:8000/webhook/<TELEGRAM_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: <WEBHOOK_SECRET>" \
  -d '{
    "update_id": 100000001,
    "message": {
      "message_id": 1,
      "from": {"id": 123456789, "is_bot": false, "first_name": "Test", "username": "testuser"},
      "chat": {"id": <YOUR_CHAT_ID>, "type": "group", "title": "Test"},
      "date": 1710000000,
      "text": "https://example.com/article"
    }
  }'
```

Replace:
- `<TELEGRAM_TOKEN>` — your bot token
- `<WEBHOOK_SECRET>` — the value from your `.env` (omit the header if `WEBHOOK_SECRET` is empty)
- `<YOUR_CHAT_ID>` — your Telegram chat ID (see below)

**How to find your chat ID:**
Open the chat in Telegram Web (`https://web.telegram.org/a/#-1003897321914`) — the number after `#` is the chat ID (include the `-` sign for groups).

### Expected pipeline in the server logs

```
INFO      Update ricevuto: 100000001
INFO      HTTP Request: POST .../sendChatAction "HTTP/1.1 200 OK"   ← typing indicator
INFO      HTTP Request: GET https://example.com/article "HTTP/1.1 200 OK"   ← content fetched
INFO      HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"   ← AI summarized
INFO      HTTP Request: POST .../sendMessage "HTTP/1.1 200 OK"   ← tag keyboard sent to Telegram
```

### Simulate the "Archivia" button press

After the bot sends the tag selection keyboard, simulate pressing **Archivia** with a callback query. You need the `message_id` from the bot's Telegram message:

```bash
curl -s -X POST "http://localhost:8000/webhook/<TELEGRAM_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: <WEBHOOK_SECRET>" \
  -d '{
    "update_id": 100000002,
    "callback_query": {
      "id": "callback_test_001",
      "from": {"id": 123456789, "is_bot": false, "first_name": "Test"},
      "message": {
        "message_id": <BOT_MESSAGE_ID>,
        "chat": {"id": <YOUR_CHAT_ID>, "type": "group"}
      },
      "data": "tag:__done__"
    }
  }'
```

On success, the server archives to Notion and updates the Telegram message with the Notion link.

---

## Step 8 — Test with real Telegram messages (ngrok)

To receive actual messages from Telegram (sent by you or others), you need a public HTTPS URL.

### 8a. Start ngrok

```bash
ngrok http 8000
```

Note the HTTPS forwarding URL, e.g.: `https://abc123.ngrok-free.app`

### 8b. Register the webhook with Telegram

```bash
curl "http://localhost:8000/setup-webhook" \
  --header "Host: abc123.ngrok-free.app" \
  --header "X-Forwarded-Proto: https"
```

Or simply open in browser:
```
https://abc123.ngrok-free.app/setup-webhook
```

Expected response:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

### 8c. Send a message to the bot

Open your Telegram group or DM the bot and send:
- A URL → bot fetches, summarizes, shows tag keyboard
- A PDF file → bot extracts text, summarizes
- An image → bot uses Claude Vision to describe it
- Plain text → bot treats it as a note

### 8d. Remove the webhook when done

```bash
curl "https://api.telegram.org/bot<TELEGRAM_TOKEN>/deleteWebhook"
```

> **Note:** ngrok's free tier generates a new URL on every restart. You must re-run `/setup-webhook` each time.

---

## Step 9 — Debug with VS Code

The `.vscode/launch.json` is pre-configured.

1. Open the project in VS Code: `code .`
2. Make sure VS Code uses the `.venv` interpreter:
   - `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv`
3. Add breakpoints by clicking the gutter in any `.py` file
4. Press `F5` → select **Debug Server**
5. The server starts with the debugger attached

Useful breakpoint locations:
- `app/handlers.py:handle_update` — every incoming Telegram update
- `app/handlers.py:_handle_urls` — URL processing
- `app/handlers.py:_do_archive` — right before archival to Notion
- `app/summarizer.py:summarize_content` — AI summarization call
- `app/notion.py:archive_to_notion` — Notion page creation

---

## Troubleshooting

### `TELEGRAM_TOKEN not found` on startup
The `.env` file is missing or not loaded. Make sure it exists at the project root and `python-dotenv` is installed.

### Notion `401 Unauthorized` at startup
- Token is wrong or expired — regenerate it at notion.so/my-integrations
- Integration not connected to the Notion page — go to the page → `...` → **Connect to**

### Notion `400 Bad Request` when creating the database
- `NOTION_PARENT_PAGE_ID` is incorrect or missing
- The integration doesn't have access to that page

### `Port 8000 already in use`
Find and kill the process:
```bash
# Windows
netstat -ano | grep :8000
# then: powershell -Command "Stop-Process -Id <PID> -Force"

# macOS/Linux
lsof -i :8000
kill -9 <PID>
```
Or use a different port: `uvicorn app.main:app --port 8001`

### Webhook returns `403 Invalid secret`
The `X-Telegram-Bot-Api-Secret-Token` header must match `WEBHOOK_SECRET` in `.env`. Include it in every curl test or set `WEBHOOK_SECRET=` (empty) in `.env` to disable secret validation.

### Bot sends messages but Telegram returns `chat not found`
The `chat.id` in your test payload is wrong. Use the real chat ID from the Telegram Web URL.

### ngrok tunnel disconnects
Ngrok free tier has session time limits. Restart ngrok and re-register the webhook via `/setup-webhook`.

---

## Project structure

```
tg-notion/
├── app/
│   ├── main.py          # FastAPI app, webhook endpoint, startup hook
│   ├── handlers.py      # Telegram update router (URL/PDF/image/text/callbacks)
│   ├── extractor.py     # Content extraction (web scraping, PDF, Claude Vision)
│   ├── summarizer.py    # Claude AI summarization → title, bullets, tags
│   ├── notion.py        # Notion database management and page creation
│   ├── tagger.py        # Tag suggestion system with daily cache
│   ├── state.py         # In-memory session state (30-min TTL)
│   └── telegram.py      # Telegram API helpers (send, edit, keyboard)
├── .github/
│   └── workflows/
│       └── ci.yml       # GitHub Actions: lint (ruff) + Docker build
├── .vscode/
│   └── launch.json      # VS Code debugger configuration
├── .env                 # Local secrets — never commit
├── .env.example         # Template with placeholder values
├── requirements.txt     # Python dependencies
├── Dockerfile           # Production container (python:3.12-slim)
├── Procfile             # Railway start command
├── railway.toml         # Railway deployment config
└── CLAUDE.md            # Architecture reference for Claude Code
```

---

## Useful commands

```bash
# Check registered webhook info
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Remove webhook (re-enables getUpdates)
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# Manually poll for updates (only works when no webhook is set)
curl "https://api.telegram.org/bot<TOKEN>/getUpdates"

# Lint the codebase
pip install ruff
ruff check app/

# Build the Docker image locally
docker build -t tg-notion .
docker run --env-file .env -p 8000:8000 tg-notion
```
