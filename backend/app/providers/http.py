"""Bounded, allowlisted, cached HTTP access. No browser impersonation or challenge bypass."""
import hashlib
import json
from xml.etree import ElementTree as ET
import threading
import time
import socket
import ipaddress
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.ingestion import RawSnapshot, FetchCache, HostThrottle
from app.providers.contracts import Payload, ProviderError
from app.providers.storage import blob_store
from app.services.normalization import canonical_url, utc

_LOCK = threading.RLock()
ALLOWED = {
    "www.pidilite.com": ("/content/dam/pidilitecorporatewebsite/",),
    "query1.finance.yahoo.com": ("/v8/finance/chart/",),
    "nsearchives.nseindia.com": ("/content/RSS/", "/corporate/"),
    "www.bseindia.com": ("/data/xml/announcements.xml", "/xml-data/corpfiling/"),
    "www.tcs.com": ("/content/dam/tcs/investor-relations/", "/content/dam/tcs/pdf/discover-tcs/investor-relations/"),
    "www.ril.com": ("/sites/default/files/", "/ar2024-25/"),
    "rilstaticasset.akamaized.net": ("/sites/default/files/",),
}

def validate_source_url(url: str) -> str:
    url = canonical_url(url)
    parts = urlsplit(url)
    if parts.hostname not in ALLOWED:
        from app.core.config import get_settings
        if parts.hostname not in get_settings().reviewed_primary_hosts or "." not in parts.hostname:
            raise ProviderError("source_not_allowed", "URL is outside the reviewed source allowlist")
        try:
            addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise ProviderError("unsafe_url", "Reviewed primary-source host must resolve only to public addresses")
        except socket.gaierror as exc:
            raise ProviderError("network_error", "Reviewed primary-source host could not be resolved") from exc
        if not parts.path.lower().endswith(".pdf"):
            raise ProviderError("source_not_allowed", "Additional reviewed hosts allow exact PDF retrieval, not crawling")
    elif not any(parts.path.startswith(p) for p in ALLOWED[parts.hostname]):
        raise ProviderError("source_not_allowed", "URL is outside the reviewed source allowlist")
    return url

