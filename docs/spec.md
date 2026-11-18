# Taiwan Stock Research MCP

## AI-Powered Taiwan Stock Market Intelligence

> 專案目標：建立一套可被不同 AI Client 使用的台股研究 MCP
> Server，整合台灣上市櫃市場資料、法人籌碼、技術指標與 AI
> 研究流程。第一階段以免費、本機開發為主，先完成可運作的
> MVP，再逐步產品化。

------------------------------------------------------------------------

## 1. 專案願景

讓支援 MCP（Model Context Protocol）的 AI
成為台股研究助理。使用者以自然語言提出問題，AI 透過 MCP Tools
取得資料、呼叫金融計算服務，最後產出有資料來源、時間戳記與計算依據的研究摘要。

### 四個專案目標

1.  **求職作品集：** 展示 MCP、LLM、API
    整合、資料工程、金融資料處理、測試及部署能力。
2.  **個人使用：** 查詢台股、追蹤三大法人、計算技術指標及整理研究結果。
3.  **產品化：** 未來提供網站、其他 AI Agent 或不同 MCP Client 共用。
4.  **技術學習：** 從 MCP 基礎延伸到
    RAG、Agent、Evaluation、Guardrails、Observability 與 CI/CD。

### 核心原則

-   **程式負責數據，AI 負責解釋。**
    RSI、MACD、法人買賣超、連續買超天數等必須由程式計算，不讓 LLM
    憑空產生數字。
-   每筆市場資料都應保留來源、資料日期、擷取時間及資料狀態。
-   清楚區分即時、延遲、盤中、盤後與歷史資料，不將盤後資料描述為即時行情。
-   MVP 優先使用官方公開資料及免費工具。
-   MCP Server 與金融計算邏輯分離，避免未來只能透過 MCP 使用金融服務。

------------------------------------------------------------------------

## 2. 技術決策

### 2.1 語言分工：TypeScript + Python

採用雙語言架構：

  ---------------------------------------------------------------------------------------------------------
  層級                    技術                        職責
  ----------------------- --------------------------- -----------------------------------------------------
  MCP Layer               TypeScript / Node.js        MCP
                                                      Server、Tools、Resources、Prompts、參數驗證、Client
                                                      溝通

  Financial Engine        Python / FastAPI            金融資料處理、指標計算、法人資金流分析

  Data Processing         Pandas / NumPy              數據清理、轉換、統計

  Database（第二階段）    PostgreSQL                  歷史行情、法人資料、股票基本資料與快取結果

  Testing                 MCP                         MCP 工具測試及金融計算測試
                          Inspector、Vitest、Pytest   

  Version Control         Git / GitHub                版本管理、作品集展示

  Deployment（後續）      Docker / Docker Compose     本機整合與雲端部署
  ---------------------------------------------------------------------------------------------------------

**為什麼這樣分工：**

-   TypeScript 延續既有 JavaScript、Next.js 開發經驗，適合 MCP
    與服務整合。
-   Python 擁有成熟的資料分析與數值運算生態，適合金融資料處理。
-   兩者透過本機 HTTP + JSON 溝通，降低跨語言耦合。
-   第一版不導入 Kubernetes、訊息佇列或複雜微服務架構。

### 2.2 AI Client：免費優先

建議採取以下順序：

1.  **Claude Desktop Free：** 第一個互動式 MCP Host，使用本機 stdio
    連接本機 MCP
    Server。免費方案仍有使用量限制，實際功能依官方當期方案為準。
2.  **MCP Inspector：** 開發階段直接檢查 MCP
    Server、Tools、輸入參數與回傳結果；它是測試工具，不是完整 AI 模型。
3.  **Ollama + 自建 MCP Host：** 第二階段研究本機模型及自建
    Client。模型推論不需支付模型 API 費，但會使用本機 RAM、CPU/GPU。
4.  **ChatGPT：** 後續再測試。自訂 MCP
    連線能力、傳輸方式及方案限制需依當期官方文件確認，不列為第一階段必要條件。

