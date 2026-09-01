"""db.py - SQLite 数据库层

三表结构：
  crawl_runs  抓取批次表（每轮定时抓取一行）
  flights     航班主表（一个航班一条数据，带抓取时间戳，保留历史价格）
  segments    航段表（中转航班有多个航段，与 flights 一对多）
"""

import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,               -- 轮次开始时间 UTC
    finished_at   TEXT,                        -- 轮次结束时间（进行中为 NULL）
    total_flights INTEGER DEFAULT 0,           -- 本轮成功抓到的航班总数
    ok_queries    INTEGER DEFAULT 0,           -- 成功的查询数
    failed_queries INTEGER DEFAULT 0           -- 失败的查询数
);

CREATE TABLE IF NOT EXISTS flights (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES crawl_runs(id),
    crawled_at     TEXT NOT NULL,              -- 抓取时间 UTC
    dep            TEXT NOT NULL,              -- 出发城市代码（查询参数）
    arr            TEXT NOT NULL,              -- 到达城市代码（查询参数）
    flight_date    TEXT NOT NULL,              -- 出发日期 "YYYY-MM-DD"（查询参数）
    itinerary_id   TEXT NOT NULL,              -- 行程唯一标识（各段航班号 "-" 拼接）
    departure_time TEXT NOT NULL,              -- 出发日期时间（第一段）
    arrival_time   TEXT NOT NULL,              -- 到达日期时间（最后一段）
    departure_hour INTEGER NOT NULL DEFAULT -1, -- 出发小时（0-23，便于按时段筛选/分析；-1=未知）
    transfer_count INTEGER NOT NULL DEFAULT 0, -- 中转次数（0=直飞）
    cross_days     INTEGER NOT NULL DEFAULT 0, -- 跨天数
    duration_total INTEGER NOT NULL DEFAULT 0, -- 总时长（分钟）
    adult_price    REAL NOT NULL DEFAULT 0,    -- 成人最低价
    child_price    REAL NOT NULL DEFAULT 0,    -- 儿童价（最低档对应）
    infant_price   REAL NOT NULL DEFAULT 0,    -- 婴儿价（最低档对应，无则为 0）
    cabin          TEXT NOT NULL DEFAULT '',   -- 舱位等级（Y/C/F）
    seat_class     TEXT NOT NULL DEFAULT '',   -- 舱位代码（如 K/V/X1）
    baggage_kg     INTEGER NOT NULL DEFAULT 0, -- 免费托运行李额（公斤）
    free_airport_fee INTEGER NOT NULL DEFAULT 0, -- 是否免机建费（0/1）
    free_fuel_fee  INTEGER NOT NULL DEFAULT 0, -- 是否免燃油（0/1）
    discount_rate  REAL NOT NULL DEFAULT 0,    -- 折扣率（0.37=3.7折）
    ticket_count   INTEGER NOT NULL DEFAULT 0  -- 剩余票数（0=未提供）
);
CREATE INDEX IF NOT EXISTS idx_flights_route_date
    ON flights(dep, arr, flight_date, crawled_at);
CREATE INDEX IF NOT EXISTS idx_flights_itinerary
    ON flights(itinerary_id, flight_date, crawled_at);
CREATE INDEX IF NOT EXISTS idx_flights_latest
    ON flights(dep, arr, flight_date, run_id, adult_price);

-- 最新一轮数据视图：每条 (dep, arr, flight_date, itinerary_id) 只保留
-- run_id 最大（最近一次抓到该航班）的一行，免去每次手写子查询
CREATE VIEW IF NOT EXISTS v_latest_flights AS
SELECT f.*
FROM flights f
JOIN (
    SELECT dep, arr, flight_date, itinerary_id, MAX(run_id) AS max_run_id
    FROM flights
    GROUP BY dep, arr, flight_date, itinerary_id
) latest
  ON f.dep = latest.dep AND f.arr = latest.arr
 AND f.flight_date = latest.flight_date
 AND f.itinerary_id = latest.itinerary_id
 AND f.run_id = latest.max_run_id;