class CachedHttpFetcher:
    def __init__(self, db: Session, data_dir: Path, *, client: httpx.Client | None = None,
                 min_interval: float = 2.0, attempts: int = 2, clock=None, sleeper=time.sleep):
        self.db, self.data_dir = db, Path(data_dir)
        self.client = client
        self.min_interval, self.attempts = min_interval, attempts
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper
        self.blobs = self.data_dir / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.store = blob_store(self.blobs)

    def body(self, snapshot: RawSnapshot) -> bytes:
        content = self.store.get(snapshot.sha256)
        if hashlib.sha256(content).hexdigest() != snapshot.sha256:
            raise ProviderError("cache_corrupt", "Stored source file failed its integrity check")
        return content

    def capture(self, url: str, final_url: str, body: bytes, headers: dict, fetched_at: datetime) -> RawSnapshot:
        """Import an actually retrieved capture, retaining its original retrieval timestamp."""
        url, final_url = validate_source_url(url), validate_source_url(final_url)
        sha = hashlib.sha256(body).hexdigest()
        snapshot = self.db.scalar(select(RawSnapshot).where(RawSnapshot.url == url, RawSnapshot.sha256 == sha))
        if snapshot is None:
            snapshot = RawSnapshot(url=url, final_url=final_url, sha256=sha, media_type=headers.get("content-type", "application/octet-stream").split(";")[0],
                                   byte_count=len(body), fetched_at=fetched_at,
                                   response_headers={k: v for k, v in headers.items() if k.lower() in {"content-type", "etag", "last-modified"}})
            self.db.add(snapshot)
            self.db.flush()
        self.store.put(sha, body)
        return snapshot

    def _payload(self, snapshot, status, warning=None):
        return Payload(snapshot.id, self.body(snapshot), snapshot.final_url, snapshot.sha256, utc(snapshot.fetched_at), status, warning)

    def get(self, url: str, ttl_seconds: int, force: bool = False) -> Payload:
        with _LOCK:
            return self._get(url, ttl_seconds, force)

    def _get(self, url: str, ttl_seconds: int, force: bool) -> Payload:
        url = validate_source_url(url)
        cache = self.db.get(FetchCache, url)
        if cache is None:
            cache = FetchCache(url=url)
            self.db.add(cache)
            self.db.flush()
        snapshot = self.db.get(RawSnapshot, cache.snapshot_id) if cache.snapshot_id else None
        if snapshot and not force and cache.expires_at and utc(cache.expires_at) > self.clock():
            return self._payload(snapshot, "stale" if cache.last_error else "cache", cache.last_error)
        if cache.last_error and cache.last_attempt_at and (self.clock()-utc(cache.last_attempt_at)).total_seconds()<60:
            if snapshot:return self._payload(snapshot,"stale",cache.last_error)
            raise ProviderError("cooldown","Source retry is temporarily deferred after a failed request")
        cache.last_attempt_at = self.clock()
        error = ProviderError("network_error", "Source request failed")
        own_client = self.client is None
        client = self.client or httpx.Client(timeout=httpx.Timeout(20, connect=8), headers={"User-Agent": "FINN-prototype/0.2 (personal educational research)"}, follow_redirects=False)
        try:
            for attempt in range(self.attempts):
                try:
                    current = url
                    headers = {}
                    if snapshot:
                        if snapshot.response_headers.get("etag"): headers["If-None-Match"] = snapshot.response_headers["etag"]
                        if snapshot.response_headers.get("last-modified"): headers["If-Modified-Since"] = snapshot.response_headers["last-modified"]
                    for redirects in range(4):
                        host = urlsplit(current).hostname
                        throttle = self.db.get(HostThrottle, host)
                        if throttle:
                            wait = (utc(throttle.next_allowed_at) - self.clock()).total_seconds()
                            if wait > 5:
                                raise ProviderError("cooldown", "Source is cooling down; retry later")
                            if wait > 0: self.sleeper(wait)
                        else:
                            throttle = HostThrottle(host=host, next_allowed_at=self.clock())
                            self.db.add(throttle)
                        throttle.next_allowed_at = self.clock() + timedelta(seconds=self.min_interval)
                        self.db.flush()
                        with client.stream("GET", current, headers=headers) as response:
                            if response.status_code in {301,302,303,307,308}:
                                current = validate_source_url(urljoin(current, response.headers.get("location", "")))
                                continue
                            if response.status_code == 429:
                                retry = response.headers.get("retry-after", "60")
                                try: seconds = max(1, int(retry))
                                except ValueError:
                                    try: seconds = max(1, (utc(parsedate_to_datetime(retry)) - self.clock()).total_seconds())
                                    except (TypeError, ValueError): seconds = 60
                                throttle.next_allowed_at = self.clock() + timedelta(seconds=seconds)
                                raise ProviderError("rate_limited", "Source returned HTTP 429; Retry-After cooldown is active")
                            if response.status_code == 304 and snapshot:
                                cache.last_checked_at = self.clock()
                                cache.expires_at = self.clock() + timedelta(seconds=ttl_seconds)
                                cache.last_error = None
                                self.db.commit()
                                return self._payload(snapshot, "revalidated")
                            if response.status_code != 200:
                                raise ProviderError("http_error", f"Source returned HTTP {response.status_code}")
                            body = bytearray()
                            for chunk in response.iter_bytes():
                                body.extend(chunk)
                                if len(body) > 50 * 1024 * 1024:
                                    raise ProviderError("too_large", "Source exceeds the 50 MiB download limit")
                            if not body: raise ProviderError("empty_response", "Source returned an empty response")
                            raw = bytes(body)
                            path = urlsplit(current).path.lower()
                            if path.endswith(".pdf") and not raw.startswith(b"%PDF-"):
                                raise ProviderError("invalid_content", "Source returned a challenge/page instead of a PDF")
                            if path.endswith(".xml"):
                                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                                    raise ProviderError("invalid_content", "RSS entity declarations are unsupported")
                                try:
                                    root = ET.fromstring(raw)
                                    if root.tag != "rss": raise ValueError("Not RSS")
                                except (ET.ParseError, ValueError) as exc:
                                    raise ProviderError("invalid_content", "Source returned a page instead of RSS XML") from exc
                            if urlsplit(current).hostname == "query1.finance.yahoo.com":
                                try:
                                    chart = json.loads(raw)["chart"]
                                    if chart.get("error") or not chart.get("result"): raise ValueError("No chart")
                                except (ValueError, KeyError, TypeError) as exc:
                                    raise ProviderError("invalid_content", "Yahoo returned an error or a page instead of price data") from exc
                            snapshot = self.capture(url, current, raw, dict(response.headers), self.clock())
                            cache.snapshot_id = snapshot.id
                            cache.last_checked_at = self.clock()
                            cache.expires_at = self.clock() + timedelta(seconds=ttl_seconds)
                            cache.last_error = None
                            self.db.commit()
                            return self._payload(snapshot, "network")
                    raise ProviderError("redirect_limit", "Source exceeded the redirect limit")
                except httpx.HTTPError as exc:
                    error = ProviderError("network_error", f"Source request failed ({type(exc).__name__})")
                except ProviderError as exc:
                    error = exc
                if error.code in {"rate_limited", "cooldown", "source_not_allowed", "unsafe_url", "too_large", "redirect_limit", "invalid_content"}: break
                if error.code == "http_error" and "HTTP 5" not in str(error): break
                if attempt + 1 < self.attempts: self.sleeper(2 ** attempt)
            cache.last_error = f"{error.code}: {error}"
            cache.last_attempt_at = self.clock()
            self.db.commit()
            if snapshot:
                return self._payload(snapshot, "stale", cache.last_error)
            raise error
        finally:
            if own_client: client.close()
