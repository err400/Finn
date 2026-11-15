"""Interchangeable content-addressed stores. Only the backend sees storage credentials."""
import re
import hashlib
from pathlib import Path
from typing import Protocol
import httpx
from app.providers.contracts import ProviderError

class BlobStore(Protocol):
    def put(self, sha: str, content: bytes): ...
    def get(self, sha: str) -> bytes: ...

def object_key(sha):
    if not re.fullmatch(r'[a-f0-9]{64}', sha):
        raise ProviderError('invalid_blob_key', 'Invalid content-addressed source identifier')
    return sha

class LocalBlobStore:
    def __init__(self, folder: Path):
        self.folder=folder
        folder.mkdir(parents=True, exist_ok=True)
    def put(self, sha, content):
        target=self.folder/object_key(sha)
        if not target.exists():
            temporary=target.with_suffix('.tmp')
            temporary.write_bytes(content);temporary.replace(target)
    def get(self, sha):
        try:return (self.folder/object_key(sha)).read_bytes()
        except OSError as exc:raise ProviderError('cache_missing', 'Stored source file is missing') from exc

class SupabaseBlobStore:
    def __init__(self, settings, client=None):
        self.base=settings.storage_url.rstrip('/')+'/storage/v1/object/'
        self.bucket=settings.storage_bucket
        self.key=settings.storage_key.get_secret_value()
        self.client=client
    def request(self, method, sha, content=None):
        own=self.client is None
        client=self.client or httpx.Client(timeout=45, follow_redirects=False)
        try:
            headers={'apikey':self.key,'Content-Type':'application/octet-stream','x-upsert':'true'}
            if not self.key.startswith('sb_secret_'):
                headers['Authorization']='Bearer '+self.key
            url=self.base+('authenticated/' if method=='GET' else '')+self.bucket+'/'+object_key(sha)
            with client.stream(method,url,headers=headers,content=content) as response:
                if response.status_code not in {200,201}:
                    raise ProviderError('storage_unavailable','Private source storage request failed; no raw provider errors are exposed')
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>50*1024*1024:
                        raise ProviderError('storage_too_large','Stored source exceeds the download limit')
                return bytes(body)
        except httpx.HTTPError as exc:
            raise ProviderError('storage_unavailable','Private source storage is unreachable; previous metadata is retained') from exc
        finally:
            if own:client.close()
    def put(self,sha,content):
        if hashlib.sha256(content).hexdigest()!=object_key(sha):
            raise ProviderError('cache_corrupt','Source bytes do not match their content address')
        self.request('POST',sha,content)
    def get(self,sha):return self.request('GET',sha)

def blob_store(folder):
    from app.core.config import get_settings
    settings=get_settings()
    return SupabaseBlobStore(settings) if settings.storage_backend=='supabase' else LocalBlobStore(folder)