> 注意：MCP 是連接協定，不等於免費模型。使用雲端 AI Client
> 仍受該服務的免費額度及使用限制約束。

### 2.3 傳輸方式

-   **本機開發：** MCP Server 使用 `stdio`，由 MCP Host 啟動本機程序。
-   **金融服務：** FastAPI 在本機提供 HTTP API，例如
    `http://127.0.0.1:8000`。
-   **未來遠端部署：** 再評估 Streamable
    HTTP、身分驗證、TLS、權限及多使用者隔離。

第一階段不要為了遠端部署而先引入不必要的複雜度。

------------------------------------------------------------------------

## 3. 系統架構

``` text
AI Client (Claude Desktop)
        |
        | MCP / stdio
        v
MCP Server (TypeScript)
  - Tools
  - Resources
  - Prompts
  - Zod validation
        |
        | HTTP / JSON
        v
Financial Engine (Python / FastAPI)
  - Stock Service
  - Market Service
  - Institutional Flow
  - Technical Indicators
  - Data Validation
        |
        v
Data Providers
  - TWSE Open Data
  - TPEx Open Data
  - Optional licensed APIs
        |
        v
Database (Phase 2)
  - PostgreSQL
```

### 架構責任界線

**MCP Server** - 定義 AI 可呼叫的工具及其輸入輸出 Schema。 -
驗證參數、呼叫 Financial Engine。 - 將錯誤轉成清楚且可理解的 Tool
回應。 - 不在此層實作複雜金融指標。

**Financial Engine** - 負責資料來源介接、清理、標準化及計算。 -
對外提供穩定、可測試的 HTTP API。 - 不依賴特定 AI Client 或 MCP SDK。

**Data Provider** - 每個來源獨立封裝。 -
統一欄位、日期、單位及代碼格式。 - 保留原始來源資訊，方便追查與替換。

------------------------------------------------------------------------

## 4. MVP 功能範圍

### 4.1 P0：第一版必做

  功能           MCP Tool                     說明
  -------------- ---------------------------- --------------------------------
  股票基本資料   `get_stock_info`             股票名稱、代號、上市櫃別等
  最新可用行情   `get_stock_price`            回傳最新可取得的行情與資料時間
  歷史行情       `get_stock_history`          指定期間 OHLCV
  三大法人       `get_institutional_flow`     外資、投信、自營商買賣超
  技術指標       `get_technical_indicators`   MA、RSI、MACD；後續加入 KD
  大盤概況       `get_market_summary`         加權指數或可取得的市場摘要
  個股綜合分析   `analyze_stock`              整合以上資料產生有依據的摘要

MVP 以 6 個資料／計算 Tools 加上 1 個整合分析 Tool
為目標。若開發時間有限，先完成基本資料、歷史行情與技術指標，再逐步加入法人資料。

### 4.2 P1：第二階段

-   `screen_stocks`：條件選股。
-   `compare_stocks`：多檔股票比較。
-   `get_institutional_ranking`：法人買賣超排行。
-   `get_stock_momentum`：價格與成交量動能。
-   `get_stock_valuation`：估值資料（須先確認可靠資料來源及定義）。

### 4.3 P2：進階功能

-   `search_stock_news`：新聞搜尋。
-   `analyze_industry`：產業分析。
-   `generate_research_report`：研究報告產生。
-   `detect_market_anomalies`：異常成交與資金流偵測。
-   `compare_institutional_trends`：不同期間法人動向比較。
-   RAG：搜尋歷史研究報告及已整理的知識文件。

------------------------------------------------------------------------

## 5. MCP Tools 設計

### 5.1 Tool 規格

#### `get_stock_info`

用途：查詢股票基本資料。

輸入：

``` json
{
  "stock_id": "2330"
}
```

輸出概念：

``` json
{
  "stock_id": "2330",
  "name": "台積電",
  "market": "TWSE",
  "data_source": "TWSE",
  "retrieved_at": "ISO-8601 timestamp"
}
```

