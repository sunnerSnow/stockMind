import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import { afterEach, describe, expect, it } from 'vitest';
import { createServer } from '../src/server.js';
import { EngineClient } from '../src/services/engineClient.js';

/** 以下樣本的結構與 Financial Engine 實際回應一致。 */
const meta = (over: Record<string, unknown> = {}) => ({
  source: 'TWSE OpenAPI',
  data_date: '2026-11-17',
  retrieved_at: '2026-11-18T12:31:45+08:00',
  data_type: 'after_market',
  unit: null,
  ...over,
});

const INFO = {
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
  metadata: meta({ data_type: 'reference' }),
  warnings: [],
};

const PRICE = {
  success: true,
  data: {
    stock_id: '2330',
    name: '台積電',
    market: 'TWSE',
    trade_date: '2026-11-17',
    open: 2195,
    high: 2270,
    low: 2155,
    close: 2170,
    change: -45,
    previous_close: 2215,
    change_percent: -2.03,
    volume: 61610981,
    value: 135465361736,
    transactions: 371462,
  },
  metadata: meta({ unit: '價格：新台幣元；volume：股；value：元' }),
  warnings: ['這是最近一個交易日的盤後資料，不是即時行情。'],
};

const HISTORY = {
  success: true,
  data: {
    stock_id: '2330',
    name: '台積電',
    market: 'TWSE',
    start_date: '2026-11-16',
    end_date: '2026-11-17',
    count: 2,
    bars: [
      { date: '2026-11-16', open: 2340, high: 2350, low: 2215, close: 2215, change: -135, volume: 52604545, value: 119305254268, transactions: 408529 },
      { date: '2026-11-17', open: 2195, high: 2270, low: 2155, close: 2170, change: null, volume: 61610981, value: 135465361736, transactions: 371462 },
    ],
  },
  metadata: meta({ source: 'TWSE 盤後資訊', data_type: 'historical' }),
  warnings: [],
};

const flow = (net: number) => ({ buy: 1000, sell: 1000 - net, net });
const streak = (direction: string | null, days: number) => ({ direction, days });
const FLOW = {
  success: true,
  data: {
    stock_id: '2330',
    name: '台積電',
    market: 'TWSE',
    start_date: '2026-11-13',
    end_date: '2026-11-17',
    days: [
      { date: '2026-11-13', reported: false, foreign: null, investment_trust: null, dealer: null, total_net: null },
      { date: '2026-11-17', reported: true, foreign: flow(-300), investment_trust: flow(-5), dealer: flow(-1), total_net: -306 },
    ],
    summary: {
      trading_days: 2,
      days_with_data: 1,
      cumulative_net: { foreign: -300, investment_trust: -5, dealer: -1, total: -306 },
      streaks: { foreign: streak('sell', 1), investment_trust: streak('sell', 1), dealer: streak('sell', 1), total: streak('sell', 1) },
      latest_alignment: 'all_sell',
    },
  },
  metadata: meta({ source: 'TWSE 盤後資訊', data_type: 'historical', unit: '股' }),
  warnings: [],
};

