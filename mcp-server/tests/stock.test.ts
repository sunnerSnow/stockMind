import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import { afterEach, describe, expect, it } from 'vitest';
import { createServer } from '../src/server.js';
import { EngineClient } from '../src/services/engineClient.js';

const TSMC = {
  success: true,
  data: {
    stock_id: '2330',
    name: '台積電',
    full_name: '台灣積體電路製造股份有限公司',
    market: 'TWSE',
    security_type: 'stock',
    industry_code: '24',
    listing_date: '1994-09-05',
  },
  metadata: {
    source: 'TWSE OpenAPI',
    data_date: '2026-11-17',
    retrieved_at: '2026-11-18T12:31:45+08:00',
    data_type: 'reference',
    unit: null,
  },
  warnings: [],
};

type FakeFetch = (url: URL) => Response | Promise<Response>;

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const engineError = (status: number, code: string, message: string) =>
  json(status, { success: false, error: { code, message } });

let cleanup: Array<() => Promise<void>> = [];
afterEach(async () => {
  for (const fn of cleanup) await fn();
  cleanup = [];
});

/** 建一組以記憶體傳輸相連的 client／server，Engine 以假的 fetch 取代。 */
async function connect(fakeFetch: FakeFetch) {
  const requested: string[] = [];
  const engine = new EngineClient({
    baseUrl: 'http://engine.test',
    timeoutMs: 50,
    fetch: (async (input: URL) => {
      requested.push(input.toString());
      return fakeFetch(input);
    }) as unknown as typeof fetch,
  });
  const server = createServer({ stockInfo: engine });
  const client = new Client({ name: 'test-client', version: '0.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
  cleanup.push(() => client.close(), () => server.close());
  return { client, requested };
}

function textOf(result: { content?: unknown }): string {
  const first = (result.content as Array<{ type: string; text?: string }>)[0];
  return first?.text ?? '';
}

const call = (client: Client, args: Record<string, unknown>) =>
  client.callTool({ name: 'get_stock_info', arguments: args });

describe('get_stock_info', () => {
  it('註冊在 tools/list，且帶有輸入與輸出 schema', async () => {
    const { client } = await connect(() => json(200, TSMC));
    const { tools } = await client.listTools();
    const tool = tools.find((t) => t.name === 'get_stock_info');
    expect(tool?.inputSchema.required).toContain('stock_id');
    expect(tool?.outputSchema).toBeDefined();
  });

  it('把 Engine 的結果原樣回傳，含來源、資料日期與擷取時間', async () => {
    const { client, requested } = await connect(() => json(200, TSMC));
    const result = await call(client, { stock_id: '2330' });
    expect(result.isError).toBeFalsy();
    expect(result.structuredContent).toEqual(TSMC);
    expect(JSON.parse(textOf(result))).toEqual(TSMC);
    expect(requested).toEqual(['http://engine.test/stocks/2330']);
  });

  it('查無代號時回 STOCK_NOT_FOUND', async () => {
    const { client } = await connect(() => engineError(404, 'STOCK_NOT_FOUND', '查無股票代號 9999'));
    const result = await call(client, { stock_id: '9999' });
    expect(result.isError).toBe(true);
    const body = JSON.parse(textOf(result));
    expect(body.error.code).toBe('STOCK_NOT_FOUND');
    expect(body.error.message).toContain('9999');
  });

  it('資料來源失敗時回 UPSTREAM_ERROR，並說明不代表股票不存在', async () => {
    const { client } = await connect(() =>
      engineError(502, 'UPSTREAM_ERROR', '資料來源 TWSE OpenAPI 目前無法取得資料：連線逾時'),
    );
    const body = JSON.parse(textOf(await call(client, { stock_id: '2330' })));
    expect(body.error.code).toBe('UPSTREAM_ERROR');
    expect(body.error.message).toContain('TWSE OpenAPI');
    expect(body.error.message).toContain('不代表該股票不存在');
  });

  it('Engine 沒啟動時回 ENGINE_UNAVAILABLE，並提示要啟動服務', async () => {
    const { client } = await connect(() => {
      throw new TypeError('fetch failed');
    });
    const result = await call(client, { stock_id: '2330' });
    expect(result.isError).toBe(true);
    const body = JSON.parse(textOf(result));
    expect(body.error.code).toBe('ENGINE_UNAVAILABLE');
    expect(body.error.message).toContain('http://engine.test');
  });

  it('Engine 逾時時回 ENGINE_UNAVAILABLE', async () => {
    const { client } = await connect(() => {
      throw new DOMException('timed out', 'TimeoutError');
    });
    const body = JSON.parse(textOf(await call(client, { stock_id: '2330' })));
    expect(body.error.code).toBe('ENGINE_UNAVAILABLE');
    expect(body.error.message).toContain('沒有回應');
  });

  it.each([
    ['未知的錯誤碼', () => engineError(500, 'DB_PASSWORD_LEAK', 'secret detail')],
    ['非 JSON 的錯誤頁', () => new Response('<html>secret detail</html>', { status: 500 })],
    ['成功但格式不符', () => json(200, { success: true, data: { secret: 'secret detail' } })],
  ])('Engine 回 %s 時回 INTERNAL_ERROR，不轉述內部內容', async (_label, respond) => {
    const { client } = await connect(respond);
    const result = await call(client, { stock_id: '2330' });
    expect(result.isError).toBe(true);
    const text = textOf(result);
    expect(JSON.parse(text).error.code).toBe('INTERNAL_ERROR');
    expect(text).not.toContain('secret');
  });

  it.each([
    ['缺少 stock_id', {}],
    ['代號格式錯誤', { stock_id: 'TSMC' }],
    ['代號太短', { stock_id: '23' }],
    ['數字型別（會丟失前導零）', { stock_id: 2330 }],
    ['夾帶路徑字元', { stock_id: '../health' }],
  ])('%s 時回驗證錯誤，且不呼叫 Engine', async (_label, args) => {
    const { client, requested } = await connect(() => json(200, TSMC));
    const outcome = await call(client, args).then(
      (r) => ({ isError: r.isError === true, text: textOf(r) }),
      (e: Error) => ({ isError: true, text: e.message }),
    );
    expect(outcome.isError).toBe(true);
    expect(outcome.text).toMatch(/stock_id/);
    expect(requested).toEqual([]);
  });
});

describe('EngineClient 設定', () => {
  it.each(['file:///etc/passwd', 'not a url', 'ftp://host'])('拒絕不合法的位址 %s', (baseUrl) => {
    expect(() => new EngineClient({ baseUrl })).toThrow(/STOCKMIND_ENGINE_URL/);
  });

  it('未設定時使用本機預設位址', async () => {
    const seen: string[] = [];
    const engine = new EngineClient({
      fetch: (async (input: URL) => {
        seen.push(input.toString());
        return json(200, TSMC);
      }) as unknown as typeof fetch,
    });
    await engine.getStockInfo('2330');
    expect(seen).toEqual(['http://127.0.0.1:8000/stocks/2330']);
  });
});
