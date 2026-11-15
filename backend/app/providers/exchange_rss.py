"""Only published RSS feeds. These are recent windows, not historical coverage APIs."""
import hashlib
import re
from xml.etree import ElementTree as ET
from app.providers.contracts import Fetcher, FilingBatch, FilingCandidate, ProviderError
from app.services.normalization import canonical_url, filing_datetime

FEEDS = {
    "nse_rss": "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",
    "bse_rss": "https://www.bseindia.com/data/xml/announcements.xml",
}

class ExchangeRssProvider:
    def __init__(self, name: str, fetcher: Fetcher):
        self.name, self.fetcher = name, fetcher
    def latest(self, force: bool = False) -> FilingBatch:
        payload = self.fetcher.get(FEEDS[self.name], 5 * 60, force)
        if b"<!DOCTYPE" in payload.body.upper() or b"<!ENTITY" in payload.body.upper():
            raise ProviderError("invalid_xml", "RSS entity declarations are unsupported")
        try: root = ET.fromstring(payload.body)
        except ET.ParseError as exc: raise ProviderError("invalid_xml", "Source did not return valid RSS XML") from exc
        if root.tag != "rss" or root.find("channel") is None:
            raise ProviderError("invalid_xml", "Source returned a page instead of RSS")
        items, rejected = [], 0
        for item in root.findall("./channel/item"):
            try:
                title = (item.findtext("title") or "").strip()
                description = (item.findtext("description") or "").strip()
                link = canonical_url(item.findtext("link") or "")
                raw_date = (item.findtext("pubDate") or "").strip()
                if not title or not description: raise ValueError("Missing RSS fields")
                code = (item.findtext("scripcode") or "").strip() or None
                name = re.sub(r"\s*\(\d{6}\)\s*$", "", title) if self.name == "bse_rss" else title
                items.append(FilingCandidate(name, description, link, raw_date, filing_datetime(raw_date), code))
            except (ProviderError, ValueError): rejected += 1
        return FilingBatch(items, payload, rejected)