const SUMMARY = {
  success: true,
  data: {
    market: 'TPEx',
    index_name: '櫃買指數',
    trade_date: '2026-11-17',
    close: 292.42,
    change: -10.08,
    previous_close: 302.5,
    change_percent: -3.33,
    open: 301,
    high: 303,
    low: 290.1,
    volume: null,
    value: null,
    transactions: null,
    recent: [{ date: '2026-11-17', close: 292.42, change: -10.08 }],
  },
  metadata: meta({ source: 'TPEx OpenAPI' }),
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
async function connect(fakeFetch: FakeFetch, baseUrl = 'http://engine.test') {
  const requested: string[] = [];
  const engine = new EngineClient({
    baseUrl,
    timeoutMs: 50,
    fetch: (async (input: URL) => {
      requested.push(input.toString());
      return fakeFetch(input);
    }) as unknown as typeof fetch,
  });
  const server = createServer({ engine });
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

const call = (client: Client, name: string, args: Record<string, unknown>) =>
  client.callTool({ name, arguments: args });

/** 呼叫結果不論是 isError 回應還是丟出例外，都整理成同一種形狀。 */
const outcomeOf = (promise: ReturnType<typeof call>) =>
  promise.then(
    (r) => ({ isError: r.isError === true, text: textOf(r) }),
    (e: Error) => ({ isError: true, text: e.message }),
  );

const TOOLS = [
  { name: 'get_stock_info', args: { stock_id: '2330' }, body: INFO, url: 'http://engine.test/stocks/2330' },
  { name: 'get_stock_price', args: { stock_id: '2330' }, body: PRICE, url: 'http://engine.test/stocks/2330/price' },
  {
    name: 'get_stock_history',
    args: { stock_id: '2330', start_date: '2026-11-16', end_date: '2026-11-17' },
    body: HISTORY,
    url: 'http://engine.test/stocks/2330/history?start_date=2026-11-16&end_date=2026-11-17',
  },
  {
    name: 'get_institutional_flow',
    args: { stock_id: '2330', start_date: '2026-11-13', end_date: '2026-11-17' },
    body: FLOW,
    url: 'http://engine.test/stocks/2330/institutional-flow?start_date=2026-11-13&end_date=2026-11-17',
  },
  { name: 'get_market_summary', args: { market: 'TPEx' }, body: SUMMARY, url: 'http://engine.test/market/TPEx/summary' },
] as const;

describe('工具清單', () => {
  it('五個工具都註冊，且各有輸入與輸出 schema、標示為唯讀', async () => {
    const { client } = await connect(() => json(200, INFO));
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name).sort()).toEqual(TOOLS.map((t) => t.name).sort());
    for (const tool of tools) {
      expect(tool.description, tool.name).toBeTruthy();
      expect(tool.outputSchema, tool.name).toBeDefined();
      expect(tool.annotations?.readOnlyHint, tool.name).toBe(true);
    }
    expect(tools.find((t) => t.name === 'get_stock_price')?.description).toContain('不是即時');
  });
});

