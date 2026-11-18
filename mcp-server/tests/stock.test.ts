import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createServer } from '../src/server.js';
import type { StockInfoProvider } from '../src/services/stockInfo.js';

async function connect(deps?: Parameters<typeof createServer>[0]) {
  const server = createServer(deps);
  const client = new Client({ name: 'test-client', version: '0.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
  return { server, client };
}

function textOf(result: { content?: unknown }): string {
  const first = (result.content as Array<{ type: string; text?: string }>)[0];
  return first?.text ?? '';
}

describe('get_stock_info', () => {
  let ctx: Awaited<ReturnType<typeof connect>>;

  beforeEach(async () => {
    ctx = await connect();
  });
  afterEach(async () => {
    await ctx.client.close();
    await ctx.server.close();
  });

  it('註冊在 tools/list，且帶有輸入與輸出 schema', async () => {
    const { tools } = await ctx.client.listTools();
    const tool = tools.find((t) => t.name === 'get_stock_info');
    expect(tool).toBeDefined();
    expect(tool?.inputSchema.required).toContain('stock_id');
    expect(tool?.outputSchema).toBeDefined();
  });

  it('正確代號回傳結構化結果，含來源與擷取時間', async () => {
    const result = await ctx.client.callTool({ name: 'get_stock_info', arguments: { stock_id: '2330' } });
    expect(result.isError).toBeFalsy();
    const out = result.structuredContent as any;
    expect(out.success).toBe(true);
    expect(out.data).toEqual({ stock_id: '2330', name: '台積電', market: 'TWSE', security_type: 'stock' });
    expect(out.metadata.source).toBe('fixture');
    expect(out.metadata.retrieved_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$/);
    expect(out.warnings.length).toBeGreaterThan(0);
    expect(JSON.parse(textOf(result))).toEqual(out);
  });

  it('上櫃股票標示為 TPEx', async () => {
    const result = await ctx.client.callTool({ name: 'get_stock_info', arguments: { stock_id: '6488' } });
    expect((result.structuredContent as any).data.market).toBe('TPEx');
  });

  it('格式正確但查無代號時回 STOCK_NOT_FOUND', async () => {
    const result = await ctx.client.callTool({ name: 'get_stock_info', arguments: { stock_id: '9999' } });
    expect(result.isError).toBe(true);
    const body = JSON.parse(textOf(result));
    expect(body).toMatchObject({ success: false, error: { code: 'STOCK_NOT_FOUND' } });
    expect(body.error.message).toContain('9999');
  });

  it.each([
    ['缺少 stock_id', {}],
    ['代號格式錯誤', { stock_id: 'TSMC' }],
    ['代號太短', { stock_id: '23' }],
    ['型別錯誤', { stock_id: 2330 }],
  ])('%s 時回明確的驗證錯誤', async (_label, args) => {
    const outcome = await ctx.client
      .callTool({ name: 'get_stock_info', arguments: args as Record<string, unknown> })
      .then(
        (r) => ({ isError: r.isError === true, text: textOf(r) }),
        (e: Error) => ({ isError: true, text: e.message }),
      );
    expect(outcome.isError).toBe(true);
    expect(outcome.text).toMatch(/stock_id/);
  });

  it('資料來源丟出非預期錯誤時回 INTERNAL_ERROR，不洩漏內部訊息', async () => {
    await ctx.client.close();
    await ctx.server.close();
    const failing: StockInfoProvider = {
      getStockInfo: async () => {
        throw new Error('secret connection string');
      },
    };
    ctx = await connect({ stockInfo: failing });
    const result = await ctx.client.callTool({ name: 'get_stock_info', arguments: { stock_id: '2330' } });
    expect(result.isError).toBe(true);
    const text = textOf(result);
    expect(JSON.parse(text).error.code).toBe('INTERNAL_ERROR');
    expect(text).not.toContain('secret');
  });
});
