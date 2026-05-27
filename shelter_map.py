"""
shelter_map.py — 避難所地圖功能

路由:
  GET  /map                 → 地圖頁面（顯示所有避難所 + 使用者定位 + 找最近）
  GET  /api/shelters/map    → JSON API 提供避難所資料給地圖使用
"""
from flask import Blueprint, jsonify, render_template_string, request
import shelter_db as db

map_bp = Blueprint("map", __name__)


# ──────────────────────────────────────
# API：提供地圖用的避難所資料
# ──────────────────────────────────────
@map_bp.route("/api/shelters/map", methods=["GET"])
def shelters_api():
    shelters = db.get_shelters_with_stats()
    # 過濾掉沒有座標的
    shelters = [s for s in shelters if s.get("latitude") and s.get("longitude")]
    return jsonify({"shelters": shelters})


# ──────────────────────────────────────
# 地圖頁面
# ──────────────────────────────────────
@map_bp.route("/map", methods=["GET"])
def map_page():
    # 預先把支援的 shelter_id 從 query 拿出來（若使用者從別處跳轉指定避難所）
    highlight_id = request.args.get("shelter_id", type=int)
    return render_template_string(MAP_HTML, highlight_id=highlight_id or 0)


MAP_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>埔里鎮避難所地圖</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""/>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
html, body { height:100%; font-family:'Noto Sans TC', sans-serif; }

