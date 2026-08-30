"""
batch_query.py - Demonstrates why token reuse fails (for educational purposes).

⚠️  THIS APPROACH DOES NOT WORK ⚠️

Research结论:
- `token` 是会话级的，每次新建浏览器会话都会变化
- `w-payload-source` 是请求级的，每个请求都不同
- 纯 requests 无法跨浏览器会话复用 token

This script attempts to use a captured token with pure requests.
Expected result: HTTP 432 (WhaleGuard block) for all queries.

For actual flight price queries, use pure browser automation (Plan B).
See RESEARCH.md for details.
"""

import json
import logging
import os
import random
import sys
import time
from typing import Optional

# Ensure project root is on path for importing pure_requests
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import requests

try:
    from pure_requests.ctrip_flight import (
        compute_sign,
        generate_transaction_id,
        build_search_body,
    )
except ImportError:
    compute_sign = None
    generate_transaction_id = None
    build_search_body = None

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://flights.ctrip.com/international/search/api/search/batchSearch"
    "?v={random_v}"
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


class FlightQueryClient:
    """Client for querying flight prices using a captured WhaleGuard token."""

    def __init__(self, token_data: dict):
        self.token = token_data.get("token", "")
        self.w_payload_source = token_data.get("w_payload_source", "")
        self.cookies = token_data.get("cookies", {})
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json;charset=utf-8",
            "Origin": "https://flights.ctrip.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        for name, value in self.cookies.items():
            self.session.cookies.set(name, value)

    def query(
        self,
        dep: str,
        arr: str,
        dep_date: str,
        adult: int = 1,
        cabin: str = "Y_S",
    ) -> dict:
        """Query flight prices for a single route and date."""
        tx_id = generate_transaction_id() if generate_transaction_id else _gen_tx()
        sign = compute_sign(tx_id, dep, arr, dep_date) if compute_sign else _calc_sign(tx_id, dep, arr, dep_date)

        url = SEARCH_URL.format(random_v=random.random())

        headers = {
            "Referer": (
                f"https://flights.ctrip.com/online/list/oneway-{dep.lower()}-{arr.lower()}"
                f"?_=1&depdate={dep_date}&cabin=y_s&adult={adult}"
            ),
            "sign": sign,
            "transactionID": tx_id,
            "scope": "d",
            "token": self.token,
            "w-payload-source": self.w_payload_source,
        }

        if build_search_body:
            body = build_search_body(tx_id, dep, arr, dep_date, adult=adult, cabin=cabin)
        else:
            body = _build_body_fallback(tx_id, dep, arr, dep_date, adult, cabin)

        try:
            resp = self.session.post(url, headers=headers, json=body, timeout=30)
            result = {
                "status_code": resp.status_code,
                "reason": resp.reason,
                "url": url,
                "dep": dep,
                "arr": arr,
                "date": dep_date,
            }

            if resp.status_code == 200:
                try:
                    result["data"] = resp.json()
                    result["success"] = True
                except Exception:
                    result["body_preview"] = resp.text[:500]
                    result["success"] = False
            elif resp.status_code == 432:
                result["error"] = "WhaleGuard block - token may have expired"
                result["success"] = False
            else:
                result["body_preview"] = resp.text[:500]
                result["success"] = False

            return result

        except Exception as e:
            return {
                "status_code": 0,
                "error": str(e),
                "dep": dep,
                "arr": arr,
                "date": dep_date,
                "success": False,
            }

    def batch_query(self, queries: list[dict]) -> list[dict]:
        """Execute multiple queries with rate limiting."""
        results = []
        for i, q in enumerate(queries):
            logger.info(
                "Query %d/%d: %s -> %s (%s)",
                i + 1, len(queries), q["dep"], q["arr"], q["dep_date"]
            )
            result = self.query(
                dep=q["dep"],
                arr=q["arr"],
                dep_date=q["dep_date"],
                adult=q.get("adult", 1),
                cabin=q.get("cabin", "Y_S"),
            )
            results.append(result)

            if i < len(queries) - 1:
                delay = random.uniform(1.0, 3.0)
                logger.debug("Waiting %.1f seconds before next query", delay)
                time.sleep(delay)

        return results


# Fallback functions (used if pure_requests not available)
def _gen_tx() -> str:
    import uuid
    return uuid.uuid4().hex


def _calc_sign(tx_id: str, dep: str, arr: str, date: str) -> str:
    import hashlib
    return hashlib.md5((tx_id + dep + arr + date).encode()).hexdigest()


def _build_body_fallback(tx_id: str, dep: str, arr: str, date: str, adult: int = 1, cabin: str = "Y_S") -> dict:
    return {
        "adultCount": adult,
        "childCount": 0,
        "infantCount": 0,
        "flightWay": "S",
        "cabin": cabin,
        "scope": "d",
        "segmentNo": 1,
        "transactionID": tx_id,
        "flightSegments": [{
            "departureCityCode": dep.upper(),
            "arrivalCityCode": arr.upper(),
            "departureDate": date,
            "departureCountryId": 1,
            "arrivalCountryId": 1,
            "departureProvinceId": 4,
            "departureCityId": 4,
            "arrivalProvinceId": 15,
            "arrivalCityId": 15,
            "departureCityTimeZone": 480,
            "arrivalCityTimeZone": 480,
            "timeZone": 480,
        }],
        "directFlight": False,
        "extGlobalSwitches": {"useAllRecommendSwitch": True, "unfoldPriceListSwitch": True},
        "noRecommend": False,
        "extensionAttributes": {"LoggingSampling": False, "isFlightIntlNewUser": False},
    }


def load_token_cache() -> Optional[dict]:
    """Load token data from cache file."""
    cache_path = os.path.join(_HERE, "token_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    """CLI entry point - demonstrates token reuse failure."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== Batch Query with Captured Token ===\n")
    print("⚠️  WARNING: This approach is expected to FAIL with HTTP 432")
    print("   Research shows token is session-level and cannot be reused.\n")

    # Load token
    token_data = load_token_cache()
    if token_data:
        print("Loaded token from cache (token_cache.json)")
        print(f"Token: {token_data.get('token', '')[:50]}...")
        print(f"Note: Token is session-level and will fail outside the browser.\n")
    else:
        print("No token cache found. Please run get_token.py first.")
        print("  python playwright_token/get_token.py\n")
        return 1

    # Create client
    client = FlightQueryClient(token_data)

    # Define batch queries
    queries = [
        {"dep": "CKG", "arr": "YTY", "dep_date": "2026-09-01"},
        {"dep": "CKG", "arr": "YTY", "dep_date": "2026-09-05"},
        {"dep": "CKG", "arr": "YTY", "dep_date": "2026-09-10"},
    ]

    print(f"Executing {len(queries)} queries...\n")
    results = client.batch_query(queries)

    # Display results
    print("\n=== Results ===\n")
    success_count = 0
    for r in results:
        status = "✅" if r.get("success") else "❌"
        print(f"{status} {r['dep']} -> {r['arr']} ({r['date']}): HTTP {r['status_code']}")
        if r.get("success"):
            success_count += 1
            data = r.get("data", {})
            if isinstance(data, dict):
                api_status = data.get("status")
                msg = data.get("message", "")
                print(f"   API status: {api_status}, message: {msg}")
        elif r.get("error"):
            print(f"   Error: {r['error']}")
        print()

    print(f"Summary: {success_count}/{len(queries)} queries succeeded")
    print("\nExpected: 0/N succeeded (token cannot be reused outside browser)")
    print("For working solution, use pure browser automation (Plan B)")
    return 0 if success_count == len(queries) else 1


if __name__ == "__main__":
    exit(main())