describe.each(TOOLS)('$name', ({ name, args, body, url }) => {
  it('呼叫正確的 Engine 端點，並把結果原樣回傳', async () => {
    const { client, requested } = await connect(() => json(200, body));
    const result = await call(client, name, args);
    expect(result.isError).toBeFalsy();
    expect(result.structuredContent).toEqual(body);
    expect(JSON.parse(textOf(result))).toEqual(body);
    expect(requested).toEqual([url]);
  });

  it('回傳含資料來源、資料日期與擷取時間', async () => {
    const { client } = await connect(() => json(200, body));
    const out = (await call(client, name, args)).structuredContent as typeof body;
    expect(out.metadata.source).toBeTruthy();
    expect(out.metadata.data_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(out.metadata.retrieved_at).toMatch(/\+08:00$/);
  });

  it('資料來源失敗時回 UPSTREAM_ERROR', async () => {
    const { client } = await connect(() =>
      engineError(502, 'UPSTREAM_ERROR', '資料來源 TWSE OpenAPI 目前無法取得資料：連線逾時'),
    );
    const result = await call(client, name, args);
    expect(result.isError).toBe(true);
    const error = JSON.parse(textOf(result)).error;
    expect(error.code).toBe('UPSTREAM_ERROR');
    expect(error.message).toContain('TWSE OpenAPI');
    expect(error.message).toContain('不代表查詢的對象不存在');
  });

  it('Engine 沒啟動時回 ENGINE_UNAVAILABLE，並提示要啟動服務', async () => {
    const { client } = await connect(() => {
      throw new TypeError('fetch failed');
    });
    const error = JSON.parse(textOf(await call(client, name, args))).error;
    expect(error.code).toBe('ENGINE_UNAVAILABLE');
    expect(error.message).toContain('http://engine.test');
  });

  it('Engine 回應格式不符時回 INTERNAL_ERROR，不把內容當成資料回傳', async () => {
    const { client } = await connect(() => json(200, { success: true, data: { secret: 'secret detail' } }));
    const result = await call(client, name, args);
    expect(result.isError).toBe(true);
    expect(JSON.parse(textOf(result)).error.code).toBe('INTERNAL_ERROR');
    expect(textOf(result)).not.toContain('secret');
  });
});

describe('錯誤轉譯', () => {
  it('查無代號時回 STOCK_NOT_FOUND', async () => {
    const { client } = await connect(() => engineError(404, 'STOCK_NOT_FOUND', '查無股票代號 9999'));
    const result = await call(client, 'get_stock_price', { stock_id: '9999' });
    expect(result.isError).toBe(true);
    const error = JSON.parse(textOf(result)).error;
    expect(error.code).toBe('STOCK_NOT_FOUND');
    expect(error.message).toContain('9999');
  });

  it('Engine 判定範圍不合理時，把原因原樣轉述', async () => {
    const { client } = await connect(() => engineError(422, 'INVALID_INPUT', '查詢範圍最多 31 天，請縮小範圍'));
    const result = await call(client, 'get_institutional_flow', {
      stock_id: '2330',
      start_date: '2026-01-01',
      end_date: '2026-11-17',
    });
    const error = JSON.parse(textOf(result)).error;
    expect(error).toEqual({ code: 'INVALID_INPUT', message: '查詢範圍最多 31 天，請縮小範圍' });
  });

  it('Engine 逾時時回 ENGINE_UNAVAILABLE', async () => {
    const { client } = await connect(() => {
      throw new DOMException('timed out', 'TimeoutError');
    });
    const error = JSON.parse(textOf(await call(client, 'get_stock_history', { stock_id: '2330' }))).error;
    expect(error.code).toBe('ENGINE_UNAVAILABLE');
    expect(error.message).toContain('沒有回應');
  });

  it.each([
    ['未知的錯誤碼', () => engineError(500, 'DB_PASSWORD_LEAK', 'secret detail')],
    ['非 JSON 的錯誤頁', () => new Response('<html>secret detail</html>', { status: 500 })],
  ])('Engine 回 %s 時回 INTERNAL_ERROR，不轉述內部內容', async (_label, respond) => {
    const { client } = await connect(respond);
    const text = textOf(await call(client, 'get_stock_info', { stock_id: '2330' }));
    expect(JSON.parse(text).error.code).toBe('INTERNAL_ERROR');
    expect(text).not.toContain('secret');
  });
});

describe('輸入驗證（不呼叫 Engine）', () => {
  it.each([
    ['get_stock_info', {}, /stock_id/],
    ['get_stock_info', { stock_id: 'TSMC' }, /stock_id/],
    ['get_stock_price', { stock_id: '23' }, /stock_id/],
    ['get_stock_price', { stock_id: 2330 }, /stock_id/], // 數字會丟失前導零
    ['get_stock_history', { stock_id: '../health' }, /stock_id/],
    ['get_stock_history', { stock_id: '2330', period: '10y' }, /period/],
    ['get_stock_history', { stock_id: '2330', start_date: '2026/11/01' }, /start_date/],
    ['get_institutional_flow', { stock_id: '2330', end_date: '11-17' }, /end_date/],
    ['get_market_summary', { market: 'NYSE' }, /market/],
  ])('%s %j', async (name, args, pattern) => {
    const { client, requested } = await connect(() => json(200, INFO));
    const outcome = await outcomeOf(call(client, name, args as Record<string, unknown>));
    expect(outcome.isError).toBe(true);
    expect(outcome.text).toMatch(pattern);
    expect(requested).toEqual([]);
  });
});

describe('參數傳遞', () => {
  it('get_stock_history 只帶有給的參數', async () => {
    const { client, requested } = await connect(() => json(200, HISTORY));
    await call(client, 'get_stock_history', { stock_id: '2330', period: '3mo' });
    await call(client, 'get_stock_history', { stock_id: '2330' });
    expect(requested).toEqual([
      'http://engine.test/stocks/2330/history?period=3mo',
      'http://engine.test/stocks/2330/history',
    ]);
  });

  it('get_market_summary 未指定市場時查上市', async () => {
    const { client, requested } = await connect(() => json(200, { ...SUMMARY, data: { ...SUMMARY.data, market: 'TWSE' } }));
    await call(client, 'get_market_summary', {});
    expect(requested).toEqual(['http://engine.test/market/TWSE/summary']);
  });
});

describe('EngineClient 設定', () => {
  it.each(['file:///etc/passwd', 'not a url', 'ftp://host'])('拒絕不合法的位址 %s', (baseUrl) => {
    expect(() => new EngineClient({ baseUrl })).toThrow(/STOCKMIND_ENGINE_URL/);
  });

  it.each([
    [undefined, 'http://127.0.0.1:8000/stocks/2330'],
    ['http://host:9000', 'http://host:9000/stocks/2330'],
    ['http://host/api', 'http://host/api/stocks/2330'], // 保留路徑前綴
    ['http://host/api/?x=1#frag', 'http://host/api/stocks/2330'],
  ])('位址 %s 組出 %s', async (baseUrl, expected) => {
    const seen: string[] = [];
    const engine = new EngineClient({
      baseUrl,
      fetch: (async (input: URL) => {
        seen.push(input.toString());
        return json(200, INFO);
      }) as unknown as typeof fetch,
    });
    await engine.getStockInfo('2330');
    expect(seen).toEqual([expected]);
  });
});
