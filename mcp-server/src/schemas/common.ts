import { z } from 'zod';

/**
 * 台股證券代號：4–6 位數字，可帶一個大寫英文字尾（例如 2330、0050、00878、00679B）。
 * 只驗格式；代號是否存在由資料層判斷。
 */
export const stockIdSchema = z
  .string()
  .trim()
  .regex(/^\d{4,6}[A-Z]?$/, '股票代號格式錯誤：需為 4–6 位數字，可帶一個大寫英文字尾，例如 2330、00878、00679B')
  .describe('台股證券代號，例如 2330');

export const marketSchema = z.enum(['TWSE', 'TPEx']).describe('TWSE＝上市，TPEx＝上櫃');

export const dataTypeSchema = z
  .enum(['reference', 'historical', 'delayed', 'intraday', 'after_market'])
  .describe('資料性質；reference 表示基本資料這類非行情資料');

/** 所有資料類 Tool 共用的來源／時間資訊。 */
export const metadataSchema = z.object({
  source: z.string().describe('資料來源名稱'),
  data_date: z.string().nullable().describe('資料日期 YYYY-MM-DD（台灣市場日期）；無日期語意時為 null'),
  retrieved_at: z.string().describe('擷取時間，ISO 8601，含時區'),
  data_type: dataTypeSchema,
  unit: z.string().nullable().describe('數值單位；無數值欄位時為 null'),
});

export type Metadata = z.infer<typeof metadataSchema>;

/** 成功回應的統一外層結構。 */
export function envelopeSchema<T extends z.ZodType>(data: T) {
  return z.object({
    success: z.literal(true),
    data,
    metadata: metadataSchema,
    warnings: z.array(z.string()),
  });
}

/** 以台灣時區（+08:00）輸出 ISO 8601 時間戳記。 */
export function taipeiTimestamp(now: Date = new Date()): string {
  const shifted = new Date(now.getTime() + 8 * 60 * 60 * 1000);
  return shifted.toISOString().replace(/\.\d{3}Z$/, '+08:00');
}