CREATE TABLE IF NOT EXISTS segments (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id              INTEGER NOT NULL REFERENCES flights(id),
    seg_index              INTEGER NOT NULL,   -- 航段序号（0 起）
    flight_no              TEXT NOT NULL,      -- 市场航班号
    is_shared              INTEGER NOT NULL DEFAULT 0, -- 是否共享航班（0/1）
    operate_flight_no      TEXT NOT NULL DEFAULT '',   -- 执飞航班号（共享时有值）
    operate_airline_code   TEXT NOT NULL DEFAULT '',
    operate_airline_name   TEXT NOT NULL DEFAULT '',
    airline_code           TEXT NOT NULL DEFAULT '',
    airline_name           TEXT NOT NULL DEFAULT '',
    departure_city_code    TEXT NOT NULL DEFAULT '',
    departure_city_name    TEXT NOT NULL DEFAULT '',
    departure_airport_code  TEXT NOT NULL DEFAULT '',
    departure_airport_name  TEXT NOT NULL DEFAULT '',
    departure_terminal     TEXT NOT NULL DEFAULT '',
    departure_time         TEXT NOT NULL DEFAULT '',
    arrival_city_code      TEXT NOT NULL DEFAULT '',
    arrival_city_name      TEXT NOT NULL DEFAULT '',
    arrival_airport_code   TEXT NOT NULL DEFAULT '',
    arrival_airport_name   TEXT NOT NULL DEFAULT '',
    arrival_terminal       TEXT NOT NULL DEFAULT '',
    arrival_time           TEXT NOT NULL DEFAULT '',
    duration               INTEGER NOT NULL DEFAULT 0  -- 该段时长（分钟）
);
CREATE INDEX IF NOT EXISTS idx_segments_flight ON segments(flight_id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """连接数据库并确保 schema 存在（含旧库迁移）"""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """旧库迁移：为 flights 补充 departure_hour 列并从 departure_time 回填"""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(flights)")]
    if "departure_hour" not in cols:
        conn.execute(
            "ALTER TABLE flights ADD COLUMN departure_hour INTEGER NOT NULL DEFAULT -1"
        )
    # 回填缺失的小时值（departure_time 格式 "YYYY-MM-DD HH:MM:SS"）
    conn.execute(
        """UPDATE flights
           SET departure_hour = CAST(substr(departure_time, 12, 2) AS INTEGER)
           WHERE departure_hour = -1 AND length(departure_time) >= 13"""
    )
    conn.commit()


def _utcnow() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _parse_hour(departure_time: str) -> int:
    """从 "YYYY-MM-DD HH:MM:SS" 中解析出小时（0-23），解析失败返回 -1"""
    try:
        return int(departure_time[11:13])
    except (ValueError, IndexError, TypeError):
        return -1



def start_run(conn: sqlite3.Connection) -> int:
    """开启一轮抓取，返回 run_id"""
    cur = conn.execute(
        "INSERT INTO crawl_runs (started_at) VALUES (?)", (_utcnow(),)
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int,
               total_flights: int, ok_queries: int, failed_queries: int) -> None:
    """结束一轮抓取"""
    conn.execute(
        """UPDATE crawl_runs
           SET finished_at = ?, total_flights = ?, ok_queries = ?, failed_queries = ?
           WHERE id = ?""",
        (_utcnow(), total_flights, ok_queries, failed_queries, run_id),
    )
    conn.commit()



def save_search_result(conn: sqlite3.Connection, run_id: int, result) -> int:
    """把一次 SearchResult 的所有航班写入数据库，返回写入行数"""
    crawled_at = _utcnow()
    n = 0
    for f in result.flights:
        cur = conn.execute(
            """INSERT INTO flights (
                   run_id, crawled_at, dep, arr, flight_date, itinerary_id,
                   departure_time, arrival_time, departure_hour,
                   transfer_count, cross_days,
                   duration_total, adult_price, child_price, infant_price,
                   cabin, seat_class, baggage_kg, free_airport_fee,
                   free_fuel_fee, discount_rate, ticket_count
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, crawled_at, result.dep, result.arr, result.date,
                f.itinerary_id, f.departure_time, f.arrival_time,
                _parse_hour(f.departure_time),
                f.transfer_count, f.cross_days, f.duration_total,
                f.adult_price, f.child_price, f.infant_price,
                f.cabin, f.seat_class, f.baggage_kg,
                int(f.free_airport_fee), int(f.free_fuel_fee),
                f.discount_rate, f.ticket_count,
            ),
        )
        flight_id = cur.lastrowid
        for i, s in enumerate(f.segments):
            conn.execute(
                """INSERT INTO segments (
                       flight_id, seg_index, flight_no, is_shared,
                       operate_flight_no, operate_airline_code,
                       operate_airline_name, airline_code, airline_name,
                       departure_city_code, departure_city_name,
                       departure_airport_code, departure_airport_name,
                       departure_terminal, departure_time,
                       arrival_city_code, arrival_city_name,
                       arrival_airport_code, arrival_airport_name,
                       arrival_terminal, arrival_time, duration
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    flight_id, i, s.flight_no, int(s.is_shared),
                    s.operate_flight_no, s.operate_airline_code,
                    s.operate_airline_name, s.airline_code, s.airline_name,
                    s.departure_city_code, s.departure_city_name,
                    s.departure_airport_code, s.departure_airport_name,
                    s.departure_terminal, s.departure_time,
                    s.arrival_city_code, s.arrival_city_name,
                    s.arrival_airport_code, s.arrival_airport_name,
                    s.arrival_terminal, s.arrival_time, s.duration,
                ),
            )
        n += 1
    conn.commit()
    return n
