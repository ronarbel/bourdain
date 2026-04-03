import io
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, ItemsConfig
from .instacart import InstacartAutomation
from .parser import parse_order

logger = logging.getLogger(__name__)

# Store pending orders awaiting confirmation: chat_id -> parsed order items
_pending_orders: dict[int, list] = {}
# Store login automation instances waiting for /done
_pending_logins: dict[int, InstacartAutomation] = {}
# Store active automation instances for checkout
_active_automations: dict[int, InstacartAutomation] = {}


def create_bot(settings: Settings, items_config: ItemsConfig) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Hi! Send me a grocery order like:\n"
            '"Get 2 granolas and 3 yogurts"\n\n'
            "I'll add items to your Instacart cart at "
            f"{items_config.store.name} and ask for approval before checkout.\n\n"
            "Commands:\n"
            "/login — Log in to Instacart (opens browser)\n"
            "/done — Finish login after logging in\n"
            "/items — Show available items"
        )

    async def cmd_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
        lines = ["Available items:"]
        for key, item in items_config.items.items():
            lines.append(f"  • {key} — {item.display_name}")
        await update.message.reply_text("\n".join(lines))

    async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        await update.message.reply_text("Opening browser for Instacart login...\nLog in, then send /done when finished.")
        automation = InstacartAutomation(
            store_slug=items_config.store.instacart_slug,
            auth_state_path=settings.auth_state_path,
        )
        await automation.login()
        _pending_logins[chat_id] = automation

    async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        automation = _pending_logins.pop(chat_id, None)
        if not automation:
            await update.message.reply_text("No pending login. Use /login first.")
            return
        await automation.finish_login()
        await update.message.reply_text("Login saved! You can now place orders.")

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        chat_id = update.message.chat_id

        # Check if this is a confirmation response
        if chat_id in _pending_orders:
            await _handle_confirmation(update, context, text)
            return

        await _process_order(update, context, text)

    async def _process_order(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        chat_id = update.message.chat_id

        await update.message.reply_text("Parsing your order...")
        result = parse_order(text, items_config, settings.anthropic_api_key)

        if not result.items and not result.unknown:
            await update.message.reply_text(
                "I couldn't find any items in that message. Try something like:\n"
                '"Get 2 granolas and 3 yogurts"'
            )
            return

        lines = ["Here's what I understood:\n"]
        for item in result.items:
            lines.append(f"  • {item.quantity}x {item.display_name}")

        if result.unknown:
            lines.append(f"\nUnknown items (skipped): {', '.join(result.unknown)}")
            lines.append("Use /items to see available items.")

        if result.items:
            lines.append("\nReply YES to add these to your Instacart cart, or NO to cancel.")
            _pending_orders[chat_id] = result.items

        await update.message.reply_text("\n".join(lines))

    async def _handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        chat_id = update.message.chat_id
        pending = _pending_orders.get(chat_id)

        # Handle checkout confirmation (second stage)
        if pending == "__CHECKOUT__":
            await _handle_checkout_confirmation(update, context, text)
            return

        # Handle add-to-cart confirmation (first stage)
        order_items = pending

        if text.upper() in ("NO", "CANCEL", "N"):
            del _pending_orders[chat_id]
            await update.message.reply_text("Order cancelled.")
            return

        if text.upper() not in ("YES", "Y", "YEP", "YEAH", "OK"):
            await update.message.reply_text("Reply YES to confirm or NO to cancel.")
            return

        del _pending_orders[chat_id]
        await update.message.reply_text("Adding items to your Instacart cart...")

        automation = InstacartAutomation(
            store_slug=items_config.store.instacart_slug,
            auth_state_path=settings.auth_state_path,
            headless=settings.headless,
        )

        try:
            await automation.start()

            added = []
            failed = []
            for item in order_items:
                mapping = items_config.items[item.item_key]
                result = await automation.add_item(
                    mapping.search_term, mapping.display_name,
                    item.quantity, mapping.match,
                )
                if result.success:
                    added.append(f"  • {item.quantity}x {item.display_name}")
                else:
                    failed.append(f"  • {item.display_name}")
                    # Send screenshot so user can see what was found
                    screenshot = await automation.screenshot()
                    if screenshot:
                        caption = f"Could not find exact match for {item.display_name}"
                        if result.reason:
                            caption += f"\n{result.reason}"
                        await update.message.reply_photo(
                            photo=io.BytesIO(screenshot), caption=caption
                        )

            status_lines = []
            if added:
                status_lines.append("Added to cart:\n" + "\n".join(added))
            if failed:
                status_lines.append("Failed to add:\n" + "\n".join(failed))

            await update.message.reply_text("\n".join(status_lines))

            # Get cart summary
            await update.message.reply_text("Getting cart summary...")
            summary = await automation.get_cart_summary()
            # Send cart screenshot
            cart_screenshot = await automation.screenshot()
            if cart_screenshot:
                await update.message.reply_photo(
                    photo=io.BytesIO(cart_screenshot), caption="Cart"
                )

            if summary:
                summary_lines = ["Cart summary:"]
                for ci in summary.items:
                    summary_lines.append(f"  • {ci.quantity}x {ci.name} — {ci.price}")
                if summary.total:
                    summary_lines.append(f"\nTotal: {summary.total}")
                summary_lines.append("\nReply CHECKOUT to place the order, or CANCEL to abandon.")
                await update.message.reply_text("\n".join(summary_lines))

                _pending_orders[chat_id] = "__CHECKOUT__"
                _active_automations[chat_id] = automation
            else:
                await update.message.reply_text(
                    "Couldn't read cart summary. Check Instacart manually."
                )
                await automation.close()
        except Exception as e:
            logger.exception("Instacart automation error")
            await update.message.reply_text(f"Error: {e}")
            await automation.close()

    async def _handle_checkout_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        chat_id = update.message.chat_id
        automation = _active_automations.pop(chat_id, None)

        if text.upper() in ("NO", "CANCEL", "N"):
            del _pending_orders[chat_id]
            if automation:
                await automation.close()
            await update.message.reply_text("Checkout cancelled. Items are still in your cart.")
            return

        if text.upper() not in ("CHECKOUT", "YES", "Y", "OK"):
            if automation:
                _active_automations[chat_id] = automation
            await update.message.reply_text("Reply CHECKOUT to place the order, or CANCEL to abandon.")
            return

        del _pending_orders[chat_id]
        await update.message.reply_text("Placing your order...")

        if not automation:
            automation = InstacartAutomation(
                store_slug=items_config.store.instacart_slug,
                auth_state_path=settings.auth_state_path,
                headless=settings.headless,
            )
            await automation.start()

        try:
            success = await automation.checkout()
            if success:
                await update.message.reply_text("Order placed! You should receive a confirmation from Instacart.")
            else:
                await update.message.reply_text("Checkout may not have completed. Please check Instacart directly.")
        except Exception as e:
            logger.exception("Checkout error")
            await update.message.reply_text(f"Checkout error: {e}")
        finally:
            await automation.close()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("items", cmd_items))
    app.add_handler(CommandHandler("login", cmd_login))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app
