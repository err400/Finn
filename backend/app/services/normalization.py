import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote, unquote
from zoneinfo import ZoneInfo
from app.providers.contracts import ProviderError

IST = ZoneInfo("Asia/Kolkata")

def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def normalize_symbol(value: str) -> tuple[str, str]:
    value = value.strip().upper()
    exchange = "NSE"
    if value.startswith("NSE:"): value = value[4:]
    elif value.startswith("BSE:"): exchange, value = "BSE", value[4:]
    if value.endswith(".NS"):
        if exchange == "BSE": raise ValueError("Conflicting exchange qualifiers")
        value = value[:-3]
    elif value.endswith(".BO"): exchange, value = "BSE", value[:-3]
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9&_-]{0,39}", value):
        raise ValueError("Expected an NSE symbol or mapped BSE security code")
    return exchange, value

def normalize_name(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"\b(limited|ltd)\b\.?", "", value)
    return re.sub(r"[^a-z0-9]", "", value)

def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise ProviderError("unsafe_url", "Only ordinary public HTTP(S) source URLs are supported")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    path = quote(unquote(parts.path or "/"), safe="/!$&'()*+,;=:@-._~")
    return urlunsplit(("https", parts.hostname.lower(), path, urlencode(sorted(query)), ""))

def filing_datetime(value: str) -> datetime:
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None:
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d %b %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try: parsed = datetime.strptime(value, fmt); break
            except ValueError: pass
    if parsed is None:
        try: parsed = datetime.fromisoformat(value)
        except ValueError as exc: raise ProviderError("invalid_date", "Unrecognized exchange publication timestamp") from exc
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(timezone.utc)

def category_for(title: str) -> str:
    t = title.casefold()
    # Notices are not the results themselves. Category is only a navigation label.
    rules = [
        ("earnings_call", ["transcript", "earnings call", "conference call", "audio recording"]),
        ("management_change", ["resignation", "cessation", "chief financial officer", "managing director", "appointment of director"]),
        ("litigation", ["litigation", "penalty", "regulatory order", "insolvency"]),
        ("results", ["financial results", "financial performance", "quarterly results"]),
        ("M&A", ["acquisition", "merger", "demerger", "joint venture"]),
        ("fund_raise", ["rights issue", "qip", "preferential allotment", "buyback", "commercial paper", "fund rais"]),
        ("insider_trading", ["insider trading", "promoter acquisition", "disposal of shares by promoter"]),
        ("pledging", ["pledging", "pledge of shares", "encumbrance"]),
        ("postal_ballot", ["postal ballot"]), ("agm_egm", ["annual general meeting", "extraordinary general meeting", "agm notice", "egm notice"]),
        ("dividend", ["dividend"]), ("bonus_split", ["bonus issue", "stock split"]),
        ("credit_rating", ["credit rating"]), ("capex", ["capital expenditure", "capacity expansion"]),
        ("investor_meetings", ["investor meet", "analyst meet"]),
        ("press_release", ["press release", "media release", "investor presentation"]),
    ]
    return next((category for category, words in rules if any(word in t for word in words)), "unclassified")
