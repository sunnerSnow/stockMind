import { McpServer } from '@modelcontextprotocol/server';
import { FixtureStockInfoProvider, type StockInfoProvider } from './services/stockInfo.js';
import { registerStockTools } from './tools/stock.js';

export const SERVER_INFO = { name: 'stockmind', version: '0.1.0' } as const;

export interface ServerDeps {
  stockInfo?: StockInfoProvider;
}

/** 建立並註冊好所有 Tools 的 MCP Server。依賴可注入，方便測試替換資料來源。 */
export function createServer(deps: ServerDeps = {}): McpServer {
  const server = new McpServer(SERVER_INFO, {
    instructions:
      'StockMind 提供台股研究資料。所有數值都來自工具回傳，請引用回傳的資料來源與日期；資料不足時請明說，不要自行補值。本服務僅供查詢與分析，不提供下單，也不構成投資建議。',
  });
  registerStockTools(server, deps.stockInfo ?? new FixtureStockInfoProvider());
  return server;
}
