from __future__ import annotations

import os
import shutil
from pathlib import Path

source = Path("app/static/index.html")
dist = Path("dist")
dist.mkdir(exist_ok=True)
html = source.read_text(encoding="utf-8")
api_base = os.getenv("PUBLIC_API_BASE_URL", "")
html = html.replace('const API_BASE = "";', f'const API_BASE = "{api_base.rstrip("/")}";')

html = html.replace(
    '<main class="main"><div class="top"><h1 id="pageTitle">出品プラン</h1><span class="badge" id="connectionBadge">接続未確認</span></div>',
    '<main class="main"><div class="top"><h1 id="pageTitle">出品プラン</h1><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="badge" id="lastSyncBadge">在庫更新: 未実行</span><span class="badge" id="connectionBadge">接続未確認</span></div></div>',
)
html = html.replace(
    '<div class="card wide"><h2>どの商品を、何件出品するか</h2><div class="row"><div class="field"><label>商品ジャンル / 検索キーワード</label><input id="query" value="文房具" placeholder="例: 文房具、キッチン収納、USBハブ"></div>',
    '<div class="card wide"><h2>どの商品を、何件出品するか</h2><div class="row"><div class="field"><label>おすすめ低リスクカテゴリー</label><select id="presetCategory"><option value="">自由入力</option></select></div><div class="field"><label>商品ジャンル / 検索キーワード</label><input id="query" value="文房具" placeholder="例: 文房具、キッチン収納、USBハブ"></div>',
)
html = html.replace(
    '<div class="card"><h2>全面禁止</h2><div class="chips" id="denyGroups"></div></div><div class="card"><h2>要審査（自動では拒否）</h2><div class="chips" id="reviewGroups"></div></div>',
    '<div class="card"><h2>全面禁止 <span id="denyCount" class="help"></span></h2><div class="chips" id="denyGroups"></div></div><div class="card"><h2>要審査（自動では拒否） <span id="reviewCount" class="help"></span></h2><div class="chips" id="reviewGroups"></div></div><div class="card wide"><h2>市場別追加ルール</h2><div class="chips" id="marketGroups"></div><p class="help" id="policyMeta"></p></div>',
)
html = html.replace(
    "function renderPolicy(p){$('denyGroups').innerHTML=Object.keys(p.deny||{}).map(x=>`<span class=\"chip red\">${x}</span>`).join('');$('reviewGroups').innerHTML=Object.keys(p.review||{}).map(x=>`<span class=\"chip amber\">${x}</span>`).join('')}",
    "function renderPolicy(p){const deny=p.deny||{},review=p.review||{},markets=p.market_overrides||{};$('denyGroups').innerHTML=Object.keys(deny).map(x=>`<span class=\"chip red\">${x}</span>`).join('');$('reviewGroups').innerHTML=Object.keys(review).map(x=>`<span class=\"chip amber\">${x}</span>`).join('');$('denyCount').textContent=`${Object.keys(deny).length}分類 / ${Object.values(deny).reduce((n,a)=>n+a.length,0)}語`;$('reviewCount').textContent=`${Object.keys(review).length}分類 / ${Object.values(review).reduce((n,a)=>n+a.length,0)}語`;$('marketGroups').innerHTML=Object.entries(markets).map(([m,v])=>`<span class=\"chip\">${m}: 禁止${Object.keys(v.deny||{}).length} / 審査${Object.keys(v.review||{}).length}</span>`).join('');$('policyMeta').textContent=`ポリシー版 ${p.version||'-'} / 公式参照 ${p.sources?.length||0}件 / strict=${p.strict!==false}`;}",
)
html = html.replace(
    "await loadPolicy();await loadListings()",
    "await loadPolicy();await loadListings();await loadPresets();await loadSyncStatus()",
)
html = html.replace(
    "$('syncStatus').className='status ok';loadListings()",
    "$('syncStatus').className='status ok';loadListings();loadSyncStatus()",
)
extra_js = r'''async function loadPresets(){try{let p;if(base()){p=await api('/api/presets')}else{p={categories:[{label:'文房具・オフィス小物',query:'文房具 オフィス用品 ノート ペンケース ファイル'},{label:'デスク整理用品',query:'デスク収納 ケーブル整理 卓上収納'},{label:'家庭用収納・整理用品',query:'収納ボックス 収納ケース 整理用品'},{label:'キッチン収納・非電気小物',query:'キッチン収納 保存容器 調理小物 非電気'},{label:'手芸・クラフト用品',query:'手芸用品 クラフト用品 ビーズ 糸 工作'},{label:'旅行収納用品',query:'トラベルポーチ 旅行収納 パッキングキューブ'}]}}const sel=$('presetCategory');sel.innerHTML='<option value="">自由入力</option>'+p.categories.map(x=>`<option value="${x.query.replace(/"/g,'&quot;')}">${x.label}</option>`).join('');sel.onchange=()=>{if(sel.value)$('query').value=sel.value}}catch{}}
function formatSyncTime(value){if(!value)return '在庫更新: 未実行';const d=new Date(value);return '在庫更新: '+new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(d)}
async function loadSyncStatus(){try{if(!base())return;$('lastSyncBadge').textContent=formatSyncTime((await api('/api/sync/status')).last_inventory_update_at)}catch{$('lastSyncBadge').textContent='在庫更新: 取得失敗'}}
'''
html = html.replace(
    "$('apiBase').value=sessionStorage.getItem('mpApiBase')||'';",
    extra_js + "$('apiBase').value=sessionStorage.getItem('mpApiBase')||'';",
)
html = html.replace(
    "loadDemoPolicy();if(base())connect();else $('connectionBadge').textContent='Pages UI / API未接続';",
    "loadDemoPolicy();loadPresets();if(base())connect();else $('connectionBadge').textContent='Pages UI / API未接続';",
)

required_markers = ["lastSyncBadge", "presetCategory", "denyCount", "marketGroups"]
missing = [marker for marker in required_markers if marker not in html]
if missing:
    raise RuntimeError("Dashboard injection failed: " + ", ".join(missing))

(dist / "index.html").write_text(html, encoding="utf-8")
asset_source = Path("docs/assets/architecture-overview.svg")
if asset_source.exists():
    shutil.copy2(asset_source, dist / "architecture-overview.svg")
print(f"Built Cloudflare Pages site in {dist.resolve()}")
