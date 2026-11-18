import type { McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { envelopeSchema, marketSchema, stockIdSchema } from '../schemas/common.js';
import { StockNotFoundError, type StockInfoProvider } from '../services/stockInfo.js';
import { toolError } from './errors.js';

const stockInfoOutput = envelopeSchema(
  z.object({
    stock_id: z.string(),
    name: z.string(),
    market: marketSchema,
    security_type: z.enum(['stock', 'etf']),
  }),
);

export function registerStockTools(server: McpServer, provider: StockInfoProvider): void {
  server.registerTool(
    'get_stock_info',
    {
      title: '股票基本資料',
      description:
        '查詢台股個股或 ETF 的基本資料：名稱、代號、上市（TWSE）或上櫃（TPEx）。回傳含資料來源與擷取時間。不含行情價格。',
      inputSchema: z.object({ stock_id: stockIdSchema }),
      outputSchema: stockInfoOutput,
      annotations: { readOnlyHint: true, openWorldHint: true },
    },
    async ({ stock_id }) => {
      try {
        const result = await provider.getStockInfo(stock_id);
        const output = { success: true as const, ...result };
        return {
          content: [{ type: 'text', text: JSON.stringify(output, null, 2) }],
          structuredContent: output,
        };
      } catch (err) {
        if (err instanceof StockNotFoundError) {
          return toolError('STOCK_NOT_FOUND', `${err.message}。請確認代號是否正確，或該證券是否已下市櫃。`);
        }
        console.error('[get_stock_info] 未預期的錯誤', err);
        return toolError('INTERNAL_ERROR', '查詢股票基本資料時發生未預期的錯誤，請稍後再試。');
      }
    },
  );
}
