from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright, Page, BrowserContext

logger = logging.getLogger(__name__)


@dataclass
class AddItemResult:
    success: bool
    matched_name: str = ""  # name of the product that was found
    reason: str = ""  # failure reason if not successful


@dataclass
class SearchResult:
    name: str
    price: str
    index: int


@dataclass
class CartItem:
    name: str
    quantity: int
    price: str


@dataclass
class CartSummary:
    items: list[CartItem]
    total: str


async def _human_delay(min_s: float = 1.0, max_s: float = 3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


class InstacartAutomation:
    def __init__(self, store_slug: str, auth_state_path: str, headless: bool = True):
        self.store_slug = store_slug
        self.auth_state_path = auth_state_path
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

        state_path = Path(self.auth_state_path)
        if state_path.exists():
            self._context = await self._browser.new_context(storage_state=str(state_path))
        else:
            self._context = await self._browser.new_context()

        self._page = await self._context.new_page()

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def login(self):
        """Open browser for manual login. Call finish_login() after user logs in."""
        self._login_pw = await async_playwright().start()
        self._login_browser = await self._login_pw.chromium.launch(headless=False)
        self._login_context = await self._login_browser.new_context()
        page = await self._login_context.new_page()
        await page.goto("https://www.instacart.com/login")

    async def finish_login(self):
        """Save session state and close the login browser."""
        await self._login_context.storage_state(path=self.auth_state_path)
        await self._login_context.close()
        await self._login_browser.close()
        await self._login_pw.stop()
        self._login_pw = None
        self._login_browser = None
        self._login_context = None

    async def screenshot(self) -> bytes | None:
        """Take a screenshot and return the PNG bytes."""
        try:
            return await self._page.screenshot(timeout=30000)
        except Exception:
            return None

    async def add_item(self, search_term: str, display_name: str,
                      quantity: int = 1, match: str = "strict") -> AddItemResult:
        """Search for an item and add it to the cart with the specified quantity.

        Args:
            search_term: What to type into Instacart search
            display_name: Expected product name for strict matching
            quantity: How many to add
            match: "strict" requires the first result to match display_name,
                   "fuzzy" accepts the first result
        """
        page = self._page
        url = f"https://www.instacart.com/store/{self.store_slug}/s?k={quote(search_term)}"

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # Get the first Add button and read its aria-label for the clean product name
        # aria-label format: "Add 1 ct Purely Elizabeth Original Ancient Grain Granola, Organic"
        add_button = page.locator('button:has-text("Add")').first
        try:
            await add_button.wait_for(timeout=15000)
            aria_label = (await add_button.get_attribute("aria-label") or "").strip()
            # Strip the "Add 1 ct " or "Add 1 item " prefix
            found_name = aria_label
            for prefix in ("Add 1 ct ", "Add 1 item "):
                if found_name.startswith(prefix):
                    found_name = found_name[len(prefix):]
                    break
        except Exception as e:
            logger.error("No products found for '%s': %s", search_term, e)
            return AddItemResult(success=False, reason="No products found")

        # For strict matching, verify the product name contains key words
        if match == "strict":
            found_lower = found_name.lower()
            display_lower = display_name.lower()
            # Check that all significant words from display_name appear in the found product
            keywords = [w for w in display_lower.split()
                        if len(w) > 2 and w.strip("(),") not in ("oz", "the")]
            missing = [w for w in keywords if w not in found_lower]
            if missing:
                logger.warning(
                    "Strict match failed for '%s': found '%s', missing keywords: %s",
                    display_name, found_name, missing,
                )
                return AddItemResult(
                    success=False,
                    matched_name=found_name,
                    reason=f"Strict match failed. Found: {found_name}",
                )

        # Click Add
        try:
            await add_button.click()
            logger.info("Added item: %s (found: %s)", search_term, found_name)
            await _human_delay(1.0, 2.0)
        except Exception as e:
            logger.error("Failed to click Add for '%s': %s", search_term, e)
            return AddItemResult(success=False, reason=f"Could not click Add: {e}")

        # Increment quantity if needed
        for i in range(quantity - 1):
            increment = page.locator('button[aria-label*="Increment" i]').first
            try:
                await increment.wait_for(timeout=5000)
                await increment.click()
                logger.info("Incremented quantity to %d", i + 2)
                await _human_delay(0.5, 1.0)
            except Exception:
                logger.warning("Could not increment quantity past %d", i + 1)
                break

        return AddItemResult(success=True, matched_name=found_name[:120])

    async def search(self, query: str) -> list[SearchResult]:
        """Search for a product and return the top results."""
        page = self._page
        url = f"https://www.instacart.com/store/{self.store_slug}/s?k={quote(query)}"

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        results = []
        # Product links contain the product name and price
        product_links = page.locator('a[href*="/products/"]')
        count = await product_links.count()

        for i in range(min(count, 6)):
            el = product_links.nth(i)
            text = await el.text_content() or ""
            # Extract name and price from the text
            text = text.strip()
            if text:
                results.append(SearchResult(name=text[:120], price="", index=i))

        return results

    async def add_item_by_index(self, index: int, quantity: int = 1) -> bool:
        """Add the item at the given index on the current search results page."""
        page = self._page
        add_buttons = page.locator('button:has-text("Add")')
        count = await add_buttons.count()

        if index >= count:
            return False

        try:
            await add_buttons.nth(index).click()
            logger.info("Clicked Add button at index %d", index)
            await _human_delay(1.0, 2.0)
        except Exception as e:
            logger.error("Failed to click Add at index %d: %s", index, e)
            return False

        for i in range(quantity - 1):
            increment = page.locator('button[aria-label*="Increment" i]').first
            try:
                await increment.wait_for(timeout=5000)
                await increment.click()
                await _human_delay(0.5, 1.0)
            except Exception:
                break

        return True

    async def get_cart_summary(self) -> CartSummary | None:
        """Open the floating cart panel and scrape the summary."""
        page = self._page

        # Click the floating cart button to open cart panel
        cart_btn = page.locator('[data-testid="floating-cart-button"], [aria-label*="View Cart" i]').first
        try:
            await cart_btn.wait_for(timeout=10000)
            cart_label = await cart_btn.get_attribute("aria-label") or ""
            logger.info("Cart button: %s", cart_label)
            await cart_btn.click()
            await asyncio.sleep(3)
        except Exception as e:
            logger.error("Could not open cart: %s", e)
            return None

        # Try to scrape cart items from the panel/page
        # Return a simple summary based on what we can read
        items = []
        total = ""

        # Look for item rows in the cart
        cart_item_selectors = [
            '[data-testid="cart_item"]',
            '[class*="CartItem"]',
            'li[class*="item" i]',
        ]
        for sel in cart_item_selectors:
            count = await page.locator(sel).count()
            if count > 0:
                logger.info("Found %d cart items with selector '%s'", count, sel)
                for i in range(count):
                    el = page.locator(sel).nth(i)
                    text = await el.text_content() or ""
                    items.append(CartItem(name=text.strip()[:80], quantity=1, price=""))
                break

        # If we couldn't find structured items, get the cart button text as summary
        if not items:
            try:
                cart_text = await cart_btn.text_content() or ""
                total = cart_text.strip()
            except Exception:
                pass

        return CartSummary(items=items, total=total)

    async def checkout(self) -> bool:
        """Complete the checkout process. Assumes payment and delivery are pre-configured.

        Flow: navigate to store → dismiss overlays → open cart → "Go to checkout"
              → upsell page → "Continue to checkout" → "Place order"
        """
        page = self._page

        # Step 0: Navigate to store page to get a clean state (dismiss any overlays)
        await page.goto(
            f"https://www.instacart.com/store/{self.store_slug}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await asyncio.sleep(5)
        # Dismiss any popups/overlays
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)

        # Step 1: Open cart panel
        cart_btn = page.locator('[data-testid="floating-cart-button"], [aria-label*="View Cart" i]').first
        try:
            await cart_btn.wait_for(timeout=10000)
            await cart_btn.click(force=True)
            await asyncio.sleep(3)
        except Exception as e:
            logger.error("Could not open cart: %s", e)
            return False

        # Step 2: Click "Go to checkout"
        go_btn = page.locator('button:has-text("Go to checkout"), a:has-text("Go to checkout")').first
        try:
            await go_btn.wait_for(timeout=10000)
            await go_btn.click()
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Could not click Go to checkout: %s", e)
            return False

        # Step 3: Skip upsell page — click "Continue to checkout"
        continue_btn = page.locator('button:has-text("Continue to checkout"), a:has-text("Continue to checkout")').first
        try:
            await continue_btn.wait_for(timeout=10000)
            await continue_btn.click()
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Could not click Continue to checkout: %s", e)
            return False

        # Step 4: Place order
        place_order_btn = page.locator('button:has-text("Place order")').first
        try:
            await place_order_btn.wait_for(timeout=15000)
            await place_order_btn.click()
            logger.info("Clicked Place order")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Could not click Place order: %s", e)
            return False

        # Wait for confirmation page
        try:
            await page.wait_for_url("**/orders/**", timeout=30000)
        except Exception:
            pass

        return True
