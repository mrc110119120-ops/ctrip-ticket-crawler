# browser_automation — 纯浏览器自动化爬取携程机票价格（方案 B）

> ✅ **方案 B 验证成功**（2026-08-30）：成功爬取 PEK→SHA、SHA→PEK 的机票价格。
> 采用事件等待，首次查询 ~7.6 秒、后续查询 ~6.1 秒/次。
> 研究过程与结论见 [RESEARCH.md](./RESEARCH.md)。本文件只讲"怎么用"。

## 文件结构

```
browser_automation/
├── __init__.py            # 包初始化
├── flight_crawler.py      # 核心爬虫模块（事件等待版，已验证）
├── time_benchmark.py      # 性能基准测试
├── results.json           # 查询结果（运行时生成）
├── AGENTS.md              # 本文件（使用说明）
└── RESEARCH.md            # 研究报告（研究过程与结论）
```

## 文件说明

### flight_crawler.py

核心爬虫模块，使用纯 Playwright 浏览器自动化 + 事件等待。

**核心类：**
- `FlightInfo` — 航班信息数据类（航班号、时间、机场、价格）
- `SearchResult` — 搜索结果数据类
- `FlightCrawler` — 爬虫主类

**核心方法：**
- `start()` / `stop()` — 启动/关闭浏览器
- `search(dep, arr, date, cabin)` — 单次搜索（首次自动建立会话）
- `batch_search(queries, delay_range)` — 批量搜索（带随机延迟）
- `_ensure_session(timeout_ms)` — 会话建立（轮询 `_bfa`/`FVP` cookie，仅首次执行）

**工作流程（每次查询）：**
1. `_ensure_session()` 确保会话 cookie 就绪（仅首次，~1.3 秒）
2. `page.expect_response()` 监听 batchSearch 响应，同时导航到搜索页
3. 响应到达后短等待+重试，直到 DOM 渲染出航班
4. `page.evaluate(EXTRACT_FLIGHTS_JS)` 一次性提取数据

**使用方式：**
```python
# 上下文管理器（推荐）
with FlightCrawler(headless=True) as crawler:
    result = crawler.search("PEK", "SHA", "2026-09-01")
    print(result.flights)

# 批量查询（共享会话，后续查询无首页开销）
with FlightCrawler(headless=True) as crawler:
    results = crawler.batch_search([
        {"dep": "PEK", "arr": "SHA", "date": "2026-09-01"},
        {"dep": "SHA", "arr": "PEK", "date": "2026-09-05"},
    ])
```

### time_benchmark.py

测量当前实现的性能：首次查询（含会话建立）与后续查询（会话复用）的耗时。
运行方式同下。最新测量结果见 RESEARCH.md 第 4 节。

## 使用注意事项（必须遵守，否则查不到数据）

1. **必须先建立会话**：模块已内置（首次查询前自动访问首页并轮询关键 cookie）。
2. **不要用 page.route 拦截 batchSearch**：`route.fetch() + fulfill()` 会重新发起请求，破坏反爬参数绑定，导致返回空数据。
3. **Windows 控制台运行需设置编码**：
   ```powershell
   $env:PYTHONIOENCODING="utf-8"
   python browser_automation/flight_crawler.py
   ```

## 运行要求

```bash
pip install playwright
playwright install chromium
```

## 性能速览

实测：首次查询 ~7.6 秒（含会话建立），后续查询 ~6.1 秒/次（会话复用）。
详细分析见 [RESEARCH.md](./RESEARCH.md) 第 4 节。

