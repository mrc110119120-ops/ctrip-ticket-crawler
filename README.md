# ctrip-ticket-crawler

携程（flights.ctrip.com）机票价格爬虫研究项目。针对同一目标（爬取 A 地到 B 地的机票价格），实现并对比了三种技术方案的可行性，最终验证了纯浏览器自动化方案。

## 项目背景与核心问题

携程机票搜索接口 `POST /international/search/api/search/batchSearch` 的响应包含机票价格，但请求受 **WhaleGuard** 反爬系统保护：

- 缺少反爬头时，**任何请求（包括访问首页 HTML 本身）都返回 HTTP 432 "whaleguard block"**
- 反爬头 `token`、`w-payload-source` 由页面 JS（overlock.js）在浏览器端动态计算

### 已逆向并验证的部分（可纯 Python 复现）

| 要素 | 结论 |
|------|------|
| `sign` 请求头 | `md5(transactionID + depCode + arrCode + depDate)`，已实测验证完全匹配 |
| `transactionID` | 客户端自生成，`uuid4().hex` 即可，同时出现在请求头和请求体中 |
| URL `v` 参数 | `Math.random()` 缓存破坏参数，服务端不校验 |
| JSON 请求体 | 固定结构，可自行构建 |

### 无法在浏览器外复现的部分（方案失败的根因）

| 要素 | 动态级别 | 说明 |
|------|---------|------|
| `token` | 会话级 | 每个浏览器会话不同，无法跨会话复用 |
| `w-payload-source` | 请求级 | 每个请求都不同，由混淆 JS 基于请求内容计算 |
| cookies（`_bfa`/`FVP` 等） | 会话级 | 全部由页面 JS 在浏览器内生成，服务端不下发 |

## 三种方案的对比结论

| 方案 | 目录 | 结果 | 根因 |
|------|------|------|------|
| 0. 纯 requests | `pure_requests/` | ❌ HTTP 432 | 缺 token / w-payload-source，页面本身也被保护，无入口可先获取 cookie |
| A. Playwright 取 token + requests 批量查询 | `playwright_token/` | ❌ HTTP 432 | token 是会话级、w-payload-source 是请求级，捕获后无法在浏览器外复现 |
| **B. 纯浏览器自动化** | **`browser_automation/`** | ✅ **成功** | 不需要在浏览器外复现任何东西，让浏览器 JS 自己完成签名 |

**最终方案：方案 B。** 实测 PEK→SHA、SHA→PEK、CKG→YTY 均成功提取航班号、起降时间、价格（如 CKG→YTY 最低 390 元）。

## 目录结构

```
ctrip-ticket-crawler/
├── README.md                   # 本文件（项目总览）
├── pyproject.toml / uv.lock    # 项目配置（uv 管理，Python 3.14）
│
├── pure_requests/              # 方案 0：纯 requests（已验证不可行）
│   ├── AGENTS.md               #   使用说明
│   ├── RESEARCH.md             #   研究报告：API 分析、签名逆向、432 根因
│   ├── ctrip_flight.py         #   核心模块：签名计算 / 请求体构建 / header 生成
│   ├── sign_verify.py          #   签名算法验证（MATCH=True）
│   ├── run_check.py            #   测试入口
│   ├── probe.py                #   WhaleGuard 432 探测
│   └── test_page_fetch.py      #   "先请求页面取参数"策略验证（不可行）
│
├── playwright_token/           # 方案 A：Playwright 取 token + requests（已验证不可行）
│   ├── AGENTS.md               #   使用说明（含不可行结论）
│   ├── RESEARCH.md             #   研究报告：token/w-payload-source 动态性分析
│   ├── get_token.py            #   Playwright 拦截 batchSearch，提取反爬头
│   ├── batch_query.py          #   requests 批量查询（实测全部 432）
│   └── token_cache.json        #   token 缓存（运行时生成）
│
├── browser_automation/         # 方案 B：纯浏览器自动化（✅ 最终可行方案）
│   ├── AGENTS.md               #   使用说明
│   ├── RESEARCH.md             #   研究报告：实现原理、关键发现、性能分析
│   ├── flight_crawler.py       #   核心爬虫（事件等待版，已实测）
│   ├── time_benchmark.py       #   性能基准测试
│   └── results.json            #   查询结果（运行时生成）
│
└── doc/                        # 原始抓包数据（人工整理）
    ├── curltest.bat            #   原始 curl 重放脚本
    ├── 请求体/ 请求头/ 响应体/ 响应头/ 网页源码/
```

各子目录的详细文档见其 `AGENTS.md`（怎么用）和 `RESEARCH.md`（研究过程与结论）。

## 快速开始（最终可行方案）

### 环境要求

```bash
# Python 3.14（uv 管理）
uv sync

# 安装 Playwright 与 Chromium
pip install playwright
playwright install chromium
```

### 作为库使用

```python
from browser_automation.flight_crawler import FlightCrawler

# 单次查询
with FlightCrawler(headless=True) as crawler:
    result = crawler.search("CKG", "YTY", "2026-09-01")
    for f in result.flights:
        print(f.flight_no, f.departure_time, f.arrival_time, f.price)

# 批量查询（共享会话，后续查询无首页开销）
with FlightCrawler(headless=True) as crawler:
    results = crawler.batch_search([
        {"dep": "CKG", "arr": "YTY", "date": "2026-09-01"},
        {"dep": "PEK", "arr": "SHA", "date": "2026-09-05"},
    ])
```

### 命令行运行

```powershell
# Windows 控制台需先设置 UTF-8 编码
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe browser_automation\flight_crawler.py      # 运行爬虫
.\.venv\Scripts\python.exe browser_automation\time_benchmark.py      # 性能基准
```

## 性能

| 指标 | 数值 |
|------|------|
| 首次查询（含浏览器启动 + 会话建立） | ~7.6 秒 |
| 后续查询（会话复用） | ~6.1 秒/次 |
| 会话建立（首页 cookie 轮询，事件驱动） | ~1.3-1.8 秒 |

## 技术要点（复用本项目经验时必读）

1. **签名算法**：`sign = md5(transactionID + depCode + arrCode + depDate)`，transactionID 用 `uuid4().hex` 自行生成
2. **必须先建立浏览器会话**：全新浏览器无 cookie 时，即使航线有航班也返回"未找到符合条件的航班"；关键 cookie `_bfa` + `FVP` 出现即可视为会话就绪
3. **绝不能用 `page.route` 拦截 batchSearch**：`route.fetch() + fulfill()` 会重新发起请求，破坏反爬参数绑定，导致返回空数据
4. **batchSearch 响应到达 ≠ DOM 渲染完成**：拿到响应立即提取会得到空数据，需短等待+重试直到 DOM 出现航班
5. **DOM 结构**：航班容器 `.flight-item.domestic`，到达栏是 `.arrive-box`（不是 `.arrival-box`），价格 `.price`
6. **Windows 编码**：控制台运行需 `$env:PYTHONIOENCODING="utf-8"`

## 使用限制与风险

- 仅供学习研究，请遵守携程网站服务条款，勿用于商业用途或大规模抓取
- 反爬策略（WhaleGuard）可能随时更新，方案可能失效
- 批量查询请保持随机延迟并控制并发（建议 ≤3），过高的请求频率会触发更严格风控
