import { z } from 'zod';
import {
  institutionalFlowEnvelope,
  marketSummaryEnvelope,
  stockHistoryEnvelope,
  stockInfoEnvelope,
  stockPriceEnvelope,
  technicalIndicatorsEnvelope,
  type InstitutionalFlowResult,
  type MarketSummaryResult,
  type StockHistoryResult,
  type StockInfoResult,
  type StockPriceResult,
  type TechnicalIndicatorsResult,
} from '../schemas/stock.js';

export const DEFAULT_ENGINE_URL = 'http://127.0.0.1:8000';
/**
 * 必須比 Engine 最慢的查詢久：首次查一個月的三大法人要逐日向交易所取資料，
 * 受節流限制約需一分鐘。MCP 端先逾時的話，使用者只會看到「Engine 沒有回應」。
 */
const DEFAULT_TIMEOUT_MS = 120_000;

export type EngineErrorCode =
  | 'STOCK_NOT_FOUND'
  | 'INVALID_INPUT'
  | 'UPSTREAM_ERROR'
  | 'ENGINE_UNAVAILABLE'
  | 'INTERNAL_ERROR';

/** 可以直接轉述給使用者的錯誤：code 與 message 都不含內部細節。 */
export class EngineError extends Error {
  constructor(
    public readonly code: EngineErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'EngineError';
  }
}

const engineErrorSchema = z.object({
  success: z.literal(false),
  error: z.object({ code: z.string(), message: z.string() }),
});

/** Engine 會回、且 MCP 端願意原樣轉述的錯誤碼。其餘一律視為內部錯誤。 */
const PASSTHROUGH_CODES: ReadonlySet<string> = new Set(['STOCK_NOT_FOUND', 'INVALID_INPUT', 'UPSTREAM_ERROR']);

export interface DateRange {
  start_date?: string;
  end_date?: string;
}

/** MCP Tools 需要的 Engine 功能。測試可注入替身。 */
export interface EngineApi {
  getStockInfo(stockId: string): Promise<StockInfoResult>;
  getStockPrice(stockId: string): Promise<StockPriceResult>;
  getStockHistory(stockId: string, query: DateRange & { period?: string }): Promise<StockHistoryResult>;
  getInstitutionalFlow(stockId: string, query: DateRange): Promise<InstitutionalFlowResult>;
  getMarketSummary(market: string): Promise<MarketSummaryResult>;
  getTechnicalIndicators(
    stockId: string,
    query: DateRange & { period?: string; indicators?: string[] },
  ): Promise<TechnicalIndicatorsResult>;
}

export interface EngineClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetch?: typeof fetch;
}

/** 解析並檢查 Engine 位址，只允許 http／https。 */
export function resolveEngineUrl(raw: string | undefined): URL {
  const value = raw?.trim() || DEFAULT_ENGINE_URL;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`STOCKMIND_ENGINE_URL 不是有效的網址：${value}`);
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(`STOCKMIND_ENGINE_URL 只支援 http 或 https：${value}`);
  }
  // 結尾補上斜線，之後以相對路徑組網址時才會保留路徑前綴（例如 http://host/api）
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  url.search = '';
  url.hash = '';
  return url;
}

/** 透過 HTTP 呼叫 Financial Engine。 */
export class EngineClient implements EngineApi {
  private readonly baseUrl: URL;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: EngineClientOptions = {}) {
    this.baseUrl = resolveEngineUrl(options.baseUrl);
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.fetchImpl = options.fetch ?? fetch;
  }

  getStockInfo(stockId: string) {
    return this.get(['stocks', stockId], {}, stockInfoEnvelope);
  }

  getStockPrice(stockId: string) {
    return this.get(['stocks', stockId, 'price'], {}, stockPriceEnvelope);
  }

  getStockHistory(stockId: string, query: DateRange & { period?: string }) {
    return this.get(['stocks', stockId, 'history'], query, stockHistoryEnvelope);
  }

  getInstitutionalFlow(stockId: string, query: DateRange) {
    return this.get(['stocks', stockId, 'institutional-flow'], query, institutionalFlowEnvelope);
  }

  getMarketSummary(market: string) {
    return this.get(['market', market, 'summary'], {}, marketSummaryEnvelope);
  }

  getTechnicalIndicators(stockId: string, query: DateRange & { period?: string; indicators?: string[] }) {
    return this.get(['stocks', stockId, 'indicators'], query, technicalIndicatorsEnvelope);
  }

  private async get<T>(segments: string[], query: object, schema: z.ZodType<T>): Promise<T> {
    const url = new URL(segments.map(encodeURIComponent).join('/'), this.baseUrl);
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined) continue;
      // 陣列以重複的參數送出（?indicators=MA5&indicators=MACD）
      for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(item));
    }

    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        headers: { accept: 'application/json' },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      if (err instanceof Error && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
        throw new EngineError(
          'ENGINE_UNAVAILABLE',
          `Financial Engine 在 ${this.timeoutMs / 1000} 秒內沒有回應，請稍後再試。`,
        );
      }
      throw new EngineError(
        'ENGINE_UNAVAILABLE',
        `無法連線到 Financial Engine（${this.baseUrl.origin}）。請確認服務已啟動。`,
      );
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new EngineError('INTERNAL_ERROR', 'Financial Engine 回傳的內容無法解析。');
    }

    if (!response.ok) {
      const parsed = engineErrorSchema.safeParse(body);
      if (parsed.success && PASSTHROUGH_CODES.has(parsed.data.error.code)) {
        throw new EngineError(parsed.data.error.code as EngineErrorCode, parsed.data.error.message);
      }
      console.error(`[engine] ${url.pathname} 回 HTTP ${response.status}`, body);
      throw new EngineError('INTERNAL_ERROR', 'Financial Engine 發生未預期的錯誤，請稍後再試。');
    }

    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      console.error(`[engine] ${url.pathname} 回應格式不符`, parsed.error.issues);
      throw new EngineError('INTERNAL_ERROR', 'Financial Engine 的回應格式與預期不符。');
    }
    return parsed.data;
  }
}
