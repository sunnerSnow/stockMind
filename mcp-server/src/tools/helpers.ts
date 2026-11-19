import { EngineError, type EngineErrorCode } from '../services/engineClient.js';

/** 附在錯誤訊息後面、告訴 AI 這個錯誤代表什麼的補充說明。 */
const HINTS: Partial<Record<EngineErrorCode, string>> = {
  STOCK_NOT_FOUND: '請確認代號是否正確，或該證券是否已下市櫃。',
  UPSTREAM_ERROR: '這是資料來源的暫時性問題，不代表查詢的對象不存在。',
};

/** 統一的 Tool 錯誤回應：isError 加上可被 AI 讀懂的 JSON 內容。 */
export function toolError(code: EngineErrorCode, message: string) {
  const body = { success: false as const, error: { code, message } };
  return {
    isError: true,
    content: [{ type: 'text' as const, text: JSON.stringify(body) }],
  };
}

/**
 * 執行一次 Engine 呼叫並包成 Tool 回應。
 * 成功時同時回 structuredContent 與同內容的 JSON 文字（給只讀 content 的 client）。
 */
export async function runEngineTool<T extends Record<string, unknown>>(tool: string, call: () => Promise<T>) {
  try {
    const output = await call();
    return {
      content: [{ type: 'text' as const, text: JSON.stringify(output) }],
      structuredContent: output,
    };
  } catch (err) {
    if (err instanceof EngineError) {
      const hint = HINTS[err.code];
      return toolError(err.code, hint ? `${err.message}。${hint}` : err.message);
    }
    console.error(`[${tool}] 未預期的錯誤`, err);
    return toolError('INTERNAL_ERROR', '查詢時發生未預期的錯誤，請稍後再試。');
  }
}

export const READ_ONLY = { readOnlyHint: true, openWorldHint: true } as const;
