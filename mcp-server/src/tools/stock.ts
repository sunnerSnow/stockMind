import type { McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { isoDateSchema, stockIdSchema } from '../schemas/common.js';
import {
  institutionalFlowEnvelope,
  stockHistoryEnvelope,
  stockInfoEnvelope,
  stockPriceEnvelope,
} from '../schemas/stock.js';
import type { EngineApi } from '../services/engineClient.js';
import { READ_ONLY, runEngineTool } from './helpers.js';

export function registerStockTools(server: McpServer, engine: EngineApi): void {
  server.registerTool(
    'get_stock_info',
    {
      title: '股票基本資料',
      description:
        '查詢台股個股或 ETF 的基本資料：簡稱、公司全名、上市（TWSE）或上櫃（TPEx）、證券類別、產業別代碼、上市櫃日期。資料來自 TWSE／TPEx 官方公開資料。不含行情價格。',
      inputSchema: z.object({ stock_id: stockIdSchema }),
      outputSchema: stockInfoEnvelope,
      annotations: READ_ONLY,
    },
    ({ stock_id }) => runEngineTool('get_stock_info', () => engine.getStockInfo(stock_id)),
  );

  server.registerTool(
    'get_stock_price',
    {
      title: '最新可用行情',
      description:
        '取得個股或 ETF 最近一個交易日的盤後行情：開高低收、漲跌、漲跌幅、成交量。這是盤後資料，不是即時報價；盤中查詢拿到的是前一個交易日的資料，請以回傳的 trade_date 為準並向使用者說明。',
      inputSchema: z.object({ stock_id: stockIdSchema }),
      outputSchema: stockPriceEnvelope,
      annotations: READ_ONLY,
    },
    ({ stock_id }) => runEngineTool('get_stock_price', () => engine.getStockPrice(stock_id)),
  );

  server.registerTool(
    'get_stock_history',
    {
      title: '歷史行情',
      description:
        '取得個股或 ETF 指定期間的日 K（開高低收、成交量、成交金額）。用 period 或 start_date／end_date 擇一指定範圍，都不給時為最近一個月；範圍最多 366 天。價格為未還原股價。首次查詢較長的期間需要逐月向交易所取資料，可能要數十秒。',
      inputSchema: z.object({
        stock_id: stockIdSchema,
        period: z.enum(['5d', '1mo', '3mo', '6mo', '1y']).optional().describe('從今天往回的期間；與起訖日期擇一'),
        start_date: isoDateSchema.optional().describe('起始日 YYYY-MM-DD'),
        end_date: isoDateSchema.optional().describe('結束日 YYYY-MM-DD，預設今天；需搭配 start_date'),
      }),
      outputSchema: stockHistoryEnvelope,
      annotations: READ_ONLY,
    },
    ({ stock_id, ...query }) => runEngineTool('get_stock_history', () => engine.getStockHistory(stock_id, query)),
  );

  server.registerTool(
    'get_institutional_flow',
    {
      title: '三大法人買賣超',
      description:
        '查詢個股或 ETF 的三大法人（外資、投信、自營商）每日買賣超，單位為股。回傳每日明細，以及由程式算好的期間累計、連續買超／賣超天數、最近一日三者方向是否一致，請直接引用這些數值，不要自行加總。不給日期時為最近 14 天；範圍最多 31 天。首次查詢要逐日向交易所取資料，一個月約需一分鐘。',
      inputSchema: z.object({
        stock_id: stockIdSchema,
        start_date: isoDateSchema.optional().describe('起始日 YYYY-MM-DD'),
        end_date: isoDateSchema.optional().describe('結束日 YYYY-MM-DD，預設今天；需搭配 start_date'),
      }),
      outputSchema: institutionalFlowEnvelope,
      annotations: READ_ONLY,
    },
    ({ stock_id, ...query }) =>
      runEngineTool('get_institutional_flow', () => engine.getInstitutionalFlow(stock_id, query)),
  );
}
