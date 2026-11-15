"""Public synthetic demo budgets, with a loopback-only local mode."""
import ipaddress
import threading
import time
from collections import deque
from fastapi import HTTPException, Request
from app.core.config import get_settings

_lock = threading.Lock()
_windows: dict[str, deque] = {}

def check_budget(key: str, limit: int, seconds: int):
    now = time.monotonic()
    with _lock:
        window = _windows.setdefault(key, deque())
        while window and window[0] <= now - seconds:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(429, 'Public demo request budget reached; retry later.', headers={'Retry-After': str(seconds)})
        window.append(now)

def workspace_access(request: Request):
    settings = get_settings()
    origin = request.headers.get('origin')
    if origin and origin not in settings.cors_origins:
        raise HTTPException(403, 'This browser origin is not allowed')
    if settings.access_mode == 'local':
        try:
            local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError):
            local = False
        if not local:
            raise HTTPException(403, 'Source datasets are restricted to local personal use; public redistribution is not enabled')
        return
    # Shared budgets are deliberate: one process, one synthetic public demo workspace.
    check_budget('all', 600, 60)
    if request.method != 'GET':
        check_budget('writes', 60, 3600)
        if request.url.path.endswith('/research'):
            check_budget('research', 20, 3600)
        elif request.url.path.endswith('/refresh'):
            check_budget('refresh', 12, 3600)
