"""
get_token.py - Use Playwright to obtain WhaleGuard anti-bot token from browser.

This script:
1. Opens the flights search page in a real browser (via Playwright)
2. Intercepts the batchSearch API request
3. Extracts token, w-payload-source, and cookies
4. Returns them for analysis

⚠️  Research结论: token 是会话级的，无法在浏览器外复用
   - 每次新建浏览器会话，token 都会变化
   - w-payload-source 是请求级的，每个请求都不同
   - 纯 requests 无法跨会话使用捕获的 token

实际方案：纯浏览器自动化（Plan B）

Requires: playwright (pip install playwright && playwright install chromium)
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright, Route, Request

logger = logging.getLogger(__name__)


@dataclass
class TokenData:
    """Container for captured anti-bot parameters."""
    token: str
    w_payload_source: str
    transaction_id: str
    sign: str
    cookies: dict
    raw_url: str

    def is_valid(self) -> bool:
        """Check if token data looks valid (non-empty critical fields)."""
        return bool(self.token and self.w_payload_source and self.transaction_id)

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "w_payload_source": self.w_payload_source,
            "transaction_id": self.transaction_id,
            "sign": self.sign,
            "cookies": self.cookies,
            "raw_url": self.raw_url,
        }


def capture_token(
    search_url: str = "https://flights.ctrip.com/online/list/oneway-ckg-yty?_=1&depdate=2026-09-01&cabin=y_s&adult=1",
    headless: bool = True,
    timeout_ms: int = 30000,
) -> Optional[TokenData]:
    """
    Open the search page in a browser and capture the batchSearch token.

    Args:
        search_url: The flights search page URL to open
        headless: Whether to run browser in headless mode
        timeout_ms: Maximum time to wait for batchSearch request (ms)

    Returns:
        TokenData if successful, None otherwise
    """
    captured = {"data": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()

        def handle_route(route: Route, request: Request) -> None:
            """Intercept batchSearch requests and extract anti-bot headers."""
            if "batchSearch" in request.url:
                headers = request.all_headers()
                token = headers.get("token", "")
                w_payload = headers.get("w-payload-source", "")
                tx_id = headers.get("transactionid", "")
                sign = headers.get("sign", "")

                if token:
                    # Get cookies from the browser context
                    all_cookies = context.cookies()
                    cookie_dict = {c["name"]: c["value"] for c in all_cookies}

                    captured["data"] = TokenData(
                        token=token,
                        w_payload_source=w_payload,
                        transaction_id=tx_id,
                        sign=sign,
                        cookies=cookie_dict,
                        raw_url=request.url,
                    )
                    logger.info("Captured token: %s...", token[:30])
                else:
                    logger.warning("batchSearch intercepted but no token found")

            route.continue_()

        # Register route handler for batchSearch
        page.route("**/batchSearch**", handle_route)

        try:
            logger.info("Navigating to %s", search_url)
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Wait for batchSearch to fire (it triggers automatically on page load)
            page.wait_for_timeout(8000)

        except Exception as e:
            logger.error("Error during page load: %s", e)
        finally:
            browser.close()

    return captured["data"]


def main():
    """CLI entry point for testing."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== Playwright Token Capture ===\n")
    print("Launching browser to capture WhaleGuard token...\n")

    token_data = capture_token(headless=True)

    if token_data and token_data.is_valid():
        print("✅ Token captured successfully!\n")
        print(f"Token            : {token_data.token[:50]}...")
        print(f"W-Payload-Source : {token_data.w_payload_source[:50]}...")
        print(f"TransactionID    : {token_data.transaction_id}")
        print(f"Sign             : {token_data.sign}")
        print(f"Cookies count    : {len(token_data.cookies)}")
        print(f"URL              : {token_data.raw_url[:80]}...")
        print()
        print("⚠️  NOTE: Token is session-level and CANNOT be reused outside this browser session.")
        print("   Using batch_query.py with this token will result in HTTP 432.")
        print("   For working solution, use pure browser automation (Plan B).")

        # Save to JSON for analysis
        output_path = __file__.replace("get_token.py", "token_cache.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(token_data.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\nToken data saved to: {output_path}")
    else:
        print("❌ Failed to capture token")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
