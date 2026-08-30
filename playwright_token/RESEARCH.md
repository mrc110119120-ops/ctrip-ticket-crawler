# Playwright 获取 token + requests 批量查询 — 研究报告

## 1. 方案概述

**目标**：结合 Playwright 和 requests 的优势，实现高效爬取携程机票价格。

**核心思路**：
1. 用 Playwright 打开页面，让浏览器正常执行 JS 计算 token
2. 通过路由拦截捕获 `batchSearch` 请求的 token、w-payload-source、cookies
3. 在 token 有效期内，用 requests 携带这些参数批量发起查询

**预期优势**：
- 比纯浏览器自动化快（token 有效期内可发多个请求）
- token 复用减少浏览器启动次数

---

## 2. 实验方法

### 2.1 Token 捕获（get_token.py）

```python
# 核心流程
1. 启动 Playwright Chromium 浏览器
2. 注册路由拦截器：page.route('**/batchSearch**', handler)
3. 导航到搜索页：page.goto(search_url)
4. 等待 batchSearch 请求自动触发
5. 从拦截的请求中提取：
   - token（WhGuard 反爬 token）
   - w-payload-source（反爬载荷）
   - transactionid
   - sign
   - cookies（通过 context.cookies() 获取）
6. 保存到 token_cache.json
```

### 2.2 批量查询（batch_query.py）

```python
# 核心流程
1. 从 token_cache.json 加载捕获的 token 数据
2. 构建 requests Session，设置 cookies 和基础 headers
3. 对每个查询：
   - 生成新的 transactionID（uuid4 hex）
   - 计算 sign（md5）
   - 构建请求体和 headers（携带捕获的 token）
   - 发送 POST 请求
   - 解析响应
4. 查询间加入随机延时（1-3 秒）避免触发风控
```

### 2.3 测试环境

- **搜索页面**：`https://flights.ctrip.com/online/list/oneway-ckg-yty?depdate=2026-09-01`
- **目标 API**：`POST https://flights.ctrip.com/international/search/api/search/batchSearch`
- **测试查询**：CKG → YTY（3 个不同日期）

---

## 3. 实验结果

### 3.1 Token 捕获 ✅ 成功

```
Token            : 1001-common-UHoWDAxomJ4aY30r4cE98w6cyXsEOhjsUj4XEk...
W-Payload-Source : 1.0.9@102!GVOzFEhL9XWb9XtpOSjaGS9HOrt/O6KLG6qLGSKn...
TransactionID    : de6f2d5a04204ddba54e03f545358e66
Sign             : 52f37b566c6bdf90cef078490ad7902
Cookies count    : 5（FVP, UBT_VID, FlightIntl, GUID, _bfa）
```

**结论**：Playwright 路由拦截可以完整捕获浏览器生成的反爬参数。

### 3.2 批量查询 ❌ 全部失败（HTTP 432）

```
❌ CKG -> YTY (2026-09-01): HTTP 432 - WhaleGuard block
❌ CKG -> YTY (2026-09-05): HTTP 432 - WhaleGuard block
❌ CKG -> YTY (2026-09-10): HTTP 432 - WhaleGuard block
```

---

## 4. 根因分析

### 4.1 关键发现：两次独立会话完整对比

通过两次**完全独立的浏览器会话**（清除 cookie、新建 context）捕获所有参数进行对比：

#### 请求头对比

| 参数 | 会话 1（前 40 字符） | 会话 2（前 40 字符） | 是否相同 |
|------|---------------------|---------------------|---------|
| `token` | `1001-common-qMdwnoRbqvz3R0kIfLv5...` | `1001-common-Hq7Eh9y3aWqmj9HyhFw...` | ❌ 不同 |
| `w-payload-source` | `1.0.9@102!9P9am2NaOCAbGrqLKPtI...` | `1.0.9@102!OajXOXNG9atb9rCd9ETZ...` | ❌ 不同 |
| `transactionid` | `f868df4b60dc46b5bf61285c599716c8` | `8ce7c54929ba404c818209f5b62151bd` | ❌ 不同 |
| `sign` | `4b036bbc31bfd49da78fef663ff078a3` | `c97d75e14bfe41cd29234c82a07bff2b` | ❌ 不同 |
| `scope` | `d` | `d` | ✅ 相同 |
| `cookieorigin` | `https://flights.ctrip.com` | `https://flights.ctrip.com` | ✅ 相同 |

#### Cookie 对比

| Cookie | 会话 1（前 30 字符） | 会话 2（前 30 字符） | 是否相同 |
|--------|---------------------|---------------------|---------|
| `UBT_VID` | `1787997657183.29d88gtHdhx3` | `1788047679464.3802lRGqZ9Cn` | ❌ 不同 |
| `FVP` | `g3eHwTLE8tBmrSNBAxNszP5ItTy9...` | `aEih%2FWqCstxIw%2BG2%2BeNw3QUr` | ❌ 不同 |
| `GUID` | _(不存在)_ | `09031025415754755048` | ❌ 不同 |
| `_bfa` | `1.1787997657183.29d88gtHdhx3...` | `1.1788047679464.3802lRGqZ9Cn...` | ❌ 不同 |
| `_RGUID` | `58e7c968-691d-4317-81e5-075b02...` | `66e04c50-53cc-432e-8b3c-01f51c...` | ❌ 不同 |
| `suid` | `U0A1M/ER/KOsqvSOuYvzog==` | `MQhP//ERBKR/mm6VF1WOAg==` | ❌ 不同 |
| `FlightIntl` | `Search=[%22CKG|%E9%87%8D%E5%BA...` | `Search=[%22CKG|%E9%87%8D%E5%BA...` | ✅ 相同（搜索参数） |

