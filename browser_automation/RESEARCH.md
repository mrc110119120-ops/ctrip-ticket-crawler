# browser_automation 研究报告 — 方案 B：纯浏览器自动化（最终可行方案）

> ✅ **研究结论：方案 B 是三个方案中唯一验证可行的爬取方案。**
> 研究日期：2026-08-30，事件等待版已实测（首次查询 ~7.6 秒，后续查询 ~6.1 秒）

## 1. 研究目标

在纯 requests（见 `../pure_requests/RESEARCH.md`）和方案 A（Playwright 取 token + requests，见 `../playwright_token/RESEARCH.md`）相继失败后，验证最后一个方案：**每个查询都用 Playwright 驱动真实浏览器完成，从渲染后的 DOM 中提取机票价格**。

## 2. 实现原理

```
1. 启动 Chromium（headless）
2. 首次查询前访问首页 https://flights.ctrip.com/，
   轮询等待关键 cookie（_bfa、FVP）生成（实测 ~1.3 秒就绪）
3. page.expect_response() 监听 batchSearch 响应，同时导航到搜索页
   .../oneway-{dep}-{arr}?depdate={date}&cabin=y_s&adult=1
4. 浏览器内部自动执行 JS 发起 batchSearch（由 WhaleGuard JS 正常签名，无需干预）
5. 响应到达后，"短等待 + 重试"直到 DOM 渲染出航班数据（响应 ≠ 渲染完成）
6. page.evaluate() 从 DOM 一次性提取航班号 / 时间 / 机场 / 价格
7. 会话建立后，后续查询跳过首页步骤，复用同一浏览器 context
```

关键点：**完全放弃在浏览器外复现请求**，让浏览器自己完成一切（包括 token、w-payload-source 的生成），我们只读渲染结果。

## 3. 研究过程中的关键发现

以下发现均已固化进 `flight_crawler.py` 实现：

| # | 发现 | 固化为 |
|---|------|--------|
| 1 | 全新浏览器无 cookie 时，携程返回"未找到符合条件的航班"（即使航线有航班）。首页 JS 会生成 `UBT_VID`/`_bfa`/`FVP`/`GUID`/`_RGUID` 等会话 cookie，其中 `_bfa`+`FVP` 出现即可视为会话就绪 | `_ensure_session()` + `SESSION_KEY_COOKIES` 轮询 |
| 2 | `page.route` + `route.fetch()` + `route.fulfill()` 会重新发起请求，破坏反爬参数绑定，导致返回空数据。**绝不能拦截 batchSearch 本身** | 不使用 route 拦截 |
| 3 | batchSearch 响应到达 ≠ DOM 渲染完成，立即 evaluate 会取到空数据 | 提取时"短等待+重试"（300ms→500ms→...→2000ms） |
| 4 | DOM 实际类名：航班容器 `.flight-item.domestic`、航司 `.flight-airline`、出发 `.depart-box`、到达 `.arrive-box`（不是 `arrival`）、价格 `.price` | `EXTRACT_FLIGHTS_JS` |
| 5 | `page.evaluate(JS)` 一次性提取比 Python 侧 `query_selector_all` 更可靠 | `EXTRACT_FLIGHTS_JS` |
| 6 | Windows 控制台默认 GBK，打印 emoji/¥ 会 UnicodeEncodeError | 运行时设 `PYTHONIOENCODING=utf-8` |

## 4. 性能实测（2026-08-30，`time_benchmark.py`）

| 指标 | 数值 |
|------|------|
| 首次查询（含浏览器启动 + 会话建立） | **7.57 秒** |
| 后续查询（会话复用，无首页开销） | **6.09 秒/次** |
| 会话建立（首页 cookie 轮询） | ~1.3 秒 |
| 搜索页导航 + batchSearch 响应 | ~4-5 秒 |
| DOM 渲染 + 提取 | ~1.1 秒 |

数据质量与完整版一致：PEK→SHA 与 SHA→PEK 各 7 个航班（含航班号、时间、价格）。

### 进一步优化方向（未实施）

| 优化 | 预期收益 | 说明 |
|------|---------|------|
| 并行多个 context | 吞吐 ×N | 一个浏览器开多个 context 并行查询，需控制并发数（建议 ≤3）避免触发风控 |
| 阻止无关资源加载 | ~1-2 秒/次 | 拦截图片/字体/统计脚本（仍不能拦截 batchSearch） |

## 5. 最终结论

### 5.1 三方案对比总表

| 方案 | 结果 | 根因 |
|------|------|------|
| 纯 requests（`../pure_requests/`） | ❌ HTTP 432 | 缺 token / w-payload-source，页面本身也被保护 |
| Playwright 取 token + requests（`../playwright_token/`） | ❌ 432 | token 是会话级、w-payload-source 是请求级，无法在浏览器外复现 |
| **纯浏览器自动化（本方案）** | ✅ **成功** | 不需要在浏览器外复现任何东西 |

### 5.2 方案 B 的优缺点

**优点：**
- 完全模拟真实用户，天然通过 WhaleGuard 校验（JS 自己算签名）
- 不需要逆向任何混淆 JS
- 数据来自渲染后的 DOM，可靠性高
- 事件等待版单次查询仅 ~6-8 秒，会话复用下批量查询效率可接受

**缺点：**
- 相比 HTTP 直连仍慢（每次 ~6 秒）
- 资源消耗大（需运行 Chromium）
- 不适合大规模并发（会触发更严格风控）

### 5.3 后续建议

1. **中期**：一个浏览器 + 多 context 并行（并发 ≤3），提升批量吞吐
2. **长期**（如需大规模爬取）：考虑逆向 WhaleGuard 的 w-payload-source 算法（方案 C），但携程会定期更新混淆，维护成本高

## 6. 相关文件

| 文件 | 说明 |
|------|------|
| `flight_crawler.py` | 核心爬虫（事件等待版，已实测） |
| `time_benchmark.py` | 性能基准测试脚本（第 4 节数据来源） |
| `results.json` | 成功爬取的航班数据（运行时生成） |
| `AGENTS.md` | 使用说明（程序文档，研究内容见本文件） |
| `../pure_requests/RESEARCH.md` | 纯 requests 方案研究 |
| `../playwright_token/RESEARCH.md` | 方案 A 研究及参数动态性分析 |
