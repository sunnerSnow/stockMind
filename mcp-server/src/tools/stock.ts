import type { McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { stockIdSchema } from '../schemas/common.js';
import { EngineError } from '../services/engineClient.js';
import { stockInfoEnvelopeSchema, type StockInfoProvider } from '../services/stockInfo.js';
import { toolError } from './errors.js';

const HINTS: Partial<Record<EngineError['code'], string>> = {
  STOCK_NOT_FOUND: '請確認代號是否正確，或該證券是否已下市櫃。',
  UPSTREAM_ERROR: '這是資料來源的暫時性問題，不代表該股票不存在。',
};

export function registerStockTools(server: McpServer, provider: StockInfoProvider): void {
  server.registerTool(
    'get_stock_info',
    {
      title: '股票基本資料',
      description:
        '查詢台股個股或 ETF 的基本資料：簡稱、公司全名、上市（TWSE）或上櫃（TPEx）、證券類別、產業別代碼、上市櫃日期。資料來自 TWSE／TPEx 官方公開資料，回傳含來源、資料日期與擷取時間。不含行情價格。',
      inputSchema: z.object({ stock_id: stockIdSchema }),
      outputSchema: stockInfoEnvelopeSchema,
      annotations: { readOnlyHint: true, openWorldHint: true },
    },
    async ({ stock_id }) => {
      try {
        const output = await provider.getStockInfo(stock_id);
        return {
          content: [{ type: 'text', text: JSON.stringify(output, null, 2) }],
          structuredContent: output,
        };
      } catch (err) {
        if (err instanceof EngineError) {
          const hint = HINTS[err.code];
          return toolError(err.code, hint ? `${err.message}。${hint}` : err.message);
        }
        console.error('[get_stock_info] 未預期的錯誤', err);
        return toolError('INTERNAL_ERROR', '查詢股票基本資料時發生未預期的錯誤，請稍後再試。');
      }
    },
  );
}
