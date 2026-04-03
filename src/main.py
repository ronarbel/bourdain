import logging
import sys

from dotenv import load_dotenv

from .config import Settings, load_items_config
from .bot import create_bot


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        settings = Settings()
    except Exception as e:
        print(f"Missing environment variables. Copy .env.example to .env and fill in your keys.\n{e}")
        sys.exit(1)

    items_config = load_items_config()
    logging.info(
        "Loaded %d items for %s", len(items_config.items), items_config.store.name
    )

    app = create_bot(settings, items_config)
    logging.info("Starting Telegram bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
