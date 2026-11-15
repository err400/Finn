"""Yahoo's public chart endpoint, the same dataset family used by yfinance.
Personal educational use only; no SLA or public redistribution entitlement is implied.
"""
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo
from app.providers.contracts import Fetcher, PriceBatch, PricePoint, ProviderError

class YahooChartProvider:
    name = "yahoo_chart"
    def __init__(self, fetcher: Fetcher): self.fetcher = fetcher

    def history(self, ticker: str, start: date, end: date, force: bool = False) -> PriceBatch:
        # Date boundaries follow the exchange timezone. End is exclusive.
        ist = ZoneInfo("Asia/Kolkata")
        params = {"period1": int(datetime.combine(start, time.min, ist).timestamp()),
                  "period2": int(datetime.combine(end, time.min, ist).timestamp()), "interval": "1d", "events": "history"}
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker + '.NS', safe='')}?{urlencode(params)}"
        payload = self.fetcher.get(url, 6 * 3600, force)
        try:
            data = json.loads(payload.body, parse_float=Decimal)
            chart = data["chart"]
            if chart.get("error") or not chart.get("result"):
                raise ProviderError("symbol_unavailable", "Yahoo has no history for this symbol")
            result = chart["result"][0]
            meta = result["meta"]
            if meta.get("symbol", "").upper() != ticker + ".NS" or meta.get("currency") != "INR" or meta.get("exchangeTimezoneName") != "Asia/Kolkata" or meta.get("instrumentType") != "EQUITY":
                raise ProviderError("identity_mismatch", "Provider returned an unexpected symbol, currency, timezone or instrument")
            timestamps = result.get("timestamp") or []
            quotes = result["indicators"]["quote"][0]
            adjusted = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose", [])
            points, skipped = [], 0
            today = datetime.now(ist).date()
            for i, timestamp in enumerate(timestamps):
                day = datetime.fromtimestamp(timestamp, ist).date()
                # Exclude today's candle, including while the market is open; refresh next day.
                if not start <= day < end or day >= today: continue
                def number(key):
                    values = quotes.get(key, [])
                    raw = values[i] if i < len(values) else None
                    if raw is None: return None
                    val = Decimal(str(raw))
                    if not val.is_finite() or val <= 0: raise ValueError("Invalid OHLC")
                    return format(val, "f")
                try:
                    close = number("close")
                    volumes = quotes.get("volume", [])
                    volume = volumes[i] if i < len(volumes) else None
                    if close is None or volume is None or isinstance(volume, bool) or int(volume) != volume or volume < 0:
                        skipped += 1; continue
                    opening, high, low = number("open"), number("high"), number("low")
                    values = [Decimal(v) for v in [opening, close] if v is not None]
                    if high is not None and Decimal(high) < max(values): raise ValueError("Invalid high")
                    if low is not None and Decimal(low) > min(values): raise ValueError("Invalid low")
                    adj = Decimal(str(adjusted[i])) if i < len(adjusted) and adjusted[i] is not None else None
                    if adj is not None and (not adj.is_finite() or adj <= 0): raise ValueError("Invalid adjusted close")
                    points.append(PricePoint(day, opening, high, low, close, format(adj, "f") if adj else None, int(volume)))
                except (InvalidOperation, ValueError, TypeError): skipped += 1
            return PriceBatch(meta["symbol"], meta.get("longName") or meta.get("shortName") or ticker, "INR", points, payload, skipped)
        except ProviderError: raise
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ProviderError("invalid_payload", "Yahoo response was not the expected daily-price schema") from exc