### 4.2 参数动态性分类

| 类别 | 参数 | 变化规律 |
|------|------|---------|
| **静态（固定）** | `scope`, `cookieorigin` | 永远不变 |
| **会话级（每会话变）** | `token`, `UBT_VID`, `FVP`, `GUID`, `_bfa`, `_RGUID`, `suid` | 每次新建浏览器会话变化 |
| **请求级（每请求变）** | `w-payload-source`, `transactionid`, `sign` | 每次请求都变化 |
| **业务数据** | `FlightIntl` | 取决于搜索参数 |

### 4.3 `w-payload-source` 的特性

| 特性 | 说明 |
|------|------|
| 格式 | `1.0.9@102!<base64-like-data>` |
| 生成方 | WhaleGuard SDK（overlock.js）在浏览器端计算 |
| 变化规律 | 每个请求都不同（即使参数完全相同） |
| 绑定关系 | 可能绑定请求体、头、时间戳等 |
| 能否复用 | ❌ 不能 |

### 4.4 `token` 的特性

| 特性 | 说明 |
|------|------|
| 格式 | `1001-common-<base64-encoded-data>` |
| 生成方 | WhaleGuard SDK 计算 |
| 变化规律 | 每次会话变化（同一会话内可能复用） |
| 有效期 | 较短（约几分钟） |
| 能否跨会话复用 | ❌ 不能 |

### 4.5 为什么方案 A 失效

```
预期流程：
  捕获 token + cookies → 复用发 N 个请求 → 得到 N 个结果

实际流程：
  捕获 token + cookies → 但 token 是会话级的，新请求没有浏览器环境
  → WhaleGuard 检测到 token 无效 → 全部 432

双重障碍：
  1. token 是会话级的，不能跨会话复用
  2. w-payload-source 是请求级的，每个请求都需要新的
  纯 requests 无法生成有效的 token 和 w-payload-source
```

---

## 5. 各参数可复用性分析（更新）

| 参数 | 可复用？ | 复用粒度 | 说明 |
|------|---------|---------|------|
| `scope` | ✅ 永远不变 | 永久 | 固定值 "d" |
| `cookieorigin` | ✅ 永远不变 | 永久 | 固定值 |
| `token` | ⚠️ 会话内 | 单次浏览器会话 | 每次新建浏览器变化 |
| `cookies` | ⚠️ 会话内 | 单次浏览器会话 | 部分 cookie 每次会话变化 |
| `transactionID` | ❌ 每次新生成 | 单次请求 | 由客户端生成 |
| `sign` | ❌ 每次计算 | 单次请求 | 基于 transactionID 计算 |
| `w-payload-source` | ❌ 不可复用 | 单次请求 | 请求级动态签名 |

**结论：没有任何参数可以在"浏览器外"长期复用。**

---

## 6. 结论

### 6.1 方案 A 评估

| 指标 | 评分 | 说明 |
|------|------|------|
| 可行性 | ❌ 不可行 | w-payload-source 无法复用 |
| 速度 | N/A | 无法实现批量查询 |
| 稳定性 | N/A | 无法通过 WhaleGuard 校验 |

### 6.2 核心结论

**`w-payload-source` 是方案 A 的致命障碍。**

- `token` 可以通过浏览器捕获 ✅
- `w-payload-source` 不能复用 ❌
- 纯 requests 无法生成有效的 `w-payload-source` ❌

### 6.3 后续方案建议

| 方案 | 描述 | 可行性 | 速度 |
|------|------|--------|------|
| **B：纯浏览器自动化** | 每个查询都用 Playwright | ✅ 高 | 慢 |
| **C：逆向 w-payload-source** | 分析 overlock.js 算法 | 🔬 可能但困难 | 快 |
| **D：每次查询重新获取 token** | 每个查询启动浏览器 | ✅ 高 | 很慢 |

**推荐方案 B（纯浏览器自动化）**，虽然速度较慢但最稳定可靠。

---

## 7. 项目文件

```
playwright_token/
├── get_token.py       # Token 捕获脚本（Playwright）
├── batch_query.py     # 批量查询脚本（requests）
├── AGENTS.md          # 使用说明
└── RESEARCH.md        # 本文件（研究报告）
```

---

## 8. 参考资料

- `pure_requests/RESEARCH.md` — 纯 requests 逆向研究报告
- `doc/` — 原始抓取数据（curl、请求头、响应等）
- `overlock.js` — WhaleGuard SDK（混淆 JS，托管在 tripcdn.cn）
