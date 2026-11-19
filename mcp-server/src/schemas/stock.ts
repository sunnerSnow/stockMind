import { z } from 'zod';
import { envelopeSchema, marketSchema } from './common.js';

/**
 * Financial Engine 各端點回應的 schema。同時用來驗證 Engine 的回應，
 * 以及作為 MCP Tool 的 outputSchema。欄位定義以 Engine 的 Pydantic 模型為準。
 */

const isoDate = z.string().describe('YYYY-MM-DD');
const price = z.number().nullable();
const count = z.number().int().nullable();

export const stockInfoSchema = z.object({
  stock_id: z.string(),
  name: z.string().describe('證券簡稱'),
  full_name: z.string().nullable().describe('公司全名；ETF 等無公司資料者為 null'),
  market: marketSchema,
  security_type: z.enum(['stock', 'etf', 'other']).describe('other 表示來源資料不足以判定類別'),
  industry_code: z.string().nullable().describe('交易所產業別代碼'),
  listing_date: isoDate.nullable().describe('上市／上櫃日期'),
});

export const stockPriceSchema = z.object({
  stock_id: z.string(),
  name: z.string(),
  market: marketSchema,
  trade_date: isoDate.nullable().describe('這筆行情所屬的交易日'),
  open: price,
  high: price,
  low: price,
  close: price.describe('收盤價；當日無成交為 null'),
  change: price.describe('漲跌價差'),
  previous_close: price.describe('由 close - change 算出的前一日收盤價'),
  change_percent: price.describe('漲跌幅（%），由程式計算'),
  volume: count.describe('成交股數'),
  value: count.describe('成交金額（元）'),
  transactions: count.describe('成交筆數'),
});

export const priceBarSchema = z.object({
  date: isoDate,
  open: price,
  high: price,
  low: price,
  close: price,
  change: price,
  volume: count,
  value: count,
  transactions: count,
});

export const stockHistorySchema = z.object({
  stock_id: z.string(),
  name: z.string(),
  market: marketSchema,
  start_date: isoDate,
  end_date: isoDate,
  count: z.number().int().describe('期間內的交易日數'),
  bars: z.array(priceBarSchema).describe('依日期由舊到新'),
});

const flowSchema = z.object({
  buy: z.number().int(),
  sell: z.number().int(),
  net: z.number().int().describe('買賣超 = buy - sell；正為買超、負為賣超'),
});

const streakSchema = z.object({
  direction: z.enum(['buy', 'sell', 'flat']).nullable().describe('最近一個有資料交易日的方向'),
  days: z.number().int().describe('截至最近一個有資料的交易日，同方向連續的天數'),
});

export const institutionalFlowSchema = z.object({
  stock_id: z.string(),
  name: z.string(),
  market: marketSchema,
  start_date: isoDate,
  end_date: isoDate,
  days: z
    .array(
      z.object({
        date: isoDate,
        reported: z.boolean().describe('該日三大法人報表是否列有此證券'),
        foreign: flowSchema.nullable().describe('外資及陸資，含外資自營商'),
        investment_trust: flowSchema.nullable().describe('投信'),
        dealer: flowSchema.nullable().describe('自營商，自行買賣與避險合計'),
        total_net: z.number().int().nullable().describe('三大法人買賣超合計'),
      }),
    )
    .describe('依日期由舊到新'),
  summary: z.object({
    trading_days: z.number().int().describe('期間內的交易日數'),
    days_with_data: z.number().int().describe('其中有法人資料的天數'),
    cumulative_net: z
      .object({
        foreign: z.number().int(),
        investment_trust: z.number().int(),
        dealer: z.number().int(),
        total: z.number().int(),
      })
      .describe('期間累計買賣超，只計有資料的日子'),
    streaks: z.object({
      foreign: streakSchema,
      investment_trust: streakSchema,
      dealer: streakSchema,
      total: streakSchema,
    }),
    latest_alignment: z
      .enum(['all_buy', 'all_sell', 'mixed'])
      .nullable()
      .describe('最近一個有資料的交易日，外資、投信、自營商方向是否一致'),
  }),
});

export const marketSummarySchema = z.object({
  market: marketSchema,
  index_name: z.string(),
  trade_date: isoDate,
  close: z.number(),
  change: price,
  previous_close: price.describe('由 close - change 算出'),
  change_percent: price.describe('漲跌幅（%），由程式計算'),
  open: price,
  high: price,
  low: price,
  volume: count.describe('市場成交股數'),
  value: count.describe('市場成交金額（元）'),
  transactions: count.describe('市場成交筆數'),
  recent: z
    .array(z.object({ date: isoDate, close: z.number(), change: price }))
    .describe('近期收盤指數，依日期由舊到新，最多 10 日'),
});

export const stockInfoEnvelope = envelopeSchema(stockInfoSchema);
export const stockPriceEnvelope = envelopeSchema(stockPriceSchema);
export const stockHistoryEnvelope = envelopeSchema(stockHistorySchema);
export const institutionalFlowEnvelope = envelopeSchema(institutionalFlowSchema);
export const marketSummaryEnvelope = envelopeSchema(marketSummarySchema);

export type StockInfoResult = z.infer<typeof stockInfoEnvelope>;
export type StockPriceResult = z.infer<typeof stockPriceEnvelope>;
export type StockHistoryResult = z.infer<typeof stockHistoryEnvelope>;
export type InstitutionalFlowResult = z.infer<typeof institutionalFlowEnvelope>;
export type MarketSummaryResult = z.infer<typeof marketSummaryEnvelope>;
