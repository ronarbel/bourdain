# Bourdain Bot

*"Your body is not a temple, it's an amusement park. Enjoy the ride."* — Anthony Bourdain

A personal sous-chef that lives in your pocket. Text Bourdain what you need — *"get me 2 granolas and some bananas"* — and he'll walk into the store, grab exactly the right stuff off the shelf, and have it delivered to your door. No browsing. No scrolling through 47 brands of yogurt. Just the good stuff, the stuff you actually want.

Because life's too short for the wrong granola.

---

## How It Works

You talk. Bourdain shops.

```
You (Telegram) → "get 2 granolas and 3 bananas"
  → AI parses your order
  → Browser automation hits Instacart
  → Finds your exact items at Rainbow Grocery
  → Adds them to cart
  → Sends you a screenshot to confirm
  → You say CHECKOUT → groceries are on their way
```

Bourdain knows your preferences. He knows you want the Purely Elizabeth granola, not some impostor. He knows your yogurt is Bellwether Farms A2 Organic, and he won't settle for less. Items are matched **strict** or **fuzzy** — strict means exact match or nothing, fuzzy means best effort (any banana is a good banana).

---

## Setup

### Prerequisites

- Python 3.9+
- A Telegram account
- An Instacart account with saved payment method and delivery address

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install python-telegram-bot playwright anthropic pyyaml python-dotenv pydantic pydantic-settings
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
```

### 4. Start the bot

```bash
source .venv/bin/activate
python -m src.main
```

### 5. Log in to Instacart

Send `/login` to your bot on Telegram. A browser window will open on your machine — log in to your Instacart account. Once done, send `/done`. Your session is saved to `auth_state.json` and persists across restarts.

---

## Usage

### Placing an order

Just text Bourdain like you'd text a friend:

- *"Get 2 granolas and 3 yogurts"*
- *"I need bananas"*
- *"Order 1 yogurt and 5 bananas"*

The bot will:

1. Parse your order and confirm what it understood
2. Ask you to reply **YES** to add items to your Instacart cart
3. Add items via browser automation (with strict matching for the items that matter)
4. Send you a screenshot of the cart for confirmation
5. Ask you to reply **CHECKOUT** to place the order

Reply **NO** or **CANCEL** at any step to abort.

### Bot commands

| Command  | Description                          |
|----------|--------------------------------------|
| `/start` | Welcome message and usage info       |
| `/items` | List all available items             |
| `/login` | Log in to Instacart (opens browser)  |
| `/done`  | Finish login after logging in        |

---

## The Menu

Your items are configured in `config/items.yaml`. Each item has a short alias (what you say), a search term (what Instacart sees), and a match mode:

| Alias      | Product                                                    | Match  |
|------------|------------------------------------------------------------|--------|
| `granola`  | Purely Elizabeth Original Ancient Grain Granola, Organic    | strict |
| `yogurt`   | Bellwether Farms A2 Organic Whole Milk Yogurt, Plain       | strict |
| `bananas`  | Organic Bananas                                            | fuzzy  |

**Strict** = must be the exact product, or Bourdain refuses and sends you a screenshot of what he found instead. No substitutions on the things that matter.

**Fuzzy** = best effort. Close enough is good enough. A banana is a banana.

---

## Adding New Items

Edit `config/items.yaml`:

```yaml
items:
  peanut_butter:
    search_term: "Smucker's Natural Peanut Butter 16 oz"
    display_name: "Smucker's Natural Peanut Butter"
    match: strict
    default_quantity: 1
```

The `search_term` is what gets typed into Instacart's search. Make it specific enough to return the right product as the first result. The `display_name` is matched against Instacart's product name for strict items.

---

## Project Structure

```
bourdain_bot/
├── pyproject.toml          # Dependencies
├── .env                    # API keys (not committed)
├── .env.example            # Template for .env
├── .gitignore
├── auth_state.json         # Saved Instacart session (not committed)
├── config/
│   └── items.yaml          # Your menu — item aliases and preferences
└── src/
    ├── main.py             # Entry point
    ├── config.py           # Settings + YAML config loader
    ├── bot.py              # Telegram bot handlers and order flow
    ├── parser.py           # Claude Haiku NLP — turns text into structured orders
    └── instacart.py        # Playwright browser automation for Instacart
```

---

## Notes

- **Instacart selectors**: Instacart's UI changes. If automation breaks, the selectors in `src/instacart.py` may need updating.
- **Anti-bot detection**: The bot uses human-like delays between actions. If you hit CAPTCHAs, try running with `headless=False` in `src/config.py`.
- **Session expiry**: If your Instacart session expires, run `/login` again.
- **Costs**: Each order parse uses Claude Haiku (~$0.001 per order). Practically free.
- **Runs locally**: The bot runs on your Mac. Your machine needs to be on for orders to process. Cloud deployment is a future option.

---

*Built with good taste.*
