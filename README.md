# StockMind

台股研究 MCP Server：讓支援 MCP（Model Context Protocol）的 AI Client 以自然語言查詢台股資料，並取得有來源、有日期、由程式計算的研究依據。

核心原則是**程式負責數據，AI 負責解釋**：技術指標、法人買賣超等數值一律由程式計算，AI 只做解讀。

> 本專案僅供查詢與研究，不提供下單功能，內容不構成投資建議。

## 目前進度

| 里程碑 | 內容 | 狀態 |
|---|---|---|
| M1 | 最小 MCP Server、`get_stock_info` | 完成 |
| M2 | Python Financial Engine（FastAPI）、TWSE／TPEx 基本資料來源、MCP 串接 | 完成 |
| M3 | 行情、歷史行情、三大法人、大盤概況 | 未開始 |
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
| `get_stock_info` | 股票／ETF 基本資料：簡稱、公司全名、上市櫃別、證券類別、產業別代碼、上市櫃日期 | TWSE OpenAPI、TPEx OpenAPI |

成功回應的統一格式：

```json
{
  "success": true,
  "data": {
    "stock_id": "2330",
    "name": "台積電",
    "full_name": "台灣積體電路製造股份有限公司",
    "market": "TWSE",
    "security_type": "stock",
    "industry_code": "24",
    "listing_date": "1994-09-05"
  },
  "metadata": {
    "source": "TWSE OpenAPI",
    "data_date": "2026-11-17",
    "retrieved_at": "2026-11-18T12:31:45+08:00",
    "data_type": "reference",
    "unit": null
  },
  "warnings": []
}
```

錯誤時 Tool 回 `isError: true`，內容為 `{ "success": false, "error": { "code", "message" } }`：

| 錯誤碼 | 意義 |
|---|---|
| `STOCK_NOT_FOUND` | 上市、上櫃清單都查不到這個代號 |
| `UPSTREAM_ERROR` | 官方資料來源逾時或異常；不代表股票不存在 |
| `ENGINE_UNAVAILABLE` | 連不到 Financial Engine，通常是服務沒啟動 |
| `INTERNAL_ERROR` | 其他未預期的錯誤，細節只寫在 log |

參數格式錯誤由 SDK 依 schema 直接回驗證訊息，不會呼叫 Engine。

`stock_id` 必須是**字串**。代號轉成數字會丟失前導零（`0050`、`006208`），所以不接受數字型別。

### 資料說明

- 證券清單合併自「當日行情」與「公司基本資料」兩份官方資料：前者含 ETF，後者才有產業別與上市櫃日期。
- ETF 沒有公司基本資料，`full_name`、`industry_code`、`listing_date` 為 `null`。
- 代號不在公司基本資料內、也不是 `00` 開頭時，`security_type` 為 `other`，並附警告。
- 清單在記憶體快取 6 小時；`retrieved_at` 是實際向官方來源擷取的時間，不是查詢時間。
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

Engine 不在預設位址時，設定環境變數 `STOCKMIND_ENGINE_URL`（見 [.env.example](.env.example)）。

用 Inspector 的 CLI 模式快速驗證：

```bash
npx @modelcontextprotocol/inspector@latest --cli node dist/index.js --method tools/list
npx @modelcontextprotocol/inspector@latest --cli node dist/index.js   --method tools/call --tool-name get_stock_info --tool-arg stock_id=0050
```

Inspector CLI 會把純數字的參數值當成數字送出，例如 `stock_id=2330` 會被驗證擋下；請改寫成 `--tool-arg 'stock_id="2330"'`，或直接用網頁介面測試。

## 技術選型

- **MCP SDK**：`@modelcontextprotocol/server` v2（stdio 傳輸）
- **驗證**：Zod 4，輸入與輸出都有 schema
- **測試**：Vitest，搭配 `@modelcontextprotocol/client` 的 `InMemoryTransport`
- **Financial Engine**：Python 3.13、FastAPI、httpx，以 uv 管理套件；測試用 pytest 與 `httpx.MockTransport`
