import { z } from 'zod';
import type { ToolErrorCode } from '../tools/errors.js';
import { stockInfoEnvelopeSchema, type StockInfoProvider, type StockInfoResult } from './stockInfo.js';

export const DEFAULT_ENGINE_URL = 'http://127.0.0.1:8000';
const DEFAULT_TIMEOUT_MS = 30_000;

/** 可以直接轉述給使用者的錯誤：code 與 message 都不含內部細節。 */
export class EngineError extends Error {
  constructor(
    public readonly code: ToolErrorCode,
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
const PASSTHROUGH_CODES = new Set<ToolErrorCode>(['STOCK_NOT_FOUND', 'UPSTREAM_ERROR']);

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
  return url;
}

/** 透過 HTTP 呼叫 Financial Engine。 */
export class EngineClient implements StockInfoProvider {
  private readonly baseUrl: URL;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: EngineClientOptions = {}) {
    this.baseUrl = resolveEngineUrl(options.baseUrl);
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.fetchImpl = options.fetch ?? fetch;
  }

  getStockInfo(stockId: string): Promise<StockInfoResult> {
    return this.get(`/stocks/${encodeURIComponent(stockId)}`, stockInfoEnvelopeSchema);
  }

  private async get<T>(path: string, schema: z.ZodType<T>): Promise<T> {
    const url = new URL(path, this.baseUrl);

    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        headers: { accept: 'application/json' },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      if (err instanceof Error && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
        throw new EngineError('ENGINE_UNAVAILABLE', `Financial Engine 在 ${this.timeoutMs / 1000} 秒內沒有回應，請稍後再試。`);
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
      const code = parsed.success ? (parsed.data.error.code as ToolErrorCode) : undefined;
      if (parsed.success && code && PASSTHROUGH_CODES.has(code)) {
        throw new EngineError(code, parsed.data.error.message);
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
