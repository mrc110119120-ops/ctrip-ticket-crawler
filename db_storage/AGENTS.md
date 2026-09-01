# db_storage 使用说明

定时爬取 + SQLite 存储：每隔固定时间，爬取当日起往后 N 天内每天的航班价格，
写入数据库，一个航班一条数据（带抓取时间戳，保留历史价格，可分析涨价/降价）。

## 文件结构

- `db.py`：数据库层（建表 + 写入函数）
- `scheduler.py`：定时调度主脚本（命令行入口）
- `routes.json`：航线配置文件
- `flights.db`：SQLite 数据库（运行时生成）

## 数据库结构（三表）

| 表 | 说明 |
|----|------|
| `crawl_runs` | 抓取批次表：每轮一行，记录起止时间、成功/失败查询数、航班总数 |
| `flights` | 航班主表：一个航班一条数据，外键 `run_id`，含价格（成人/儿童/婴儿）、舱位、行李、免机建/免燃油、折扣率、剩余票数等 |
| `segments` | 航段表：与 `flights` 一对多，中转航班有多个航段；含市场/执飞航班号、是否共享、起降城市/机场/航站楼/时间、段时长 |

价格规则与 `browser_automation` 一致：先剔除付费 `servicePackage`（price>0）档位，
再依次比较 成人价 → 儿童价 → 婴儿价 取最低档。

## 用法

所有运行参数均在配置文件中设置，命令行只保留两个参数：

```powershell
# 单轮测试
.venv\Scripts\python.exe db_storage\scheduler.py --once

# 正式运行（参数全部来自配置文件）
.venv\Scripts\python.exe db_storage\scheduler.py

# 使用其他配置文件
.venv\Scripts\python.exe db_storage\scheduler.py --config my_config.json
```

### 命令行参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--config` | routes.json | 配置文件路径 |
| `--once` | 关 | 只执行一轮后退出（测试用） |

### 配置文件（routes.json）

```json
{
  "routes": [
    {"dep": "CKG", "arr": "YTY"},
    {"dep": "PEK", "arr": "SHA"}
  ],
  "interval_minutes": 60,
  "days": 30,
  "start_offset": 0,
  "include_transfer": false,
  "include_shared": false,
  "db": "flights.db"
}
```

### 配置项

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `routes` | （必填） | 航线列表，每项 `{"dep": "...", "arr": "..."}` |
| `interval_minutes` | 60 | 两轮抓取间隔（分钟） |
| `days` | 30 | 从今天起往后抓取的天数 |
| `start_offset` | 0 | 起始日期偏移（0=今天，1=明天） |
| `include_transfer` | false | 是否包含中转航班 |
| `include_shared` | false | 是否包含共享航班 |
| `db` | flights.db | SQLite 数据库路径（相对路径基于配置文件所在目录） |

配置文件中省略任何配置项时自动使用默认值（`routes` 必填）。

## 常用查询示例

```sql
-- 某航线某日最低价走势（每轮抓取一条）
SELECT crawled_at, MIN(adult_price) FROM flights
WHERE dep='CKG' AND arr='YTY' AND flight_date='2026-09-01'
GROUP BY run_id ORDER BY crawled_at;

-- 某航班全部历史价格
SELECT crawled_at, adult_price FROM flights
WHERE itinerary_id='EU7347' AND flight_date='2026-09-01'
ORDER BY crawled_at;
```

## 已验证

- 2026-08-31 实测：`--once --days 2`，2 条航线 × 2 天，成功写入 184 条航班
  （CKG→YTY 16 条 + PEK→SHA 168 条），segments 一一对应，共享航班标记正确
- 当天日期在深夜可能查不到航班（当日航班已起飞/售罄），属正常现象
