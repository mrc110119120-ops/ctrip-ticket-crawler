# db_queries 使用说明

数据库查询封装模块：把高频分析查询写成 Python 函数，避免手写 SQL。

## 主要文件

- `queries.py`：全部查询函数

## 依赖的数据库特性

- `flights.departure_hour`（0-23）：出发小时列，由 `db.py` 在写入时自动填充；
  旧数据库通过 `db.connect()` 的迁移逻辑自动补列并回填
- `v_latest_flights` 视图：每个 (dep, arr, flight_date, itinerary_id) 只保留
  最新一次抓到的价格，"最新一轮"筛选无需手写子查询

## 查询函数

| 函数 | 用途 |
|------|------|
| `get_price_history(conn, itinerary_id, flight_date, dep=None, arr=None)` | 某航班全部历史价格（趋势分析，查询 1） |
| `get_cheapest(conn, dep, arr, date_from, date_to, hour_from=0, hour_to=23, only_latest=True, direct_only=False, limit=10)` | 日期区间内最便宜航班，支持出发时段筛选（查询 2） |
| `get_date_price_summary(conn, dep, arr, date_from, date_to, only_latest=True)` | 每天最低价（日期-价格关系） |
| `get_hour_price_summary(conn, dep, arr, date_from, date_to, only_latest=True)` | 各出发小时最低/均价（时段-价格关系） |
| `get_days_ahead_price(conn, dep, arr, flight_date)` | 提前购票天数 vs 最低价（购票时机预测） |

所有函数返回 `list[dict]`（列名为键）。

## 辅助函数

- `rows_to_dataframe(rows)`：转 pandas DataFrame（未安装 pandas 时返回 list[dict]）
- `to_csv(rows, path)`：导出 CSV（UTF-8 with BOM，Excel 可直接打开）

## 使用示例

```python
import sqlite3
from db_queries import queries

conn = sqlite3.connect("db_storage/flights.db")

# 需求 1：10月1日 EU7347 从 9月1日 至 10月1日每个采集时刻的价格
history = queries.get_price_history(conn, "EU7347", "2026-10-01")

# 需求 2：CKG→YTY 9月1日~10月1日，出发时间 08:00-12:00，最便宜的 5 趟
cheapest = queries.get_cheapest(conn, "CKG", "YTY",
                                "2026-09-01", "2026-10-01",
                                hour_from=8, hour_to=12, limit=5)

# 导出 CSV
queries.to_csv(cheapest, "cheapest.csv")
```