#### `get_stock_price`

用途：取得最新可用行情。必須回傳資料日期及行情類型，不能將延遲或盤後資料標成即時。

輸入：

``` json
{
  "stock_id": "2330"
}
```

#### `get_stock_history`

用途：取得指定期間歷史行情。

輸入：

``` json
{
  "stock_id": "2330",
  "period": "1mo"
}
```

建議支援明確的起訖日期，並限制最大查詢範圍及回傳筆數。

#### `get_institutional_flow`

用途：查詢三大法人買賣超。

輸入：

``` json
{
  "stock_id": "2330",
  "start_date": "2026-10-01",
  "end_date": "2026-10-31"
}
```

應清楚定義單位、買賣超計算方式及三大法人欄位。不同來源可能有欄位差異，需在
Provider 層統一。

#### `get_technical_indicators`

用途：對歷史行情計算技術指標。

輸入：

``` json
{
  "stock_id": "2330",
  "indicators": ["MA5", "MA20", "RSI14", "MACD"],
  "period": "3mo"
}
```

回傳需包含指標定義、參數、計算日期及足夠歷史資料的檢查結果。指標數值不足時回傳明確狀態，不可填入猜測值。

#### `get_market_summary`

用途：取得市場整體概況。

輸入：

``` json
{
  "market": "TWSE"
}
```

#### `analyze_stock`

用途：整合其他 Tools 的資料，形成結構化研究摘要。此 Tool 可以由 MCP
Server 呼叫 Financial Engine，也可以由 AI Client 分別呼叫前述 Tools
後自行綜合。MVP 初期建議讓 AI Client 編排工具，避免在 Server 內重複實作
Agent。

### 5.2 回傳格式原則

所有資料類 Tools 建議包含：

``` json
{
  "success": true,
  "data": {},
  "metadata": {
    "source": "資料來源名稱",
    "data_date": "YYYY-MM-DD",
    "retrieved_at": "ISO-8601 timestamp",
    "data_type": "historical | delayed | intraday | after_market",
    "unit": "依資料欄位定義"
  },
  "warnings": []
}
```

實際 MCP Tool 的回傳格式需符合所使用 SDK
版本的規範；以上是應用層資料結構示意。

------------------------------------------------------------------------

## 6. Resources 與 Prompts 設計

### Resources

Resources 提供 AI 可讀取的背景資料，例如：

-   `stock://list`：股票清單或查詢索引。
-   `market://calendar`：交易日曆。
-   `reference://indicators`：技術指標定義。
-   `reference://data-sources`：資料來源、更新頻率與限制。
-   `reference://glossary`：法人、成交量、週轉率等名詞說明。

### Prompts

建立可重複使用的研究流程：

-   `stock_health_check`：個股健檢。
-   `institutional_flow_analysis`：三大法人籌碼分析。
-   `technical_analysis`：技術面分析。
-   `weekly_market_review`：每週市場回顧。

Prompt 應要求 AI
引用工具回傳的資料日期、來源與數值；若資料不足，明確說明不足，不可自行補值。

------------------------------------------------------------------------

## 7. 資料來源策略

### 第一優先：官方公開資料

  資料類型       優先來源       注意事項
  -------------- -------------- --------------------------------
  上市股票行情   TWSE           確認資料頻率、欄位與歷史範圍
  上櫃股票行情   TPEx           確認資料頻率、欄位與歷史範圍
  三大法人       TWSE / TPEx    確認法人分類、單位與買賣超定義
  股票基本資料   TWSE / TPEx    注意上市櫃及下市櫃狀態
  交易日資訊     官方交易日曆   避免以日曆天數推算交易日

官方入口： - TWSE OpenAPI：https://openapi.twse.com.tw/ - TPEx
OpenAPI：https://www.tpex.org.tw/openapi/

### 第三方資料源

