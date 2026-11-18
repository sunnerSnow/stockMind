import type { Metadata } from '../schemas/common.js';
import { taipeiTimestamp } from '../schemas/common.js';

export interface StockInfo {
  stock_id: string;
  name: string;
  market: 'TWSE' | 'TPEx';
  security_type: 'stock' | 'etf';
}

export interface StockInfoResult {
  data: StockInfo;
  metadata: Metadata;
  warnings: string[];
}

/** 查無此代號。與格式錯誤（由 schema 擋下）分開處理。 */
export class StockNotFoundError extends Error {
  constructor(public readonly stockId: string) {
    super(`查無股票代號 ${stockId}`);
    this.name = 'StockNotFoundError';
  }
}

/** 股票基本資料來源。Milestone 2 會換成呼叫 Financial Engine 的實作。 */
export interface StockInfoProvider {
  getStockInfo(stockId: string): Promise<StockInfoResult>;
}

const FIXTURE: readonly StockInfo[] = [
  { stock_id: '2330', name: '台積電', market: 'TWSE', security_type: 'stock' },
  { stock_id: '2317', name: '鴻海', market: 'TWSE', security_type: 'stock' },
  { stock_id: '2454', name: '聯發科', market: 'TWSE', security_type: 'stock' },
  { stock_id: '6488', name: '環球晶', market: 'TPEx', security_type: 'stock' },
  { stock_id: '0050', name: '元大台灣50', market: 'TWSE', security_type: 'etf' },
];

/** 固定測試資料，只用來驗證 MCP 通訊流程。 */
export class FixtureStockInfoProvider implements StockInfoProvider {
  async getStockInfo(stockId: string): Promise<StockInfoResult> {
    const found = FIXTURE.find((s) => s.stock_id === stockId);
    if (!found) throw new StockNotFoundError(stockId);
    return {
      data: found,
      metadata: {
        source: 'fixture',
        data_date: null,
        retrieved_at: taipeiTimestamp(),
        data_type: 'reference',
        unit: null,
      },
      warnings: ['目前為內建固定測試資料，尚未接上 TWSE／TPEx 官方來源，僅涵蓋少數代號。'],
    };
  }
}
