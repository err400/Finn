"""Check the publishable source allowlist; never read or print private .env contents."""
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','node_modules','dist','__pycache__','.pytest_cache','.vercel','data','source-probes','submission-private'}
ROOT_FILES={'README.md','.gitignore','.env.example','render.yaml'}
TREES={'backend','frontend','docs','scripts','deploy','.github'}
PRIVATE_SUFFIXES={'.db','.db-shm','.db-wal','.pdf','.zip','.pyc','.tsbuildinfo','.pem','.key','.dump'}

def release_files():
    for path in ROOT.rglob('*'):
        rel=path.relative_to(ROOT)
        if any(p in EXCLUDED for p in rel.parts) or not path.is_file() or path.is_symlink():continue
        if rel.parts[0] not in TREES and str(rel) not in ROOT_FILES:continue
        if path.name.startswith('.env') and path.name!='.env.example':continue
        if path.suffix.lower() in PRIVATE_SUFFIXES or path.name.startswith('finn.db'):continue
        yield path

def main():
    failures=[];files=list(release_files())
    patterns=[r'\bsk-[A-Za-z0-9_-]{24,}',r'\bsb_secret_[A-Za-z0-9_-]{16,}',r'\bgh[pousr]_[A-Za-z0-9]{30,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}']
    for path in files:
        try:content=path.read_text()
        except UnicodeDecodeError:
            failures.append(str(path.relative_to(ROOT))+' unexpected binary');continue
        if any(re.search(p,content) for p in patterns):failures.append(str(path.relative_to(ROOT))+' possible embedded credential')
    if (ROOT/'.git').exists():
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        allowed={str(p.relative_to(ROOT)) for p in files}
        failures.extend(p+' is outside the publication allowlist' for p in tracked if p and p not in allowed)
    if failures:raise SystemExit('\n'.join(failures))
    print(f'Checked {len(files)} publishable text files; no matched credential patterns. Private files excluded. This is a heuristic scan, not a guarantee.')

if __name__=='__main__':main()