可評估金融資料服務商作為補充或備援，但在採用前確認： -
是否需要付費或申請 API Key。 - 是否允許個人使用、再散布及商業使用。 -
即時或延遲行情的定義。 - 呼叫頻率、資料保存及快取限制。 -
資料缺漏與服務可用性。

### 資料標準化

至少統一以下欄位： - `stock_id` - `trade_date` - `open` - `high` -
`low` - `close` - `volume` - `data_source` - `retrieved_at` -
`data_type`

日期與時區統一採台灣市場日期語意；時間戳記建議使用 ISO
8601，並明確標示時區。

------------------------------------------------------------------------

## 8. 金融計算規格

### 技術指標

第一版： - MA5、MA20 - RSI14 - MACD（需明確設定 fast、slow、signal
參數）

第二版： - KD - Bollinger Bands - 成交量均線 - 報酬率與波動度

每個指標都應有單元測試，並使用已知測試資料驗證結果。文件需記錄計算公式、參數及暖機資料需求。

### 三大法人分析

第一版可計算： - 每日各法人買賣超。 - 指定期間累計買賣超。 -
連續買超／賣超天數。 - 外資、投信、自營商方向是否一致。

不得將「買賣超」直接等同於未來股價方向，也不可將不同資料來源的單位混用。

### 研究摘要規則

AI 產生摘要時，至少分開呈現： 1. **觀察到的事實：** 工具回傳的數值。 2.
**程式計算結果：** 指標、累計值、期間變化。 3. **AI 解讀：**
對數據可能意義的說明。 4. **限制與風險：**
資料延遲、缺漏、樣本期間及不確定性。

------------------------------------------------------------------------

## 9. 專案目錄

建議採用 Monorepo，讓 TypeScript 與 Python 專案放在同一個 Git
Repository：

