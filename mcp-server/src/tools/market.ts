import type { McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { marketSchema } from '../schemas/common.js';
import { marketSummaryEnvelope } from '../schemas/stock.js';
import type { EngineApi } from '../services/engineClient.js';
import { READ_ONLY, runEngineTool } from './helpers.js';

export function registerMarketTools(server: McpServer, engine: EngineApi): void {
  server.registerTool(
    'get_market_summary',
    {
      title: '大盤概況',
      description:
        '取得大盤最近一個交易日的概況：上市（TWSE）為發行量加權股價指數與市場成交量值，上櫃（TPEx）為櫃買指數。含漲跌、漲跌幅與近 10 日收盤。這是盤後資料，不是即時指數。兩個市場來源提供的欄位不同，沒有的欄位為 null。',
      inputSchema: z.object({ market: marketSchema.default('TWSE') }),
      outputSchema: marketSummaryEnvelope,
      annotations: READ_ONLY,
    },
    ({ market }) => runEngineTool('get_market_summary', () => engine.getMarketSummary(market)),
  );
}
