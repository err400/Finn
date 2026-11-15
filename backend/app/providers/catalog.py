"""Reviewed exact primary-source URLs; never synthesize a document path from a ticker.
The adapter is intentionally replaceable with a licensed discovery provider. Unknown
companies return no candidates, not hardcoded analysis or guessed document URLs.
"""
import json
from datetime import date
from pathlib import Path
from app.providers.contracts import PrimaryDocument

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "fixtures" / "primary_sources.json"

class ReviewedCatalogProvider:
    def __init__(self, path: Path = DEFAULT_CATALOG): self.path = path
    def discover(self, ticker: str) -> list[PrimaryDocument]:
        rows = json.loads(self.path.read_text())
        result = []
        for row in rows:
            if row["ticker"] != ticker: continue
            row = dict(row)
            for key in ("published_date", "period_end", "event_date"):
                if row.get(key): row[key] = date.fromisoformat(row[key])
            result.append(PrimaryDocument(**row))
        return result