.top-bar {
  background: linear-gradient(135deg, #1a5276, #2e86c1);
  color:#fff; padding:14px 16px; display:flex; align-items:center; justify-content:space-between;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  z-index: 1000; position: relative;
}
.top-bar h1 { font-size:17px; font-weight:700; }
.top-bar .stat { font-size:13px; opacity:0.9; }

.legend {
  background:#fff; padding:8px 12px; display:flex; gap:14px;
  font-size:12px; border-bottom:1px solid #eee; overflow-x:auto;
  white-space:nowrap;
}
.legend .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; vertical-align:middle; }
.legend .green { background:#27ae60; }
.legend .orange { background:#e67e22; }
.legend .red { background:#c0392b; }
.legend .gray { background:#95a5a6; }
.legend .blue { background:#2980b9; }

#map { width:100%; height:calc(100vh - 105px); }

.locate-btn {
  position:fixed; bottom:80px; right:16px; z-index:1000;
  background:#fff; border:none; border-radius:50%;
  width:48px; height:48px;
  box-shadow:0 2px 10px rgba(0,0,0,0.2);
  font-size:22px; cursor:pointer;
  display:flex; align-items:center; justify-content:center;
}
.locate-btn:active { transform: scale(0.92); }

.nearest-btn {
  position:fixed; bottom:20px; left:16px; right:16px; z-index:1000;
  background: linear-gradient(135deg, #c0392b, #e74c3c);
  color:#fff; border:none; border-radius:30px;
  padding:14px 20px; font-size:15px; font-weight:700;
  box-shadow:0 4px 14px rgba(192,57,43,0.4);
  cursor:pointer; font-family:inherit;
}
.nearest-btn:active { transform: scale(0.98); }

.popup-card {
  font-family:'Noto Sans TC', sans-serif;
  min-width:200px;
}
.popup-card h3 {
  font-size:15px; font-weight:700; color:#1a5276;
  margin-bottom:4px;
}
.popup-card .address {
  font-size:12px; color:#666; margin-bottom:10px;
}
.popup-card .status-badge {
  display:inline-block; padding:3px 10px; border-radius:12px;
  font-size:12px; font-weight:500; margin-bottom:8px;
}
.popup-card .status-badge.green { background:#d5f5e3; color:#1e8449; }
.popup-card .status-badge.orange { background:#fdebd0; color:#a04000; }
.popup-card .status-badge.red { background:#fadbd8; color:#922b21; }
.popup-card .status-badge.gray { background:#eaecee; color:#5d6d7e; }
.popup-card .info-row {
  display:flex; justify-content:space-between;
  font-size:13px; color:#444; margin:4px 0;
  padding-bottom:4px; border-bottom:1px dotted #eee;
}
.popup-card .register-btn {
  display:block; margin-top:10px; padding:8px 12px;
  background:#1a5276; color:#fff; text-align:center;
  border-radius:6px; text-decoration:none; font-size:13px; font-weight:500;
}
.popup-card .distance {
  font-size:11px; color:#888; margin-top:6px; text-align:center;
}

.toast {
  position:fixed; top:80px; left:50%; transform:translateX(-50%);
  background:rgba(0,0,0,0.85); color:#fff;
  padding:10px 20px; border-radius:20px;
  font-size:13px; z-index:2000;
  opacity:0; transition:opacity 0.3s;
  pointer-events:none;
}
.toast.show { opacity:1; }

/* 自訂 marker pulse 動畫 */
.user-marker {
  background:#2980b9; border:3px solid #fff;
  border-radius:50%; width:18px; height:18px;
  box-shadow:0 0 0 4px rgba(41,128,185,0.3);
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0% { box-shadow:0 0 0 0 rgba(41,128,185,0.5); }
  70% { box-shadow:0 0 0 16px rgba(41,128,185,0); }
  100% { box-shadow:0 0 0 0 rgba(41,128,185,0); }
}
</style>
</head>
<body>

<div class="top-bar">
  <div>
    <h1>🛡️ 埔里鎮避難所地圖</h1>
    <div class="stat" id="shelterCount">載入中...</div>
  </div>
</div>

<div class="legend">
  <span><span class="dot blue"></span>您的位置</span>
  <span><span class="dot green"></span>有空位</span>
  <span><span class="dot orange"></span>即將額滿</span>
  <span><span class="dot red"></span>額滿</span>
  <span><span class="dot gray"></span>未開設</span>
</div>

<div id="map"></div>

<button class="locate-btn" onclick="locateUser()" title="重新定位">📍</button>
<button class="nearest-btn" onclick="findNearest()">🚶 找最近避難所</button>

<div class="toast" id="toast"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
        crossorigin=""></script>
<script>
const HIGHLIGHT_ID = {{ highlight_id }};

// 初始化地圖（中心點：埔里鎮中心）
const map = L.map('map', { zoomControl: true }).setView([23.9665, 120.9645], 13);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap',
  maxZoom: 19,
}).addTo(map);

let userMarker = null;
let userLatLng = null;
let shelterMarkers = [];
let allShelters = [];

const colorMap = {
  green:  '#27ae60',
  orange: '#e67e22',
  red:    '#c0392b',
  gray:   '#95a5a6',
};

function makeColoredIcon(color) {
  return L.divIcon({
    className: 'shelter-marker',
    html: `<div style="
      background:${colorMap[color] || colorMap.gray};
      width:28px; height:28px; border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      border:2px solid #fff;
      box-shadow:0 2px 6px rgba(0,0,0,0.3);
      display:flex; align-items:center; justify-content:center;
    "><span style="transform:rotate(45deg); color:#fff; font-size:14px; font-weight:700;">🏠</span></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
  });
}

function userIcon() {
  return L.divIcon({
    className: 'user-marker-wrap',
    html: '<div class="user-marker"></div>',
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function showToast(msg, ms = 2500) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms);
}

// Haversine 公式計算兩點距離（公尺）
function distance(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const toRad = (d) => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat/2)**2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
            Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function buildPopup(s, userDistance = null) {
  const occupied = s.checked_in_people + s.pre_registered_people;
  const capStr = s.capacity > 0 ? `${occupied} / ${s.capacity}` : `${occupied} / 不限`;
  const distStr = userDistance !== null
    ? `<div class="distance">距離您 ${userDistance < 1000 ? Math.round(userDistance) + ' 公尺' : (userDistance/1000).toFixed(1) + ' 公里'}</div>`
    : '';

  return `<div class="popup-card">
    <h3>${s.name}</h3>
    <div class="address">📍 ${s.address}</div>
    <span class="status-badge ${s.status_color}">${s.status_label}</span>
    <div class="info-row"><span>已報到</span><span><b>${s.checked_in_people}</b> 人</span></div>
    <div class="info-row"><span>預先報到</span><span><b>${s.pre_registered_people}</b> 人</span></div>
    <div class="info-row"><span>容量</span><span>${capStr}</span></div>
    ${distStr}
    <a class="register-btn" href="/register?shelter_id=${s.id}">📝 前往報到</a>
  </div>`;
}

async function loadShelters() {
  try {
    const res = await fetch('/api/shelters/map');
    const data = await res.json();
    allShelters = data.shelters;

    // 清除舊 marker
    shelterMarkers.forEach(m => map.removeLayer(m));
    shelterMarkers = [];

    let highlightTarget = null;

    allShelters.forEach(s => {
      const marker = L.marker([s.latitude, s.longitude], {
        icon: makeColoredIcon(s.status_color),
      }).addTo(map);
      marker.shelterData = s;
      marker.bindPopup(buildPopup(s));
      shelterMarkers.push(marker);

      if (s.id === HIGHLIGHT_ID) highlightTarget = marker;
    });

    document.getElementById('shelterCount').textContent =
      `共 ${allShelters.length} 個避難所｜${allShelters.filter(s => s.status_color !== 'gray').length} 個已開設`;

    if (highlightTarget) {
      map.setView([highlightTarget.shelterData.latitude, highlightTarget.shelterData.longitude], 16);
      highlightTarget.openPopup();
    }

    // 自動嘗試定位（不打擾用戶）
    autoLocate();
  } catch (e) {
    showToast('❌ 無法載入避難所資料');
    console.error(e);
  }
}

function autoLocate() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => placeUser(pos.coords.latitude, pos.coords.longitude, false),
    () => {},
    { enableHighAccuracy: true, timeout: 5000 }
  );
}

function locateUser() {
  if (!navigator.geolocation) {
    showToast('您的瀏覽器不支援定位功能');
    return;
  }
  showToast('📍 定位中...');
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      placeUser(pos.coords.latitude, pos.coords.longitude, true);
      showToast('✅ 定位成功');
    },
    (err) => {
      showToast('❌ 定位失敗，請開啟位置權限');
      console.error(err);
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

function placeUser(lat, lng, focus) {
  userLatLng = [lat, lng];
  if (userMarker) map.removeLayer(userMarker);
  userMarker = L.marker(userLatLng, { icon: userIcon(), zIndexOffset: 1000 })
    .addTo(map)
    .bindPopup('<b>📍 您的位置</b>');
  if (focus) map.setView(userLatLng, 15);
}

function findNearest() {
  if (!userLatLng) {
    showToast('📍 先取得您的位置...');
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        placeUser(pos.coords.latitude, pos.coords.longitude, false);
        doFindNearest();
      },
      () => showToast('❌ 無法取得您的位置')
    );
    return;
  }
  doFindNearest();
}

function doFindNearest() {
  // 只考慮有空位的避難所
  const candidates = allShelters.filter(s => s.status_color !== 'red');
  if (candidates.length === 0) {
    showToast('❌ 目前沒有可用的避難所');
    return;
  }

  // 計算每個避難所距離
  const withDist = candidates.map(s => ({
    ...s,
    distance: distance(userLatLng[0], userLatLng[1], s.latitude, s.longitude),
  })).sort((a, b) => a.distance - b.distance);

  const nearest = withDist[0];

  // 移動地圖並打開該避難所的 popup
  map.setView([nearest.latitude, nearest.longitude], 16);

  // 找到對應的 marker 並打開 popup（含距離）
  const marker = shelterMarkers.find(m => m.shelterData.id === nearest.id);
  if (marker) {
    marker.setPopupContent(buildPopup(nearest, nearest.distance));
    marker.openPopup();
  }

  const distLabel = nearest.distance < 1000
    ? `${Math.round(nearest.distance)} 公尺`
    : `${(nearest.distance / 1000).toFixed(1)} 公里`;
  showToast(`🚶 最近：${nearest.name}（${distLabel}）`, 3500);
}

// 啟動
loadShelters();

// 每 30 秒自動更新一次資料
setInterval(loadShelters, 30000);
</script>

</body>
</html>"""
