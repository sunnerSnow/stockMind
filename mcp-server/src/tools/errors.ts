export type ToolErrorCode = 'STOCK_NOT_FOUND' | 'UPSTREAM_ERROR' | 'INTERNAL_ERROR';

/** 統一的 Tool 錯誤回應：isError 加上可被 AI 讀懂的 JSON 內容。 */
export function toolError(code: ToolErrorCode, message: string) {
  const body = { success: false as const, error: { code, message } };
  return {
    isError: true,
    content: [{ type: 'text' as const, text: JSON.stringify(body, null, 2) }],
  };
}
