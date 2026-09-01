"""scheduler.py - 定时爬取调度器

每隔固定时间，爬取当日起往后 N 天内每天的航班价格，
写入 SQLite 数据库（三表结构见 db.py）。

所有参数（航线、间隔、天数、起始偏移、是否含中转/共享、数据库路径）
均从配置文件（默认 routes.json）读取，命令行只保留两个参数：
    --once     只执行一轮后退出（测试用）
    --config   配置文件路径（默认与本脚本同目录的 routes.json）

配置文件格式（routes.json）：
{
  "routes": [
    {"dep": "CKG", "arr": "YTY"},
    {"dep": "PEK", "arr": "SHA"}
  ],
  "interval_minutes": 60,      # 两轮抓取间隔（分钟）
  "days": 30,                  # 从今天起往后抓取的天数
  "start_offset": 0,           # 起始日期偏移（0=今天，1=明天）
  "include_transfer": false,   # 是否包含中转航班
  "include_shared": false,     # 是否包含共享航班
  "db": "flights.db"           # SQLite 数据库路径（相对配置文件所在目录）
}
"""

import argparse
import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from browser_automation.flight_crawler import FlightCrawler  # noqa: E402
from db_storage import db  # noqa: E402

logger = logging.getLogger("scheduler")

DEFAULT_CONFIG = Path(__file__).parent / "routes.json"

# 配置文件可用的键及其类型/默认值（routes 为必填项，单独处理）
CONFIG_DEFAULTS = {
    "interval_minutes": 60,
    "days": 30,
    "start_offset": 0,
    "include_transfer": False,
    "include_shared": False,
    "db": "flights.db",
}


def load_config(config_path: str) -> dict:
    """读取配置文件，返回合并默认值后的完整配置"""
    with open(config_path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    routes = data.get("routes", [])
    if not routes:
        raise ValueError(f"配置文件 {config_path} 中没有航线（routes）")
    cfg = dict(CONFIG_DEFAULTS)
    for key in CONFIG_DEFAULTS:
        if key in data:
            cfg[key] = data[key]
    cfg["routes"] = routes
    # db 相对路径基于配置文件所在目录解析
    db_path = Path(cfg["db"])
    if not db_path.is_absolute():
        db_path = Path(config_path).parent / db_path
    cfg["db_path"] = str(db_path)
    return cfg


def build_dates(days: int, start_offset: int = 0) -> list:
    """生成要抓取的日期列表：当日起（可偏移）往后 days 天"""
    today = date.today()
    return [
        (today + timedelta(days=start_offset + i)).isoformat()
        for i in range(days)
    ]


def run_once(conn, run_id: int, routes: list, dates: list,
             include_transfer: bool, include_shared: bool) -> tuple:
    """执行一轮抓取：所有航线 × 所有日期。返回 (ok, failed, total_flights)"""
    ok = failed = total = 0
    with FlightCrawler(headless=True) as crawler:
        for route in routes:
            for d in dates:
                tag = f"{route['dep']}->{route['arr']} {d}"
                try:
                    logger.info("查询 %s", tag)
                    result = crawler.search(
                        route["dep"], route["arr"], d,
                        include_transfer=include_transfer,
                        include_shared=include_shared,
                    )
                    if result.success:
                        n = db.save_search_result(conn, run_id, result)
                        ok += 1
                        total += n
                        logger.info("  %s: 写入 %d 条航班", tag, n)
                    else:
                        failed += 1
                        logger.warning("  %s: 失败 - %s", tag, result.error)
                except Exception as exc:  # 单个查询失败不影响整轮
                    failed += 1
                    logger.error("  %s: 异常 - %s", tag, exc)
    return ok, failed, total


def main() -> None:
    parser = argparse.ArgumentParser(description="携程机票定时爬取调度器")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="配置文件 JSON 路径（默认 routes.json）")
    parser.add_argument("--once", action="store_true",
                        help="只执行一轮后退出（测试用）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config(args.config)
    dates = build_dates(cfg["days"], cfg["start_offset"])
    conn = db.connect(cfg["db_path"])
    logger.info("配置文件：%s", args.config)
    logger.info("航线 %d 条，日期 %d 天（%s ~ %s），间隔 %.0f 分钟",
                len(cfg["routes"]), len(dates), dates[0], dates[-1],
                cfg["interval_minutes"])
    logger.info("包含中转：%s，包含共享：%s",
                cfg["include_transfer"], cfg["include_shared"])
    logger.info("数据库：%s", cfg["db_path"])

    while True:
        run_id = db.start_run(conn)
        logger.info("===== 第 %d 轮开始 =====", run_id)
        ok, failed, total = run_once(
            conn, run_id, cfg["routes"], dates,
            cfg["include_transfer"], cfg["include_shared"],
        )
        db.finish_run(conn, run_id, total, ok, failed)
        logger.info("===== 第 %d 轮结束：成功 %d 查询，失败 %d，航班 %d 条 =====",
                    run_id, ok, failed, total)
        if args.once:
            break
        logger.info("休眠 %.0f 分钟后开始下一轮...", cfg["interval_minutes"])
        time.sleep(cfg["interval_minutes"] * 60)

    conn.close()


if __name__ == "__main__":
    main()

