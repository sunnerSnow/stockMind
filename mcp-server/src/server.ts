import { McpServer } from '@modelcontextprotocol/server';
import { EngineClient, type EngineApi } from './services/engineClient.js';
import { registerMarketTools } from './tools/market.js';
import { registerStockTools } from './tools/stock.js';

export const SERVER_INFO = { name: 'stockmind', version: '0.1.0' } as const;

export interface ServerDeps {
  engine?: EngineApi;
}

/** 建立並註冊好所有 Tools 的 MCP Server。依賴可注入，方便測試替換資料來源。 */
export function createServer(deps: ServerDeps = {}): McpServer {
  const server = new McpServer(SERVER_INFO, {
    instructions:
      'StockMind 提供台股研究資料。所有數值都來自工具回傳，請引用回傳的資料來源（metadata.source）與資料日期（metadata.data_date）；回傳的 warnings 要一併告知使用者。行情都是盤後資料，不是即時報價。資料不足或為 null 時請明說，不要自行補值或估算。本服務僅供查詢與分析，不提供下單，也不構成投資建議。',
  });
  const engine = deps.engine ?? new EngineClient({ baseUrl: process.env.STOCKMIND_ENGINE_URL });
  registerStockTools(server, engine);
  registerMarketTools(server, engine);
  return server;
}
