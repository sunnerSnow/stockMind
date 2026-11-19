"""執行設定。全部可用環境變數覆寫，預設值適合本機開發。"""

import os
from dataclasses import dataclass, fields
from pathlib import Path

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"


@dataclass(frozen=True)
class Settings:
    # 對外部資料來源的單次請求逾時（秒）
    http_timeout: float = 10.0
    # 失敗後的重試次數（不含第一次）
    http_retries: int = 2
    # 重試間隔的基準秒數，每次加倍
    http_backoff: float = 0.5
    # 對交易所網站（非 OpenAPI）連續請求的最小間隔（秒）；太密會被暫時封鎖
    throttle_interval: float = 1.5
    # 公司基本資料快取秒數；一天內不會變
    securities_ttl: float = 6 * 60 * 60
    # 當日行情、指數等會在收盤後更新的資料的快取秒數
    quotes_ttl: float = 5 * 60
    # 已定案的歷史資料（過去的月份、過去的交易日）存到磁碟的位置；空字串表示不存
    cache_dir: str = str(DEFAULT_CACHE_DIR)
    # 單次查詢的日期範圍上限（日曆天）
    max_history_days: int = 366
    max_flow_days: int = 31
    user_agent: str = "stockmind-engine/0.1"


_ENV = {
    "http_timeout": "STOCKMIND_HTTP_TIMEOUT",
    "http_retries": "STOCKMIND_HTTP_RETRIES",
    "http_backoff": "STOCKMIND_HTTP_BACKOFF",
    "throttle_interval": "STOCKMIND_THROTTLE_INTERVAL",
    "securities_ttl": "STOCKMIND_SECURITIES_TTL",
    "quotes_ttl": "STOCKMIND_QUOTES_TTL",
    "cache_dir": "STOCKMIND_CACHE_DIR",
}
# 必須大於 0 的設定；其餘數值設定只需不為負
_POSITIVE = {"http_timeout"}


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """讀取環境變數。格式不對時直接指出是哪一個變數，不帶著錯誤設定啟動。"""
    source = os.environ if env is None else env
    types = {f.name: f.type for f in fields(Settings)}
    values: dict[str, object] = {}
    for name, key in _ENV.items():
        raw = source.get(key)
        if raw is None or (raw.strip() == "" and name != "cache_dir"):
            continue
        if types[name] is str:
            values[name] = raw.strip()
            continue
        try:
            number = int(raw) if types[name] is int else float(raw)
        except ValueError:
            raise ValueError(f"環境變數 {key} 必須是數字，目前是 {raw!r}") from None
        if number < 0 or (name in _POSITIVE and number == 0):
            raise ValueError(f"環境變數 {key} 的值不合理：{raw!r}")
        values[name] = number
    return Settings(**values)
