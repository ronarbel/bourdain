# Food Order Bot

A Telegram bot that takes natural language grocery orders (text or voice) and automates placing them on Instacart via browser automation.

## How It Works

```
You (Telegram) → send "get 2 granolas and 3 bananas"
  → Claude Haiku parses into structured order
  → Playwright opens Instacart (Rainbow Grocery)
  → Adds items to cart
  → Sends you a cart summary with prices
  → You reply CHECKOUT → order is placed
```

Voice notes work too — they're transcribed via OpenAI Whisper before parsing.

## Setup

### Prerequisites

- Python 3.9+
- FFmpeg: `brew install ffmpeg`
- A Telegram account
- An Instacart account with saved payment method and delivery address

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install python-telegram-bot playwright anthropic openai pyyaml python-dotenv pydantic pydantic-settings
playwright install chromium
```

### 2. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
TELEGRAM_BOT_TOKEN=<from BotFather>
ANTHROPIC_API_KEY=<your Anthropic key>
OPENAI_API_KEY=<your OpenAI key, for voice transcription>
```

### 4. Start the bot

```bash
source .venv/bin/activate
python -m src.main
```

### 5. Log in to Instacart

Send `/login` to your bot on Telegram. A browser window will open — log in to your Instacart account manually. Once done, press Enter in the terminal. Your session is saved to `auth_state.json` so you don't need to log in again.

## Usage

### Placing an order

Send a message like:

- "Get 2 granolas and 3 yogurts"
- "I need bananas"
- "Order 1 yogurt and 5 bananas"

Or send a voice note saying the same thing.

The bot will:

1. Parse your order and show what it understood
2. Ask you to reply **YES** to add items to your Instacart cart
3. Add items via browser automation
4. Show a cart summary with actual prices
5. Ask you to reply **CHECKOUT** to place the order

Reply **NO** or **CANCEL** at any step to abort.

### Bot commands

| Command  | Description                        |
|----------|------------------------------------|
| `/start` | Welcome message and usage info     |
| `/items` | List all available items           |
| `/login` | Log in to Instacart (opens browser)|

## Available Items

Configured in `config/items.yaml`. Current items (all from Rainbow Grocery):

| Alias      | Product                                                         |
|------------|-----------------------------------------------------------------|
| `granola`  | Purely Elizabeth Original Ancient Grain Granola, Organic (10 oz) |
| `yogurt`   | Bellwether Farms A2 Organic Whole Milk Yogurt, Plain (32 oz)    |
| `bananas`  | Organic Bananas                                                 |

All items support quantity — say "3 granolas" to order 3.

## Adding New Items

Edit `config/items.yaml`:

```yaml
items:
  peanut_butter:
    search_term: "Smucker's Natural Peanut Butter 16 oz"
    display_name: "Smucker's Natural Peanut Butter (16 oz)"
    default_quantity: 1
```

The `search_term` is what gets typed into Instacart's search bar. Make it specific enough to return the right product as the first result.

## Project Structure

```
foodorder/
├── pyproject.toml          # Project metadata and dependencies
├── .env                    # API keys (not committed)
├── .env.example            # Template for .env
├── .gitignore
├── auth_state.json         # Saved Instacart session (not committed)
├── config/
│   └── items.yaml          # Item aliases → product mappings
└── src/
    ├── main.py             # Entry point — loads config, starts bot
    ├── config.py           # Settings (env vars) + YAML config loader
    ├── bot.py              # Telegram bot handlers and order flow
    ├── parser.py           # Claude Haiku NLP → structured order
    ├── transcriber.py      # Voice note (.ogg) → text via Whisper
    └── instacart.py        # Playwright browser automation for Instacart
```

## Notes

- **Instacart selectors**: Instacart's UI changes frequently. If automation breaks, the CSS selectors in `src/instacart.py` may need updating.
- **Anti-bot detection**: The automation uses human-like delays between actions. If you hit CAPTCHAs, try running with `headless=False` (set `HEADLESS=false` in `.env` or edit `config.py`).
- **Session expiry**: If your Instacart session expires, run `/login` again.
- **Costs**: Each order parse uses Claude Haiku (~$0.001). Voice transcription uses Whisper (~$0.006/min).
