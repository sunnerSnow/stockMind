"""執行設定。全部可用環境變數覆寫，預設值適合本機開發。"""

import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # 對外部資料來源的單次請求逾時（秒）
    http_timeout: float = 15.0
    # 失敗後的重試次數（不含第一次）
    http_retries: int = 2
    # 重試間隔的基準秒數，每次加倍
    http_backoff: float = 0.5
    # 證券清單快取存活時間（秒）；基本資料一天內不會變
    securities_ttl: float = 6 * 60 * 60
    user_agent: str = "stockmind-engine/0.1"


def load_settings() -> Settings:
    return Settings(
        http_timeout=_float("STOCKMIND_HTTP_TIMEOUT", Settings.http_timeout),
        http_retries=_int("STOCKMIND_HTTP_RETRIES", Settings.http_retries),
        http_backoff=_float("STOCKMIND_HTTP_BACKOFF", Settings.http_backoff),
        securities_ttl=_float("STOCKMIND_SECURITIES_TTL", Settings.securities_ttl),
    )
