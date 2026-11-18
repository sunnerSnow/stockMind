import { z } from 'zod';
import { envelopeSchema, marketSchema } from '../schemas/common.js';

export const stockInfoSchema = z.object({
  stock_id: z.string(),
  name: z.string().describe('證券簡稱'),
  full_name: z.string().nullable().describe('公司全名；ETF 等無公司資料者為 null'),
  market: marketSchema,
  security_type: z.enum(['stock', 'etf', 'other']).describe('other 表示來源資料不足以判定類別'),
  industry_code: z.string().nullable().describe('交易所產業別代碼'),
  listing_date: z.string().nullable().describe('上市／上櫃日期 YYYY-MM-DD'),
});

export const stockInfoEnvelopeSchema = envelopeSchema(stockInfoSchema);

export type StockInfoResult = z.infer<typeof stockInfoEnvelopeSchema>;

/** 股票基本資料來源。正式實作是 Financial Engine；測試可注入替身。 */
export interface StockInfoProvider {
  getStockInfo(stockId: string): Promise<StockInfoResult>;
}
