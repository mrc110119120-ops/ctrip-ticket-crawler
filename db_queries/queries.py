"""queries.py - 高频分析查询封装

所有函数接收 sqlite3.Connection 作为第一个参数，返回 list[dict]（行名字典）。
"""

import csv
from typing import Optional


def _rows_to_dicts(cur) -> list:
    """把 cursor 结果转成 list[dict]"""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_price_history(conn, itinerary_id: str, flight_date: str,
                      dep: Optional[str] = None, arr: Optional[str] = None) -> list:
    """查询 1：某航班在某 flight_date 的全部历史价格（每个采集时刻一行）

    Args:
        conn: 数据库连接
        itinerary_id: 行程唯一标识（如 "EU7347" 或中转 "CZ2339-CZ3957"）
        flight_date: 出发日期 "YYYY-MM-DD"
        dep/arr: 可选，进一步限定航线（同航班号可能在不同航线复用时）

    Returns:
        按抓取时间升序的记录列表，含 crawled_at、三种价格、ticket_count 等
    """
    sql = """SELECT crawled_at, run_id, dep, arr, flight_date, itinerary_id,
                    departure_time, arrival_time, departure_hour,
                    transfer_count, cross_days, duration_total,
                    adult_price, child_price, infant_price,
                    cabin, seat_class, baggage_kg, free_airport_fee,
                    free_fuel_fee, discount_rate, ticket_count
             FROM flights
             WHERE itinerary_id = ? AND flight_date = ?"""
    params = [itinerary_id, flight_date]
    if dep:
        sql += " AND dep = ?"
        params.append(dep)
    if arr:
        sql += " AND arr = ?"
        params.append(arr)
    sql += " ORDER BY crawled_at"
    return _rows_to_dicts(conn.execute(sql, params))


def get_cheapest(conn, dep: str, arr: str, date_from: str, date_to: str,
                 hour_from: int = 0, hour_to: int = 23,
                 only_latest: bool = True, direct_only: bool = False,
                 limit: int = 10) -> list:
    """查询 2：某航线日期区间内最便宜的航班（可筛选出发时段）

    Args:
        dep/arr: 出发/到达城市 IATA 代码
        date_from/date_to: 出发日期区间（含两端）
        hour_from/hour_to: 出发小时区间（0-23，含两端）
        only_latest: True=只看每个航班最新一次抓到的价格（默认）；
                     False=使用全部历史价格（区间内可能出现同一航班多行）
        direct_only: True=只看直飞
        limit: 返回前 N 个最便宜结果

    Returns:
        按 adult_price 升序的记录列表
    """
    table = "v_latest_flights" if only_latest else "flights"
    sql = f"""SELECT flight_date, itinerary_id, departure_time, departure_hour,
                     arrival_time, adult_price, child_price, infant_price,
                     cabin, seat_class, baggage_kg, ticket_count, crawled_at, run_id
              FROM {table}
              WHERE dep = ? AND arr = ?
                AND flight_date BETWEEN ? AND ?
                AND departure_hour BETWEEN ? AND ?"""
    params = [dep, arr, date_from, date_to, hour_from, hour_to]
    if direct_only:
        sql += " AND transfer_count = 0"
    sql += " ORDER BY adult_price LIMIT ?"
    params.append(limit)
    return _rows_to_dicts(conn.execute(sql, params))


def get_date_price_summary(conn, dep: str, arr: str, date_from: str,
                           date_to: str, only_latest: bool = True) -> list:
    """航线日期区间内每天最低价（分析日期与价格的关系）"""
    table = "v_latest_flights" if only_latest else "flights"
    sql = f"""SELECT flight_date, MIN(adult_price) AS min_adult_price,
                     COUNT(*) AS flight_count
              FROM {table}
              WHERE dep = ? AND arr = ?
                AND flight_date BETWEEN ? AND ?
              GROUP BY flight_date ORDER BY flight_date"""
    return _rows_to_dicts(conn.execute(sql, [dep, arr, date_from, date_to]))


def get_hour_price_summary(conn, dep: str, arr: str, date_from: str,
                           date_to: str, only_latest: bool = True) -> list:
    """航线出发小时与最低价的关系（分析时段与价格的关系）"""
    table = "v_latest_flights" if only_latest else "flights"
    sql = f"""SELECT departure_hour, MIN(adult_price) AS min_adult_price,
                     AVG(adult_price) AS avg_adult_price, COUNT(*) AS flight_count
              FROM {table}
              WHERE dep = ? AND arr = ?
                AND flight_date BETWEEN ? AND ?
                AND departure_hour >= 0
              GROUP BY departure_hour ORDER BY departure_hour"""
    return _rows_to_dicts(conn.execute(sql, [dep, arr, date_from, date_to]))


def get_days_ahead_price(conn, dep: str, arr: str, flight_date: str) -> list:
    """提前购票天数与最低价的关系（预测"提前几天买最便宜"）

    days_ahead = flight_date - crawled_at 的天数
    """
    sql = """SELECT CAST(julianday(flight_date) - julianday(crawled_at) AS INT)
                     AS days_ahead,
                    MIN(adult_price) AS min_adult_price, COUNT(*) AS samples
             FROM flights
             WHERE dep = ? AND arr = ? AND flight_date = ?
             GROUP BY days_ahead ORDER BY days_ahead"""
    return _rows_to_dicts(conn.execute(sql, [dep, arr, flight_date]))


def rows_to_dataframe(rows: list):
    """查询结果转 pandas DataFrame；未安装 pandas 时原样返回 list[dict]"""
    try:
        import pandas as pd
        return pd.DataFrame(rows)
    except ImportError:
        return rows


def to_csv(rows: list, path: str) -> None:
    """查询结果导出为 CSV（UTF-8 with BOM，Excel 可直接打开）"""
    if not rows:
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            csv.writer(fp).writerow([])
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