``` text
taiwan-stock-research-mcp/
├── mcp-server/
│   ├── src/
│   │   ├── index.ts
│   │   ├── server.ts
│   │   ├── tools/
│   │   │   ├── stock.ts
│   │   │   ├── market.ts
│   │   │   ├── institutional.ts
│   │   │   └── technical.ts
│   │   ├── resources/
│   │   ├── prompts/
│   │   ├── services/
│   │   └── schemas/
│   ├── tests/
│   ├── package.json
│   └── tsconfig.json
│
├── financial-engine/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── services/
│   │   ├── indicators/
│   │   ├── data_providers/
│   │   ├── schemas/
│   │   └── core/
│   ├── tests/
│   └── requirements.txt
│
├── docs/
│   ├── architecture.md
│   ├── api-design.md
│   ├── data-sources.md
│   └── development-log.md
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

------------------------------------------------------------------------

## 10. 開發里程碑

### Milestone 1：建立最小 MCP Server

目標：讓 MCP Inspector 能看到並成功呼叫第一個 Tool。

任務： - \[ \] 建立 GitHub Repository。 - \[ \] 建立 `mcp-server`
TypeScript 專案。 - \[ \] 安裝並設定官方 MCP TypeScript SDK。 - \[ \]
建立 MCP Server。 - \[ \] 建立第一個 Tool：`get_stock_info`。 - \[ \]
加入 Zod 輸入驗證。 - \[ \] 使用 MCP Inspector 測試成功與錯誤情境。 - \[
\] 撰寫基本 README。

驗收條件： - MCP Inspector 能列出 Tool。 -
傳入正確股票代號可取得結構化結果。 - 缺少或錯誤參數時有明確錯誤訊息。 -
不依賴 AI 模型也能測試 Tool。

### Milestone 2：建立 Python Financial Engine

-   [ ] 建立 Python 虛擬環境。
-   [ ] 安裝 FastAPI、Uvicorn、Pandas、NumPy。
-   [ ] 建立健康檢查端點 `/health`。
-   [ ] 建立股票基本資料 API。
-   [ ] 建立 TWSE / TPEx Provider。
-   [ ] 加入 timeout、重試及錯誤處理。
-   [ ] 定義統一 JSON Schema。
-   [ ] 讓 TypeScript MCP Server 呼叫 Python API。

驗收條件： - Python API 可獨立啟動及測試。 -
資料來源失敗時回傳可理解的錯誤。 - MCP Tool 能取得 Python API 的結果。

### Milestone 3：行情與法人資料

-   [ ] 建立歷史行情 API。
-   [ ] 建立三大法人資料 API。
-   [ ] 統一上市櫃資料欄位。
-   [ ] 處理交易日、缺漏值及重複資料。
-   [ ] 加入資料來源與擷取時間。
-   [ ] 完成相應 MCP Tools。

### Milestone 4：技術指標

-   [ ] 實作 MA。
-   [ ] 實作 RSI。
-   [ ] 實作 MACD。
-   [ ] 建立 Pytest 單元測試。
-   [ ] 驗證不足資料量時的回傳狀態。
-   [ ] 建立 `get_technical_indicators` Tool。

### Milestone 5：AI Client 整合

-   [ ] 在 Claude Desktop 設定本機 MCP Server。
-   [ ] 測試自然語言查詢股票。
-   [ ] 測試多 Tool 串接流程。
-   [ ] 測試資料不足與來源錯誤時 AI 是否正確說明。
-   [ ] 完成個股研究摘要 Prompt。
-   [ ] 記錄可重現的測試案例。

### Milestone 6：產品化與作品集

-   [ ] 加入 PostgreSQL。
-   [ ] 建立 Dockerfile 與 Docker Compose。
-   [ ] 建立 GitHub Actions。
-   [ ] 加入結構化 Log。
-   [ ] 加入 Tool 呼叫耗時與錯誤率監控。
-   [ ] 評估遠端 MCP 傳輸與身分驗證。
-   [ ] 撰寫架構圖、Demo 及技術決策紀錄。

------------------------------------------------------------------------

## 11. 測試策略

### MCP 測試

-   Tool 是否正確註冊。
-   Tool Schema 是否正確。
-   必填欄位、錯誤格式及無效股票代號。
-   Python API timeout 或回傳錯誤時的處理。
-   Tool 回傳內容是否包含來源與資料日期。

### 金融計算測試

-   使用固定測試資料驗證 MA、RSI、MACD。
-   驗證交易日排序及重複日期。
-   驗證缺漏值處理。
-   驗證法人買賣超正負號及單位。
-   驗證不同期間累計結果。

### 整合測試

-   MCP Server → Python API。
-   Python API → Data Provider。
-   Data Provider 無法連線時的錯誤流程。
-   Claude Desktop 的實際 Tool 呼叫流程。

------------------------------------------------------------------------

## 12. 安全性與風險控制

-   不將 API Key、密碼或個人憑證提交至 Git。
-   使用 `.env` 管理本機環境變數，提供 `.env.example` 範本。
-   本機服務預設綁定 `127.0.0.1`，避免不必要的外部暴露。
-   對查詢期間、回傳筆數及輸入格式設上限。
-   對外部 API 設定 timeout、有限次數重試及速率限制。
-   記錄資料來源與擷取時間，避免混淆資料新舊。
-   未來遠端部署必須加入身分驗證、授權、TLS 及使用者隔離。
-   MCP Tools 初期只提供查詢及分析，不提供下單、交易或資金操作。
-   不把 AI 產生的分析視為保證獲利或個人化投資建議。
-   遵守資料來源的授權、使用條款及再散布限制。

------------------------------------------------------------------------

## 13. 成本控制

### MVP 免費優先策略

  項目         第一階段策略     可能成本
  ------------ ---------------- ------------------
  MCP Server   本機執行         無主機費
  Python API   本機執行         無主機費
  AI Client    Claude Free      有使用量限制
  MCP 測試     MCP Inspector    優先使用免費工具
  金融資料     官方公開資料     依來源條款使用
  版本管理     GitHub           先使用免費方案
  Database     初期可不建置     第二階段再加入
  雲端部署     MVP 完成後評估   依供應商及用量

**第一版不需要購買模型
API、不需要租用伺服器，也不需要先建立付費資料庫。**

------------------------------------------------------------------------

## 14. GitHub 作品集展示規劃

README 建議包含：

1.  專案介紹與使用情境。
2.  系統架構圖。
3.  MCP Tools / Resources / Prompts 清單。
4.  技術選型與原因。
5.  安裝及啟動方式。
6.  Claude Desktop 設定方式。
7.  MCP Inspector 測試畫面。
8.  自然語言呼叫 Demo。
9.  測試結果與已知限制。
10. 後續 Roadmap。

作品集要強調的能力： - Model Context Protocol implementation -
TypeScript / Python interoperability - Financial data engineering - REST
API integration - Data validation and numerical computation - Automated
testing - Docker and CI/CD - AI tool orchestration and guardrails

------------------------------------------------------------------------

## 15. 第一個實作任務：先讓 Tool 跑起來

不要一開始就串接所有行情資料。第一個目標是完成一個最小、可測試的 MCP
Server。

### Step 1：建立專案

``` bash
mkdir taiwan-stock-research-mcp
cd taiwan-stock-research-mcp

