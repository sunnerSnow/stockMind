# StockMind

台股研究 MCP Server：讓支援 MCP（Model Context Protocol）的 AI Client 以自然語言查詢台股資料，並取得有來源、有日期、由程式計算的研究依據。

核心原則是**程式負責數據，AI 負責解釋**：技術指標、法人買賣超等數值一律由程式計算，AI 只做解讀。

> 本專案僅供查詢與研究，不提供下單功能，內容不構成投資建議。

## 目前進度

| 里程碑 | 內容 | 狀態 |
|---|---|---|
| M1 | 最小 MCP Server、`get_stock_info` | 完成 |
| M2 | Python Financial Engine（FastAPI）、TWSE／TPEx 基本資料來源、MCP 串接 | 完成 |
| M3 | 最新行情、歷史行情、三大法人、大盤概況 | 完成 |
| M4 | 技術指標 MA／RSI／MACD | 未開始 |
| M5 | Resources、Prompts、Claude Desktop 整合 | 未開始 |
| M6 | PostgreSQL、Docker、CI | 未開始 |

完整規格見 [docs/spec.md](docs/spec.md)。

## 架構

```text
AI Client（Claude Desktop 等）
        │ MCP / stdio
        ▼
mcp-server（TypeScript）      Tools、Zod 驗證、錯誤轉譯
        │ HTTP / JSON
        ▼
financial-engine（Python）    資料來源介接、清理、快取、指標計算
        │
        ▼
TWSE／TPEx 官方公開資料
```

兩層的責任分開：`mcp-server` 不做金融計算，`financial-engine` 不依賴 MCP，可以單獨當 HTTP API 使用。

## MCP Tools

| Tool | 說明 | 資料來源 |
|---|---|---|
| `get_stock_info` | 基本資料：簡稱、公司全名、上市櫃別、證券類別、產業別代碼、上市櫃日期 | TWSE／TPEx OpenAPI |
| `get_stock_price` | 最近一個交易日的盤後行情：開高低收、漲跌、漲跌幅、成交量值 | TWSE／TPEx OpenAPI |
| `get_stock_history` | 指定期間的日 K，最多 366 天 | TWSE／TPEx 盤後資訊 |
| `get_institutional_flow` | 三大法人每日買賣超，加上累計、連續天數、方向一致性，最多 31 天 | TWSE／TPEx 盤後資訊 |
| `get_market_summary` | 大盤概況：加權指數或櫃買指數、漲跌、近 10 日收盤 | TWSE／TPEx OpenAPI |

所有 Tool 都是唯讀查詢。成功回應的統一格式：

```json
{
  "success": true,
  "data": {
    "stock_id": "2330",
    "name": "台積電",
    "market": "TWSE",
    "trade_date": "2026-11-17",
    "open": 2195.0,
    "high": 2270.0,
    "low": 2155.0,
    "close": 2170.0,
    "change": -45.0,
    "previous_close": 2215.0,
    "change_percent": -2.03,
    "volume": 61610981,
    "value": 135465361736,
    "transactions": 371462
  },
  "metadata": {
    "source": "TWSE OpenAPI",
    "data_date": "2026-11-17",
    "retrieved_at": "2026-11-18T16:57:58+08:00",
    "data_type": "after_market",
    "unit": "價格：新台幣元；volume：股；value：元"
  },
  "warnings": ["這是最近一個交易日的盤後資料，不是即時行情。"]
}
```

錯誤時 Tool 回 `isError: true`，內容為 `{ "success": false, "error": { "code", "message" } }`：

| 錯誤碼 | 意義 |
|---|---|
| `STOCK_NOT_FOUND` | 上市、上櫃清單都查不到這個代號 |
| `INVALID_INPUT` | 日期範圍矛盾、超出上限或是未來的日期 |
| `UPSTREAM_ERROR` | 官方資料來源逾時、異常或格式改變；不代表查詢的對象不存在 |
| `ENGINE_UNAVAILABLE` | 連不到 Financial Engine，通常是服務沒啟動 |
| `INTERNAL_ERROR` | 其他未預期的錯誤，細節只寫在 log |

參數格式錯誤由 SDK 依 schema 直接回驗證訊息，不會呼叫 Engine。

`stock_id` 必須是**字串**。代號轉成數字會丟失前導零（`0050`、`006208`），所以不接受數字型別。

### 資料說明

**單位與時間**

