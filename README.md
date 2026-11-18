# StockMind

台股研究 MCP Server：讓支援 MCP（Model Context Protocol）的 AI Client 以自然語言查詢台股資料，並取得有來源、有日期、由程式計算的研究依據。

核心原則是**程式負責數據，AI 負責解釋**：技術指標、法人買賣超等數值一律由程式計算，AI 只做解讀。

> 本專案僅供查詢與研究，不提供下單功能，內容不構成投資建議。

## 目前進度

| 里程碑 | 內容 | 狀態 |
|---|---|---|
| M1 | 最小 MCP Server、`get_stock_info`（固定測試資料） | 完成 |
| M2 | Python Financial Engine（FastAPI）、TWSE／TPEx 資料來源 | 未開始 |
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
        │ HTTP / JSON（M2 起）
        ▼
financial-engine（Python）    資料來源介接、清理、指標計算
        │
        ▼
TWSE／TPEx 官方公開資料
```

## MCP Tools

| Tool | 說明 | 資料來源 |
|---|---|---|
| `get_stock_info` | 股票／ETF 基本資料：名稱、代號、上市櫃別 | 目前為固定測試資料（2330、2317、2454、6488、0050） |

成功回應的統一格式：

```json
{
  "success": true,
  "data": { "stock_id": "2330", "name": "台積電", "market": "TWSE", "security_type": "stock" },
  "metadata": {
    "source": "fixture",
    "data_date": null,
    "retrieved_at": "2026-11-18T11:21:41+08:00",
    "data_type": "reference",
    "unit": null
  },
  "warnings": ["…"]
}
```

錯誤時 Tool 回 `isError: true`，內容為 `{ "success": false, "error": { "code", "message" } }`；參數格式錯誤則由 SDK 依 schema 直接回驗證訊息。

`stock_id` 必須是**字串**。代號轉成數字會丟失前導零（`0050`、`006208`），所以不接受數字型別。

## 本機開發

需求：Node.js 20 以上（MCP Inspector 最新版建議 22.23 以上）。

```bash
cd mcp-server
npm install
npm test          # Vitest：以記憶體內傳輸實際走一輪 MCP 呼叫
npm run typecheck
npm run build
npm run inspect   # 建置後開啟 MCP Inspector 網頁介面
```

用 Inspector 的 CLI 模式快速驗證：

```bash
npx @modelcontextprotocol/inspector@latest --cli node dist/index.js --method tools/list
npx @modelcontextprotocol/inspector@latest --cli node dist/index.js \
  --method tools/call --tool-name get_stock_info --tool-arg stock_id=0050
```

Inspector CLI 會把純數字的參數值當成數字送出，例如 `stock_id=2330` 會被驗證擋下；請改寫成 `--tool-arg 'stock_id="2330"'`，或直接用網頁介面測試。

## 技術選型

- **MCP SDK**：`@modelcontextprotocol/server` v2（stdio 傳輸）
- **驗證**：Zod 4，輸入與輸出都有 schema
- **測試**：Vitest，搭配 `@modelcontextprotocol/client` 的 `InMemoryTransport`
- **金融計算（M2 起）**：Python、FastAPI、Pandas，以 uv 管理套件
