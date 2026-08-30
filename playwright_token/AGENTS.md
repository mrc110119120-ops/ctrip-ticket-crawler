# playwright_token — Playwright 获取 token + requests 批量查询

> ⚠️ **研究结论：方案 A 不可行**
>
> 本文件夹中的代码用于验证"Playwright 获取 token → requests 批量查询"的方案。
> 研究发现 `token` 是会话级的，`w-payload-source` 是请求级的，无法在浏览器外复用。
> **实际可行的方案是纯浏览器自动化（Plan B）。**

## 工作原理

```
步骤 1: Playwright 打开搜索页
  浏览器加载页面 → JS 执行 → 计算 token → 自动发起 batchSearch 请求

步骤 2: 路由拦截捕获请求头
  拦截 batchSearch → 提取 token, w-payload-source → 提取 cookies → 保存到 token_cache.json

步骤 3: 尝试用 requests 批量查询 → ❌ 全部 432
  token 是会话级的 → 跨会话复用失败
  w-payload-source 是请求级的 → 无法复用
```

## 文件结构

```
playwright_token/
├── __init__.py            # 包初始化
├── get_token.py           # 获取 token（Playwright 浏览器）
├── batch_query.py         # 批量查询（纯 requests）- 预期失败
├── token_cache.json       # token 缓存文件（运行时生成）
├── AGENTS.md              # 本文件
└── RESEARCH.md            # 详细研究报告
```

## 文件说明

### get_token.py

使用 Playwright 打开携程搜索页，拦截 `batchSearch` 请求，提取反爬参数。

**核心类/函数：**
- `TokenData` — 数据类，包含 token、w_payload_source、transaction_id、sign、cookies
- `capture_token(search_url, headless, timeout_ms)` — 执行捕获，返回 TokenData

**运行方式：**
```bash
python playwright_token/get_token.py
```

**输出：**
- 控制台显示捕获结果
- 保存 `token_cache.json`
- ⚠️ 提示 token 无法跨会话复用

### batch_query.py

⚠️ **预期失败的演示脚本**：使用捕获的 token 通过纯 requests 批量查询。

**核心类/函数：**
- `FlightQueryClient` — 查询客户端
  - `query(dep, arr, dep_date, adult, cabin)` — 单次查询
  - `batch_query(queries)` — 批量查询（带限速）
- `load_token_cache()` — 从 token_cache.json 加载 token

**运行方式：**
```bash
# 先获取 token
python playwright_token/get_token.py

# 再执行批量查询（预期全部 432）
python playwright_token/batch_query.py
```

**预期结果：**
- 所有查询返回 HTTP 432（WhaleGuard block）
- 原因：token 是会话级的，无法在浏览器外复用

## 研究结论

| 参数 | 变化级别 | 可复用？ |
|------|---------|---------|
| `token` | 会话级（每次新建浏览器变化） | ❌ |
| `w-payload-source` | 请求级（每次请求变化） | ❌ |
| `transactionid` | 请求级 | ❌ |
| `sign` | 请求级 | ❌ |
| `cookies` | 会话级 | ❌ |
| `scope`, `cookieorigin` | 静态 | ✅ |

**结论：没有任何反爬参数可以在浏览器外复用，必须使用纯浏览器自动化（Plan B）。**

## 与 pure_requests/ 的关系

| 方面 | pure_requests/ | playwright_token/ |
|------|---------------|-------------------|
| 获取 token | ❌ 无法获取 | ✅ Playwright 浏览器 |
| 批量查询 | ❌ 被 432 拦截 | ❌ 也被 432 拦截 |
| 结论 | 不可行 | 不可行 |

两个方案都验证了：**纯 requests 无法爬取携程机票价格，必须使用浏览器自动化。**

## 运行要求

```bash
# 安装 playwright（如果尚未安装）
pip install playwright
playwright install chromium
```

## 扩展使用

### 自定义查询

修改 `batch_query.py` 中的 `queries` 列表：

```python
queries = [
    {"dep": "CKG", "arr": "YTY", "dep_date": "2026-09-01"},
    {"dep": "SHA", "arr": "PEK", "dep_date": "2026-09-05"},
    # 添加更多...
]
```

### 在其他脚本中使用

```python
from playwright_token.batch_query import FlightQueryClient, load_token_cache

token_data = load_token_cache()
client = FlightQueryClient(token_data)
result = client.query("CKG", "YTY", "2026-09-01")
print(result)
```