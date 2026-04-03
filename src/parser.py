import json

import anthropic

from .config import ItemsConfig


class OrderItem:
    def __init__(self, item_key: str, quantity: int, display_name: str):
        self.item_key = item_key
        self.quantity = quantity
        self.display_name = display_name

    def __repr__(self):
        return f"OrderItem({self.item_key!r}, qty={self.quantity})"


class ParseResult:
    def __init__(self, items: list[OrderItem], unknown: list[str]):
        self.items = items
        self.unknown = unknown


def parse_order(text: str, config: ItemsConfig, api_key: str) -> ParseResult:
    """Parse a natural language order into structured items using Claude."""
    item_names = list(config.items.keys())

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = f"""You parse grocery orders. The user will send a natural language message requesting grocery items.

Known items: {json.dumps(item_names)}

Extract each requested item and its quantity. If no quantity is specified, default to 1.
Match user words to the closest known item name (e.g., "granolas" matches "granola", "yogurts" matches "yogurt").

Respond with a JSON object containing:
- "items": list of {{"item": "<known_item_key>", "quantity": <int>}}
- "unknown": list of strings the user mentioned that don't match any known item

Only output valid JSON, nothing else."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": text}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    parsed = json.loads(raw)

    order_items = []
    for entry in parsed.get("items", []):
        key = entry["item"]
        qty = entry.get("quantity", 1)
        if key in config.items:
            order_items.append(
                OrderItem(key, qty, config.items[key].display_name)
            )

    unknown = parsed.get("unknown", [])
    return ParseResult(items=order_items, unknown=unknown)
