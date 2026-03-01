# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot that receives URLs, PDFs, images, and text notes, analyzes them with Claude AI, and automatically archives them to Notion with AI-generated summaries, tags, and metadata.

## Development Commands

### Local Development
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# or: .venv\Scripts\activate.bat  # Windows CMD

# Install dependencies
pip install -r requirements.txt

# Run the server locally
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Test endpoints
curl http://localhost:8000/
curl http://localhost:8000/setup-webhook
```

### Environment Variables
Required variables (set in `.env` for local development):
- `TELEGRAM_TOKEN` - Bot token from @BotFather
- `NOTION_TOKEN` - Integration token from notion.so/my-integrations
- `ANTHROPIC_API_KEY` - Claude API key (note: the .env file has a typo, should be ANTHROPIC_API_KEY not ANTHROPICAPIKEY)

Optional:
- `NOTION_PARENT_PAGE_ID` - Parent page for the Notion database
- `WEBHOOK_SECRET` - Random string for webhook security

## Architecture Overview

### Application Flow
1. **Webhook Reception** (`main.py`): FastAPI receives Telegram updates at `/webhook/{token}`
2. **Message Routing** (`handlers.py`): Dispatches by content type (URL/PDF/image/text)
3. **Content Extraction** (`extractor.py`): Fetches and extracts content from various sources
4. **AI Summarization** (`summarizer.py`): Claude generates title, bullets, and tags
5. **Tag Selection UI** (`tagger.py` + `state.py`): Presents inline keyboard with top 5 most-used tags
6. **Archival** (`notion.py`): Creates Notion page with structured content

### Module Responsibilities

**`main.py`** - FastAPI application entry point
- Webhook endpoint security (token + optional secret validation)
- Startup hook calls `ensure_database_exists()` to create/find Notion database
- Health check at `/`
- `/setup-webhook` endpoint to register webhook with Telegram

**`handlers.py`** - Main update dispatcher
- Routes callbacks vs messages
- Handles different content types: URLs, PDFs, images, text notes
- Manages tag selection flow (shows keyboard → user selects → archives)
- Builds Telegram message links for archival

**`extractor.py`** - Content extraction layer
- Classifies URLs (YouTube, Twitter, web articles, PDF URLs, etc.)
- Extracts text from PDFs using `pypdf`
- Uses Claude Vision API for image descriptions
- Strips HTML and extracts metadata (title, author, date)

**`summarizer.py`** - Claude AI integration
- Builds prompts with content type-specific character limits
- Calls Claude API (`claude-sonnet-4-20250514`) to generate:
  - Reformulated title (max 80 chars)
  - 3-5 bullet points with key insights
  - 3-5 specific tags
  - Language detection
- Handles JSON parsing with fallback

**`notion.py`** - Notion API integration
- Database management: searches for existing "Archivio Telegram" database or creates it
- Global `_DATABASE_ID` stores database ID after startup
- Schema includes: Nome (title), URL, Link Telegram, Tipo (select), Tag (multi_select), Autore, Data Contenuto, Data Archiviazione, Lingua
- Page creation with structured blocks (heading, bullets, metadata, links)
- NO sentiment field (was removed in v2)

**`tagger.py`** - Tag suggestion system
- Fetches top 5 most-used tags from Notion database
- Daily cache refresh (`_tag_cache` dict with date tracking)
- Builds Telegram inline keyboards for tag selection
- Supports multi-select with visual feedback (🏷️ vs ✅)

**`state.py`** - In-memory session state
- Stores pending archival jobs while user selects tags
- Key: `chat_id`, Value: job dict with summary, URLs, selected_tags set
- 30-minute TTL with automatic expiry
- Single job per chat (new job overwrites previous)

**`telegram.py`** - Telegram API helpers
- `send_message()`, `send_typing()`, `send_message_with_keyboard()`
- `edit_message_keyboard()` - updates inline keyboard or replaces with final message
- `answer_callback()` - dismisses button spinner

### Key Patterns

**Async/Await**: All I/O operations (HTTP requests, API calls) use `async`/`await` with `httpx.AsyncClient`

**State Management**: Pending archival jobs stored in `state.py` module-level dict, allowing multi-step user interactions

**Notion Database Initialization**: `ensure_database_exists()` called at FastAPI startup, searches for existing database before creating new one

**Tag Keyboard Flow**:
1. Extract + summarize content → get AI tags
2. Fetch top 5 user tags from Notion (cached daily)
3. Show preview + tag selection keyboard
4. User toggles tags (0 to N selections)
5. User presses "Archivia" → combine AI tags + selected tags → archive to Notion
6. Edit message to show final confirmation with Notion link

**Content Type Classification**: `extractor.py` detects YouTube, Vimeo, Twitter, PDF URLs, etc. and applies source-specific handling

**Error Handling**: Try/except blocks around external API calls with user-facing error messages sent via Telegram

## Deployment Notes

This app is designed for Railway.app deployment:
- Railway sets `PORT` environment variable automatically
- Dockerfile uses Python 3.12-slim
- Procfile and railway.toml both specify the uvicorn start command
- Health check configured at `/` endpoint
- Webhook must be registered after deploy by calling `/setup-webhook`

## Working with Notion API

The database schema is created programmatically in `notion.py:_create_database()`. If you need to modify the schema:
1. Update the `properties` dict in `_create_database()`
2. Update the `properties` dict in `archive_to_notion()` to populate new fields
3. Consider adding migration logic or deleting/recreating the database for testing

Multi-select tags in Notion are automatically created when first used - no need to pre-define tag options.

## Working with Claude API

Two separate Claude API calls:
1. **Image description** (`extractor.py:extract_image_description`) - Vision model for image analysis
2. **Content summarization** (`summarizer.py:summarize_content`) - Text model for generating structured summaries

Both use `claude-sonnet-4-20250514` model. Prompts are designed to return JSON with specific schema. JSON parsing includes fallback handling and markdown code block stripping.
