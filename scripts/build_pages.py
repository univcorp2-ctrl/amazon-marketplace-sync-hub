from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

source = Path("app/static/index.html")
dist = Path("dist")
dist.mkdir(exist_ok=True)
html = source.read_text(encoding="utf-8")
api_base = os.getenv("PUBLIC_API_BASE_URL", "").rstrip("/")
html = html.replace('const API_BASE = "";', f"const API_BASE = {json.dumps(api_base)};")
(dist / "index.html").write_text(html, encoding="utf-8")
asset_source = Path("docs/assets/architecture-overview.svg")
if asset_source.exists():
    shutil.copy2(asset_source, dist / "architecture-overview.svg")
print(f"Built Cloudflare Pages site in {dist.resolve()}")
