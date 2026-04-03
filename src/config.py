from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

CONFIG_DIR = Path(__file__).parent.parent / "config"


class Settings(BaseSettings):
    telegram_bot_token: str
    anthropic_api_key: str
    headless: bool = True
    auth_state_path: str = "auth_state.json"

    model_config = {"env_file": ".env"}


class ItemMapping(BaseModel):
    search_term: str
    display_name: str
    match: str = "strict"  # "strict" or "fuzzy"
    default_quantity: int = 1


class StoreConfig(BaseModel):
    name: str
    instacart_slug: str


class ItemsConfig(BaseModel):
    store: StoreConfig
    items: dict[str, ItemMapping]


def load_items_config(path: Optional[Path] = None) -> ItemsConfig:
    path = path or CONFIG_DIR / "items.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return ItemsConfig(**data)