mkdir mcp-server
cd mcp-server

npm init -y
```

### Step 2：安裝依賴

依官方 TypeScript SDK 當期版本文件安裝套件。MCP SDK 的套件名稱及 API
可能隨版本更新，開始實作時先確認官方文件，不要混用不同主版本的範例。

### Step 3：建立第一個 Tool

先實作 `get_stock_info`，初期可以用固定測試資料確認 MCP
通訊流程；下一步再改成呼叫 Python Financial Engine 及官方資料來源。

### Step 4：使用 MCP Inspector

確認： - Server 可以啟動。 - Tool 可以被列出。 - 輸入 Schema 正確。 -
Tool 可以回傳 JSON 結果。 - 錯誤輸入有適當回應。

### Step 5：再接 Python

第一個 MCP Tool 通訊成功後，才建立
FastAPI，將固定測試資料替換成真實資料服務。

------------------------------------------------------------------------

## 16. 官方文件與參考資源

-   MCP 官方網站：https://modelcontextprotocol.io/
-   MCP TypeScript
    SDK：https://github.com/modelcontextprotocol/typescript-sdk
-   MCP Inspector：https://github.com/modelcontextprotocol/inspector
-   FastAPI：https://fastapi.tiangolo.com/
-   Pandas：https://pandas.pydata.org/docs/
-   NumPy：https://numpy.org/doc/
-   TWSE OpenAPI：https://openapi.twse.com.tw/
-   TPEx OpenAPI：https://www.tpex.org.tw/openapi/
-   Claude：https://claude.ai/download
-   Ollama：https://ollama.com/

> 開發前請再次確認官方 SDK 的穩定版本、安裝方式、Claude Desktop
> 免費方案能力，以及各資料來源的最新 API 規格與授權條款。

------------------------------------------------------------------------

## 17. 專案完成定義（MVP Definition of Done）

當以下條件全部達成，即可視為第一版 MVP 完成：

-   [ ] Claude Desktop 可連接本機 MCP Server。
-   [ ] MCP Inspector 可獨立測試所有 P0 Tools。
-   [ ] 可查詢至少一檔上市股票的基本資料及歷史行情。
-   [ ] 可取得並正確呈現三大法人資料。
-   [ ] MA、RSI、MACD 計算通過測試。
-   [ ] 每份行情與分析結果都能追溯資料來源及日期。
-   [ ] AI 能整合多個 Tools 產生研究摘要。
-   [ ] 資料缺漏、API 失敗及輸入錯誤均有明確處理。
-   [ ] README 能讓其他開發者依步驟完成本機安裝與測試。

**最終成果：一套免費優先、可本機運作、可被 AI
呼叫，並具備真實台股資料與可驗證金融計算能力的 Taiwan Stock Research
MCP。**
