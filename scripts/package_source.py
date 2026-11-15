"""Create a source-only submission ZIP, excluding databases, PDFs, history and secrets."""
from pathlib import Path
import zipfile
from check_release import ROOT,release_files,main as check
check()
out=ROOT/'submission-private'/'FINN-source.zip';out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
    for file in release_files():archive.write(file,file.relative_to(ROOT))
print('Created submission-private/FINN-source.zip (source only; chat history is a separate deliverable)')
