"""
flight_crawler.py - 纯浏览器自动化爬取携程机票价格（方案 B）

每个查询都使用 Playwright 打开浏览器，等待页面加载完成，
从 DOM 或网络响应中提取机票价格信息。

优点：最稳定，完全模拟真实用户，不受 token/w-payload-source 限制
缺点：速度较慢，每个查询都需要加载页面
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Route

logger = logging.getLogger(__name__)

# 航班数据提取 JS（在浏览器 DOM 中一次性提取，比 query_selector_all 更可靠）
EXTRACT_FLIGHTS_JS = """
() => {
    const flights = [];
    const items = document.querySelectorAll('.flight-item.domestic');
    items.forEach(item => {
        const flight = {};
        const airlineEl = item.querySelector('.flight-airline');
        if (airlineEl) {
            const text = airlineEl.innerText;
            const match = text.match(/([A-Z]\\d{4}|[A-Z]{2}\\d{4}|G\\d{5})/);
            if (match) flight.flightNo = match[1];
            flight.airline = text.replace(/([A-Z]\\d{4}|[A-Z]{2}\\d{4}|G\\d{5}).*/, '').trim();
        }
        const departBox = item.querySelector('.depart-box');
        if (departBox) {
            const timeEl = departBox.querySelector('.time');
            if (timeEl) flight.departureTime = timeEl.innerText.trim();
            const airportEl = departBox.querySelector('.airport');
            if (airportEl) flight.departureAirport = airportEl.innerText.trim();
        }
        const arrivalBox = item.querySelector('.arrive-box') || item.querySelector('.arrival-box');
        if (arrivalBox) {
            const timeEl = arrivalBox.querySelector('.time');
            if (timeEl) flight.arrivalTime = timeEl.innerText.trim();
            const airportEl = arrivalBox.querySelector('.airport');
            if (airportEl) flight.arrivalAirport = airportEl.innerText.trim();
        }
        const priceEl = item.querySelector('.price');
        if (priceEl) {
            const priceMatch = priceEl.innerText.match(/(\\d+)/);
            if (priceMatch) flight.price = parseInt(priceMatch[1]);
        }
        if (flight.flightNo || flight.price > 0) flights.push(flight);
    });
    return flights;
}
"""

# 会话建立所需的关键 cookie（由首页 JS 生成，缺少会导致"未找到航班"）
SESSION_KEY_COOKIES = {"_bfa", "FVP"}


@dataclass
class FlightInfo:
    """航班信息数据类"""
    flight_no: str = ""
    airline: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    departure_airport: str = ""
    arrival_airport: str = ""
    price: int = 0
    cabin: str = ""
    duration: str = ""


@dataclass
class SearchResult:
    """搜索结果数据类"""
    dep: str = ""
    arr: str = ""
    date: str = ""
    flights: list = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)
    success: bool = False
    error: str = ""


class FlightCrawler:
    """携程机票纯浏览器自动化爬虫"""

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self._session_ready = False  # 首页会话（关键 cookie）是否已建立

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """启动浏览器"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        self.page = self.context.new_page()
        logger.info("Browser started (headless=%s)", self.headless)

    def stop(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Browser stopped")

    def _ensure_session(self, timeout_ms: int = 30000):
        """
        确保首页会话已建立（关键 cookie 生成）。

        首次查询时访问首页并轮询等待 _bfa/FVP cookie 出现（事件驱动，
        通常 1-2 秒即可就绪）；会话已建立时直接跳过。
        """
        if self._session_ready:
            return
        logger.info("Visiting homepage to establish session...")
        self.page.goto("https://flights.ctrip.com/", wait_until="domcontentloaded", timeout=timeout_ms)
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            names = {c["name"] for c in self.context.cookies()}
            if SESSION_KEY_COOKIES <= names:
                self._session_ready = True
                logger.info("Session established, key cookies: %s", sorted(SESSION_KEY_COOKIES))
                return
            self.page.wait_for_timeout(200)
        raise RuntimeError("Session cookies not established within timeout")

    def search(
        self,
        dep: str,
        arr: str,
        date: str,
        cabin: str = "y_s",
        timeout_ms: int = 30000,
    ) -> SearchResult:
        """
        搜索机票价格

        Args:
            dep: 出发城市 IATA 代码（如 "CKG"）
            arr: 到达城市 IATA 代码（如 "YTY"）
            date: 出发日期（格式：YYYY-MM-DD）
            cabin: 舱位类型（y_s=经济/超经, y_s_c_f=不限, c_f=公务/头等）
            timeout_ms: 超时时间（毫秒）

        Returns:
            SearchResult 搜索结果对象
        """
        result = SearchResult(dep=dep, arr=arr, date=date)

        try:
            # 访问主页建立会话/cookies（首次查询时才需要，会话建立后跳过）
            self._ensure_session(timeout_ms)

            # 构建搜索 URL
            url = (
                f"https://flights.ctrip.com/online/list/oneway-{dep.lower()}-{arr.lower()}"
                f"?_=1&depdate={date}&cabin={cabin}&adult=1"
            )

            # 等待 batchSearch 响应到达（事件等待，响应一到立即继续）
            logger.info("Navigating to: %s", url)
            with self.page.expect_response(
                lambda r: "batchsearch" in r.url.lower(), timeout=timeout_ms
            ) as resp_info:
                self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            response = resp_info.value
            logger.info("batchSearch responded (HTTP %s)", response.status)

            # 响应到达 ≠ DOM 渲染完成：短等待 + 重试，直到 DOM 出现航班数据
            flights_data = []
            for wait_ms in (300, 500, 800, 1000, 1500, 2000):
                self.page.wait_for_timeout(wait_ms)
                flights_data = self.page.evaluate(EXTRACT_FLIGHTS_JS)
                if flights_data:
                    break

            # 转换为我们数据类
            flights = []
            for data in flights_data:
                flight = FlightInfo(
                    flight_no=data.get("flightNo", ""),
                    airline=data.get("airline", ""),
                    departure_time=data.get("departureTime", ""),
                    arrival_time=data.get("arrivalTime", ""),
                    departure_airport=data.get("departureAirport", ""),
                    arrival_airport=data.get("arrivalAirport", ""),
                    price=data.get("price", 0),
                )
                flights.append(flight)

            result.flights = flights
            result.success = len(flights) > 0

            if not result.success:
                result.error = "No flights found"

            logger.info("Found %d flights for %s -> %s (%s)", len(flights), dep, arr, date)

        except Exception as e:
            result.error = str(e)
            logger.error("Search failed: %s", e)

        return result

    def _extract_flights_from_dom(self) -> list:
        """从页面 DOM 提取航班信息"""
        flights = []

        # 携程实际结构: .flight-list > .flight-item.domestic > .flight-box > .flight-row
        # 使用 evaluate 来获取数量（更可靠）
        count = self.page.evaluate("document.querySelectorAll('.flight-item.domestic').length")
        logger.info("Found %d flight-item.domestic elements", count)

        if count == 0:
            # 回退：尝试其他选择器
            count = self.page.evaluate("document.querySelectorAll('.flight-item').length")
            logger.info("Found %d .flight-item elements", count)

        flight_items = self.page.query_selector_all(".flight-item.domestic")

        for item in flight_items:
            flight = FlightInfo()

            # 提取航空公司和航班号
            airline_el = item.query_selector(".flight-airline")
            if airline_el:
                full_text = airline_el.inner_text().strip()
                # 提取航班号（如 9C6250, G56209）
                match = re.search(r'([A-Z]\d{4}|[A-Z]{2}\d{4}|G\d{5})', full_text)
                if match:
                    flight.flight_no = match.group(1)
                # 提取航空公司
                airline_name = re.sub(r'([A-Z]\d{4}|[A-Z]{2}\d{4}|G\d{5}).*', '', full_text).strip()
                flight.airline = airline_name

            # 提取时间 - .depart-box > .time
            depart_box = item.query_selector(".depart-box")
            if depart_box:
                time_el = depart_box.query_selector(".time")
                if time_el:
                    flight.departure_time = time_el.inner_text().strip()
                airport_el = depart_box.query_selector(".airport")
                if airport_el:
                    flight.departure_airport = airport_el.inner_text().strip()

            # 提取到达信息 - .arrival-box
            arrival_box = item.query_selector(".arrival-box")
            if arrival_box:
                time_el = arrival_box.query_selector(".time")
                if time_el:
                    flight.arrival_time = time_el.inner_text().strip()
                airport_el = arrival_box.query_selector(".airport")
                if airport_el:
                    flight.arrival_airport = airport_el.inner_text().strip()

            # 提取价格 - .flight-price .price
            price_el = item.query_selector(".flight-price .price, .price")
            if price_el:
                price_text = price_el.inner_text().strip()
                price_match = re.search(r'(\d+)', price_text.replace(',', ''))
                if price_match:
                    flight.price = int(price_match.group(1))

            if flight.flight_no or flight.price > 0:
                flights.append(flight)

        return flights

    def _extract_flights_from_response(self, response: dict) -> list:
        """从 batchSearch API 响应提取航班信息"""
        flights = []

        # 根据实际响应结构调整
        data = response.get("data", response)
        flight_list = data.get("flightList", data.get("flights", []))

        for item in flight_list:
            flight = FlightInfo()
            flight.flight_no = item.get("flightNo", item.get("flightNumber", ""))
            flight.airline = item.get("airlineName", item.get("airline", ""))
            flight.departure_time = item.get("departureTime", "")
            flight.arrival_time = item.get("arrivalTime", "")
            flight.departure_airport = item.get("departureAirport", "")
            flight.arrival_airport = item.get("arrivalAirport", "")
            flight.price = item.get("price", item.get("lowestPrice", 0))
            flight.cabin = item.get("cabin", "")
            flight.duration = item.get("duration", "")
            flights.append(flight)

        return flights

    def batch_search(
        self,
        queries: list[dict],
        delay_range: tuple = (2, 5),
    ) -> list:
        """
        批量搜索

        Args:
            queries: 查询列表，每个元素为 dict: {dep, arr, date, cabin}
            delay_range: 查询间随机延迟范围（秒）

        Returns:
            SearchResult 列表
        """
        results = []
        for i, q in enumerate(queries):
            logger.info(
                "Batch search %d/%d: %s -> %s (%s)",
                i + 1, len(queries), q["dep"], q["arr"], q["date"]
            )
            result = self.search(
                dep=q["dep"],
                arr=q["arr"],
                date=q["date"],
                cabin=q.get("cabin", "y_s"),
            )
            results.append(result)

            # 随机延迟，避免被检测
            if i < len(queries) - 1:
                delay = random.uniform(*delay_range)
                logger.debug("Waiting %.1f seconds before next search", delay)
                time.sleep(delay)

        return results


def main():
    """CLI 入口"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== 携程机票纯浏览器自动化爬取 ===\n")

    queries = [
        # {"dep": "PEK", "arr": "SHA", "date": "2026-09-01"},  # 北京→上海（热门航线）
        # {"dep": "SHA", "arr": "PEK", "date": "2026-09-05"},  # 上海→北京
        {"dep": "CKG", "arr": "YTY", "date": "2026-09-01"},  # 重庆→扬州
    ]

    with FlightCrawler(headless=True) as crawler:
        print(f"执行 {len(queries)} 个查询...\n")
        results = crawler.batch_search(queries)

        # 显示结果
        print("\n=== 结果 ===\n")
        for r in results:
            status = "[OK]" if r.success else "[FAIL]"
            print(f"{status} {r.dep} -> {r.arr} ({r.date})")
            if r.success:
                print(f"   找到 {len(r.flights)} 个航班:")
                for f in r.flights[:3]:  # 只显示前 3 个
                    print(f"   - {f.flight_no or 'N/A'}: price={f.price} ({f.departure_time}-{f.arrival_time})")
                if len(r.flights) > 3:
                    print(f"   ... 还有 {len(r.flights) - 3} 个航班")
            else:
                print(f"   错误: {r.error}")
            print()

        # 保存详细结果到 JSON
        output_path = __file__.replace("flight_crawler.py", "results.json")
        save_data = []
        for r in results:
            save_data.append({
                "dep": r.dep,
                "arr": r.arr,
                "date": r.date,
                "success": r.success,
                "error": r.error,
                "flights": [f.__dict__ for f in r.flights],
            })
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"详细结果已保存到: {output_path}")


if __name__ == "__main__":
    # 通过 PYTHONIOENCODING=utf-8 环境变量运行可避免 Windows GBK 编码问题
    main()
