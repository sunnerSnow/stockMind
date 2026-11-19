"""領域錯誤。API 層統一轉成 {success: false, error: {code, message}}。"""


class EngineError(Exception):
    code = "INTERNAL_ERROR"
    http_status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class StockNotFoundError(EngineError):
    code = "STOCK_NOT_FOUND"
    http_status = 404

    def __init__(self, stock_id: str):
        super().__init__(f"查無股票代號 {stock_id}")
        self.stock_id = stock_id


class UpstreamError(EngineError):
    """外部資料來源連線失敗、逾時或回傳無法解析的內容。"""

    code = "UPSTREAM_ERROR"
    http_status = 502

    def __init__(self, source: str, detail: str):
        super().__init__(f"資料來源 {source} 目前無法取得資料：{detail}")
        self.source = source


class InvalidRangeError(EngineError):
    """查詢參數彼此矛盾或超出上限。"""

    code = "INVALID_INPUT"
    http_status = 422
