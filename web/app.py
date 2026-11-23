"""app.py - 机票价格查询与可视化前端（Streamlit）

只读展示 db_storage/flights.db 中的数据（由 scheduler.py 定时写入），
并提供"立即抓取"按钮，实时查询一次并写入数据库。

运行：
    uv run streamlit run web/app.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_queries import queries  # noqa: E402
from db_storage import db  # noqa: E402

DEFAULT_DB = ROOT / "db_storage" / "flights.db"

COLUMN_NAMES = {
    "flight_date": "出发日期",
    "itinerary_id": "航班",
    "departure_time": "出发时间",
    "arrival_time": "到达时间",
    "departure_hour": "出发小时",
    "adult_price": "成人价",
    "child_price": "儿童价",
    "infant_price": "婴儿价",
    "cabin": "舱位",
    "seat_class": "舱位代码",
    "baggage_kg": "行李(kg)",
    "ticket_count": "剩余票数",
    "crawled_at": "抓取时间(UTC)",
    "min_adult_price": "最低价",
    "avg_adult_price": "平均价",
    "flight_count": "航班数",
    "days_ahead": "提前天数",
    "samples": "样本数",
}

st.set_page_config(page_title="机票价格查询", page_icon="✈️", layout="wide")


def show_table(rows: list) -> None:
    """list[dict] -> 中文列名表格"""
    if not rows:
        st.info("没有符合条件的数据")
        return
    df = pd.DataFrame(rows).rename(columns=COLUMN_NAMES)
    st.dataframe(df, width="stretch", hide_index=True)


@st.cache_resource
def get_conn(db_path: str):
    """每个数据库路径一个连接；check_same_thread=False 以便 Streamlit 多线程使用"""
    import sqlite3
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(db.SCHEMA)
    db._migrate(conn)
    return conn


def load_routes(conn) -> list:
    rows = conn.execute(
        "SELECT DISTINCT dep, arr FROM flights ORDER BY dep, arr"
    ).fetchall()
    return [f"{d}-{a}" for d, a in rows]


def date_bounds(conn, dep: str, arr: str):
    lo, hi = conn.execute(
        "SELECT MIN(flight_date), MAX(flight_date) FROM flights WHERE dep=? AND arr=?",
        (dep, arr),
    ).fetchone()
    return date.fromisoformat(lo), date.fromisoformat(hi)


# ---------------------------------------------------------------- 侧边栏
st.sidebar.title("✈️ 查询条件")
db_path = st.sidebar.text_input("数据库路径", str(DEFAULT_DB))
if not Path(db_path).exists():
    st.error(f"数据库不存在：{db_path}。请先运行 scheduler.py 抓取数据。")
    st.stop()

conn = get_conn(db_path)
routes = load_routes(conn)

tab_crawl_only = not routes
if routes:
    route = st.sidebar.selectbox("航线", routes)
    dep, arr = route.split("-")
    lo, hi = date_bounds(conn, dep, arr)
    date_range = st.sidebar.date_input(
        "出发日期区间", (lo, hi), min_value=lo, max_value=hi
    )
    if len(date_range) != 2:
        st.sidebar.info("请选择完整的起止日期")
        st.stop()
    d_from, d_to = (d.isoformat() for d in date_range)
    hour_from, hour_to = st.sidebar.slider("出发时段（小时）", 0, 23, (0, 23))
    direct_only = st.sidebar.checkbox("只看直飞", value=False)
    only_latest = st.sidebar.checkbox(
        "只用最新一轮价格", value=True,
        help="取消勾选则使用全部历史抓取记录",
    )
else:
    st.sidebar.info("数据库暂无航班数据，请先在「立即抓取」标签页抓取。")

# ---------------------------------------------------------------- 主区域
st.title("机票价格查询")

if routes:
    st.caption(f"当前航线 {dep} → {arr}，日期 {d_from} ~ {d_to}")
    tabs = st.tabs(["最便宜航班", "日期与价格", "时段与价格", "价格走势", "立即抓取"])
    tab_cheap, tab_date, tab_hour, tab_trend, tab_crawl = tabs
else:
    (tab_crawl,) = st.tabs(["立即抓取"])

if routes:
    with tab_cheap:
        limit = st.number_input("显示条数", 1, 100, 10)
        rows = queries.get_cheapest(
            conn, dep, arr, d_from, d_to, hour_from, hour_to,
            only_latest=only_latest, direct_only=direct_only, limit=int(limit),
        )
        show_table(rows)

    with tab_date:
        rows = queries.get_date_price_summary(
            conn, dep, arr, d_from, d_to, only_latest=only_latest
        )
        if rows:
            df = pd.DataFrame(rows).set_index("flight_date")
            st.line_chart(df["min_adult_price"], y_label="每日最低价（元）")
        show_table(rows)

    with tab_hour:
        rows = queries.get_hour_price_summary(
            conn, dep, arr, d_from, d_to, only_latest=only_latest
        )
        if rows:
            df = pd.DataFrame(rows).set_index("departure_hour")
            st.bar_chart(df[["min_adult_price", "avg_adult_price"]],
                         y_label="价格（元）", x_label="出发小时")
        show_table(rows)

    with tab_trend:
        st.subheader("单个航班历史价格")
        flights = conn.execute(
            """SELECT DISTINCT flight_date, itinerary_id FROM v_latest_flights
               WHERE dep=? AND arr=? AND flight_date BETWEEN ? AND ?
               ORDER BY flight_date, itinerary_id""",
            (dep, arr, d_from, d_to),
        ).fetchall()
        if flights:
            labels = [f"{d}  {i}" for d, i in flights]
            idx = st.selectbox("选择航班", range(len(flights)),
                               format_func=lambda i: labels[i])
            f_date, f_id = flights[idx]
            hist = queries.get_price_history(conn, f_id, f_date, dep, arr)
            if hist:
                df = pd.DataFrame(hist)
                st.line_chart(df.set_index("crawled_at")["adult_price"],
                              y_label="成人价（元）")
                if len(df) < 2:
                    st.caption("该航班目前只有 1 次抓取记录，多跑几轮调度器后才能看到走势。")
                show_table(hist)
        else:
            st.info("没有可选航班")

        st.subheader("提前购票天数与最低价")
        dates = [r[0] for r in conn.execute(
            """SELECT DISTINCT flight_date FROM flights
               WHERE dep=? AND arr=? AND flight_date BETWEEN ? AND ?
               ORDER BY flight_date""", (dep, arr, d_from, d_to))]
        if dates:
            fd = st.selectbox("出发日期", dates)
            rows = queries.get_days_ahead_price(conn, dep, arr, fd)
            if rows:
                df = pd.DataFrame(rows).set_index("days_ahead")
                st.line_chart(df["min_adult_price"], y_label="最低价（元）",
                              x_label="提前天数")
            show_table(rows)

with tab_crawl:
    st.write("实时调用浏览器抓取一次并写入数据库（需要几秒到几十秒）。")
    c1, c2, c3 = st.columns(3)
    c_dep = c1.text_input("出发（三字码）", "CKG").strip().upper()
    c_arr = c2.text_input("到达（三字码）", "YTY").strip().upper()
    c_date = c3.date_input("日期", date.today() + timedelta(days=1))
    c4, c5 = st.columns(2)
    inc_transfer = c4.checkbox("包含中转", value=False)
    inc_shared = c5.checkbox("包含共享航班", value=False)

    if st.button("开始抓取", type="primary"):
        if not (len(c_dep) == 3 and len(c_arr) == 3):
            st.error("机场代码应为 3 位字母")
        else:
            from browser_automation.flight_crawler import FlightCrawler
            with st.spinner("正在抓取，请稍候..."):
                try:
                    with FlightCrawler(headless=True) as crawler:
                        result = crawler.search(
                            c_dep, c_arr, c_date.isoformat(),
                            include_transfer=inc_transfer,
                            include_shared=inc_shared,
                        )
                except Exception as exc:
                    st.error(f"抓取异常：{exc}")
                    st.stop()
            if result.success:
                run_id = db.start_run(conn)
                n = db.save_search_result(conn, run_id, result)
                db.finish_run(conn, run_id, n, 1, 0)
                st.success(f"抓取成功，写入 {n} 条航班。刷新页面后可在其他标签页查看。")
                show_table([
                    {"itinerary_id": f.itinerary_id,
                     "departure_time": f.departure_time,
                     "arrival_time": f.arrival_time,
                     "adult_price": f.adult_price,
                     "ticket_count": f.ticket_count}
                    for f in result.flights
                ])
            else:
                st.warning(f"未获取到航班：{result.error}")