- 出了 Engine 之後單位一律是：價格為新台幣元、成交量為股、成交金額為元、法人買賣超為股。上櫃歷史資料的來源單位是張與仟元，換算後精度為 1,000 股、1,000 元。
- 行情都是盤後資料（`data_type: after_market`），沒有即時或盤中報價。各來源收盤後更新的時間不同，以 `data_date` 為準。
- `retrieved_at` 是實際向官方來源擷取的時間，不是查詢時間。
- 歷史價格是未還原股價，除權息、分割前後不能直接比較。

**由程式計算的數值**

- `previous_close` = `close` - `change`；`change_percent` = `change` ÷ `previous_close` × 100，四捨五入到小數第二位。
- 三大法人的 `foreign` 含外資自營商，`dealer` 為自行買賣與避險合計。
- `cumulative_net` 是期間內有資料日子的買賣超加總。
- `streaks` 是截至最近一個有資料的交易日，同方向連續的天數；遇到持平或沒資料的日子就停止。
- `latest_alignment` 是最近一日外資、投信、自營商是否同為買超或同為賣超。

**沒有資料時**

- 沒有成交、來源未提供、或無法比較（例如除權息日的漲跌）的欄位是 `null`，不會填 0 或估計值，並在 `warnings` 說明。
- 三大法人報表只列當日有法人交易的證券。某交易日未列時，該日 `reported` 為 `false`、數值為 `null`，不計入累計與連續天數。
- 期間最後幾天的法人資料尚未公布時，那幾天不列入，並在 `warnings` 註明日期。夾在中間的交易日若來源沒有資料，該日保留為 `null`，連續天數算到這裡就停止。
- ETF 沒有公司基本資料，`full_name`、`industry_code`、`listing_date` 為 `null`。
- 來源的欄位名稱或數量與預期不符時回 `UPSTREAM_ERROR`，不會照舊的欄位位置硬解。

**快取與速度**

- 當日行情、指數在記憶體快取 5 分鐘，公司基本資料 6 小時。
- 已經結束的月份、已經過去的交易日不會再變，會另存到 `financial-engine/.cache`，重啟後仍可用。來源回「查無資料」時不存磁碟，避免暫時性的缺漏被永久記住。
- 對交易所網站的請求有節流（預設間隔 1.5 秒）。歷史行情一次抓一個月、三大法人一次抓一天，所以首次查詢較慢：一年的日 K 約 20 秒，一個月的三大法人約一分鐘；之後走快取，不到一秒。
- 其中一個市場的來源失敗時，另一個市場仍可查；但查不到的代號會回 `UPSTREAM_ERROR` 而不是 `STOCK_NOT_FOUND`。

## 本機開發

需求：Node.js 20 以上（MCP Inspector 最新版建議 22.23 以上）、Python 3.13、[uv](https://docs.astral.sh/uv/)。

### 1. 啟動 Financial Engine

```bash
cd financial-engine
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

啟動後可直接測試，API 文件在 <http://127.0.0.1:8000/docs>：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/stocks/2330
curl http://127.0.0.1:8000/stocks/2330/price
curl "http://127.0.0.1:8000/stocks/2330/history?period=3mo"
curl "http://127.0.0.1:8000/stocks/2330/institutional-flow?start_date=2026-11-02&end_date=2026-11-17"
curl http://127.0.0.1:8000/market/TWSE/summary
```

測試與檢查（不連外，以官方回應格式的樣本回放）：

```bash
uv run pytest
uv run ruff check .
```

### 2. 啟動 MCP Server

```bash
cd mcp-server
npm install
npm test          # Vitest：以記憶體內傳輸實際走一輪 MCP 呼叫
npm run typecheck
npm run build
npm run inspect   # 建置後開啟 MCP Inspector 網頁介面
```

Engine 不在預設位址時，設定環境變數 `STOCKMIND_ENGINE_URL`。所有可調整的環境變數列在 [.env.example](.env.example)。

用 Inspector 的 CLI 模式快速驗證：

```bash
npx @modelcontextprotocol/inspector@latest --cli node dist/index.js --method tools/list
npx @modelcontextprotocol/inspector@latest --cli node dist/index.js --method tools/call --tool-name get_stock_price --tool-arg stock_id=0050
```

Inspector CLI 會把純數字的參數值當成數字送出，例如 `stock_id=2330` 會被驗證擋下；請改寫成 `--tool-arg 'stock_id="2330"'`，或直接用網頁介面測試。

## 技術選型

- **MCP SDK**：`@modelcontextprotocol/server` v2（stdio 傳輸）
- **驗證**：Zod 4，輸入與輸出都有 schema
- **測試**：Vitest，搭配 `@modelcontextprotocol/client` 的 `InMemoryTransport`
- **Financial Engine**：Python 3.13、FastAPI、httpx，以 uv 管理套件；測試用 pytest 與 `httpx.MockTransport`
