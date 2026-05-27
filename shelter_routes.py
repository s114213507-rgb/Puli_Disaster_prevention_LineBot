"""
shelter_routes.py — 避難所登記系統的 Flask 路由

路由:
  GET  /register          → 填寫表單頁面
  POST /register          → 送出表單
  GET  /register/success  → 填寫成功頁
  GET  /admin/shelter      → 管理後台
  POST /admin/shelter/status → 更新狀態 (AJAX)
"""
import os
from flask import Blueprint, request, jsonify, render_template_string
import shelter_db as db

shelter_bp = Blueprint("shelter", __name__)

# ──────────────────────────────────────
# 民眾填寫表單
# ──────────────────────────────────────
@shelter_bp.route("/register", methods=["GET"])
def register_page():
    shelters = db.get_all_shelters()
    preselect_id = request.args.get("shelter_id", type=int) or 0
    return render_template_string(REGISTER_HTML, shelters=shelters, preselect_id=preselect_id)


@shelter_bp.route("/register", methods=["POST"])
def register_submit():
    try:
        data = {
            "shelter_id": int(request.form.get("shelter_id", 0)),
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "id_number": request.form.get("id_number", "").strip(),
            "emergency_contact_name": request.form.get("emergency_contact_name", "").strip(),
            "emergency_contact_phone": request.form.get("emergency_contact_phone", "").strip(),
            "num_people": int(request.form.get("num_people", 1)),
            "special_needs": request.form.get("special_needs", "").strip(),
            "status": request.form.get("status", "pre_registered"),
        }

        if not data["name"] or not data["phone"] or not data["shelter_id"]:
            shelters = db.get_all_shelters()
            return render_template_string(REGISTER_HTML, shelters=shelters, error="請填寫必要欄位（姓名、電話、避難所）")

        eid = db.register_evacuee(data)
        shelter = db.get_shelter_by_id(data["shelter_id"])
        return render_template_string(SUCCESS_HTML, evacuee_id=eid, shelter=shelter, name=data["name"])

    except Exception as e:
        shelters = db.get_all_shelters()
        return render_template_string(REGISTER_HTML, shelters=shelters, error=f"系統錯誤：{e}")


# ──────────────────────────────────────
# 管理後台
# ──────────────────────────────────────
@shelter_bp.route("/admin/shelter", methods=["GET"])
def admin_page():
    shelter_id = request.args.get("shelter_id", type=int)
    status_filter = request.args.get("status", "")
    shelters = db.get_all_shelters()
    evacuees = db.get_evacuees(shelter_id=shelter_id, status=status_filter or None)
    stats = db.get_stats(shelter_id=shelter_id)
    return render_template_string(
        ADMIN_HTML,
        shelters=shelters,
        evacuees=evacuees,
        stats=stats,
        selected_shelter=shelter_id,
        selected_status=status_filter,
    )


@shelter_bp.route("/admin/shelter/status", methods=["POST"])
def update_status():
    try:
        data = request.get_json()
        db.update_evacuee_status(int(data["id"]), data["status"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@shelter_bp.route("/admin/shelter/stats", methods=["GET"])
def get_stats_api():
    shelter_id = request.args.get("shelter_id", type=int)
    return jsonify(db.get_stats(shelter_id))


# ──────────────────────────────────────
# HTML 模板
# ──────────────────────────────────────

REGISTER_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>埔里鎮避難所登記</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'Noto Sans TC', sans-serif;
  background: #f0f2f5;
  min-height: 100vh;
}
.top-bar {
  background: linear-gradient(135deg, #1a5276, #2e86c1);
  color: #fff;
  padding: 20px 16px 24px;
  text-align: center;
}
.top-bar h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.top-bar p { font-size: 13px; opacity: 0.85; }
.card {
  background: #fff;
  margin: -12px 12px 16px;
  border-radius: 16px;
  padding: 24px 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #1a5276;
  margin: 20px 0 12px;
  padding-bottom: 6px;
  border-bottom: 2px solid #2e86c1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title:first-child { margin-top: 0; }
label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}
label .req { color: #e74c3c; margin-left: 2px; }
input, select, textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1.5px solid #ddd;
  border-radius: 10px;
  font-size: 16px;
  font-family: inherit;
  transition: border-color 0.2s;
  -webkit-appearance: none;
  background: #fafafa;
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: #2e86c1;
  background: #fff;
}
textarea { resize: vertical; min-height: 80px; }
.field { margin-bottom: 16px; }
.row { display: flex; gap: 12px; }
.row > .field { flex: 1; }
.status-group {
  display: flex; gap: 8px; margin-bottom: 16px;
}
.status-btn {
  flex: 1;
  padding: 12px 8px;
  border: 2px solid #ddd;
  border-radius: 10px;
  background: #fafafa;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
  font-weight: 500;
}
.status-btn.active {
  border-color: #2e86c1;
  background: #ebf5fb;
  color: #1a5276;
}
.status-btn .icon { font-size: 20px; display: block; margin-bottom: 4px; }
input[name="status"] { display: none; }
.submit-btn {
  width: 100%;
  padding: 16px;
  background: linear-gradient(135deg, #1a5276, #2e86c1);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 17px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  margin-top: 8px;
  transition: transform 0.1s;
}
.submit-btn:active { transform: scale(0.98); }
.error-msg {
  background: #fde8e8;
  color: #c0392b;
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 16px;
  font-size: 14px;
}
.shelter-info {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 10px 14px;
  margin-top: 8px;
  font-size: 13px;
  color: #555;
  display: none;
}
</style>
</head>
<body>
<div class="top-bar">
  <h1>📋 埔里鎮避難所登記</h1>
  <p>請填寫基本資料，協助我們掌握避難人數</p>
</div>

<form method="POST" action="/register" class="card">
  {% if error %}
  <div class="error-msg">⚠ {{ error }}</div>
  {% endif %}

  <div class="section-title">🏠 選擇避難所</div>
  <div class="field">
    <label>避難收容處所<span class="req">*</span></label>
    <select name="shelter_id" id="shelterSelect" required>
      <option value="">— 請選擇避難所 —</option>
      {% for s in shelters %}
      <option value="{{ s.id }}" data-addr="{{ s.address }}" data-cap="{{ s.capacity }}" data-village="{{ s.village }}"{% if preselect_id == s.id %} selected{% endif %}>
        {{ s.name }}（{{ s.village }}）
      </option>
      {% endfor %}
    </select>
    <div class="shelter-info" id="shelterInfo"></div>
  </div>

  <div class="section-title">👤 基本資料</div>
  <div class="field">
    <label>姓名<span class="req">*</span></label>
    <input type="text" name="name" placeholder="請輸入姓名" required>
  </div>
  <div class="row">
    <div class="field">
      <label>聯絡電話<span class="req">*</span></label>
      <input type="tel" name="phone" placeholder="0912-345678" required>
    </div>
    <div class="field">
      <label>身分證字號</label>
      <input type="text" name="id_number" placeholder="選填">
    </div>
  </div>
  <div class="field">
    <label>同行人數（含本人）</label>
    <input type="number" name="num_people" value="1" min="1" max="20">
  </div>

  <div class="section-title">📞 緊急聯絡人</div>
  <div class="row">
    <div class="field">
      <label>聯絡人姓名</label>
      <input type="text" name="emergency_contact_name" placeholder="選填">
    </div>
    <div class="field">
      <label>聯絡人電話</label>
      <input type="tel" name="emergency_contact_phone" placeholder="選填">
    </div>
  </div>

  <div class="section-title">📝 其他資訊</div>
  <div class="field">
    <label>特殊需求</label>
    <textarea name="special_needs" placeholder="如：行動不便、需要輪椅、慢性病用藥、嬰幼兒、寵物等"></textarea>
  </div>

  <div class="field">
    <label>目前狀態</label>
    <div class="status-group">
      <div class="status-btn active" data-val="pre_registered">
        <span class="icon">📝</span>預先報到
      </div>
      <div class="status-btn" data-val="checked_in">
        <span class="icon">✅</span>已到場
      </div>
    </div>
    <input type="hidden" name="status" value="pre_registered">
  </div>

  <button type="submit" class="submit-btn">送出登記</button>
</form>

<script>
document.querySelectorAll('.status-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.status-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('input[name="status"]').value = btn.dataset.val;
  });
});
document.getElementById('shelterSelect').addEventListener('change', function() {
  const opt = this.options[this.selectedIndex];
  const info = document.getElementById('shelterInfo');
  if (this.value) {
    info.style.display = 'block';
    info.innerHTML = '📍 ' + opt.dataset.addr + '｜可收容 ' + opt.dataset.cap + ' 人';
  } else {
    info.style.display = 'none';
  }
});
</script>
</body>
</html>"""


SUCCESS_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>登記成功</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'Noto Sans TC', sans-serif;
  background: #f0f2f5;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.success-card {
  background: #fff;
  border-radius: 20px;
  padding: 40px 28px;
  text-align: center;
  box-shadow: 0 2px 16px rgba(0,0,0,0.08);
  max-width: 400px;
  margin: 20px;
}
.check { font-size: 56px; margin-bottom: 16px; }
h1 { font-size: 22px; color: #1a5276; margin-bottom: 8px; }
.info { color: #555; font-size: 15px; line-height: 1.8; margin: 16px 0; }
.info strong { color: #1a5276; }
.id-badge {
  display: inline-block;
  background: #ebf5fb;
  color: #1a5276;
  font-size: 28px;
  font-weight: 700;
  padding: 12px 32px;
  border-radius: 12px;
  margin: 12px 0;
}
.note {
  font-size: 13px;
  color: #888;
  margin-top: 20px;
  line-height: 1.6;
}
.back-btn {
  display: inline-block;
  margin-top: 20px;
  padding: 12px 32px;
  background: #2e86c1;
  color: #fff;
  border-radius: 10px;
  text-decoration: none;
  font-weight: 500;
}
</style>
</head>
<body>
<div class="success-card">
  <div class="check">✅</div>
  <h1>登記成功！</h1>
  <div class="id-badge"># {{ evacuee_id }}</div>
  <div class="info">
    <strong>{{ name }}</strong> 您好<br>
    已登記至 <strong>{{ shelter.name }}</strong><br>
    📍 {{ shelter.address }}
  </div>
  <div class="note">
    請記住您的登記編號，到場時出示此畫面即可快速報到。<br>
    如有任何問題請撥打 (049)2984040
  </div>
  <a href="/register" class="back-btn">再登記一位</a>
</div>
</body>
</html>"""


ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>避難所管理後台</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Noto Sans TC', sans-serif; background: #f0f2f5; }
.header {
  background: #1a2332;
  color: #fff;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header h1 { font-size: 18px; font-weight: 700; }
.header .badge {
  background: #e74c3c;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  padding: 16px;
}
.stat-card {
  background: #fff;
  border-radius: 14px;
  padding: 16px;
  text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.stat-card .num {
  font-size: 28px;
  font-weight: 700;
  color: #1a5276;
}
.stat-card .label {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}
.stat-card.alert .num { color: #e74c3c; }
.filters {
  padding: 0 16px 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.filters select {
  padding: 10px 14px;
  border: 1.5px solid #ddd;
  border-radius: 10px;
  font-family: inherit;
  font-size: 14px;
  background: #fff;
  flex: 1;
  min-width: 140px;
}
.filters select:focus { outline:none; border-color:#2e86c1; }
.table-wrap {
  padding: 0 16px 20px;
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  font-size: 14px;
}
thead { background: #1a5276; color: #fff; }
th { padding: 12px 10px; text-align: left; font-weight: 500; white-space: nowrap; }
td { padding: 12px 10px; border-bottom: 1px solid #f0f0f0; }
tr:last-child td { border-bottom: none; }
tr:hover { background: #f7fafc; }
.badge-status {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}
.badge-pre { background: #fef9e7; color: #b7950b; }
.badge-in { background: #d5f5e3; color: #1e8449; }
.badge-left { background: #eaecee; color: #666; }
.special { color: #e74c3c; font-size: 13px; }
.empty {
  text-align: center;
  padding: 40px;
  color: #999;
  font-size: 15px;
}
.shelter-bar {
  padding: 4px 16px 16px;
  overflow-x: auto;
  white-space: nowrap;
}
.shelter-bar .chip {
  display: inline-block;
  background: #fff;
  border: 1.5px solid #ddd;
  border-radius: 20px;
  padding: 8px 14px;
  font-size: 13px;
  margin-right: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.shelter-bar .chip:hover { border-color: #2e86c1; }
.shelter-bar .chip.active {
  background: #1a5276;
  color: #fff;
  border-color: #1a5276;
}
.shelter-bar .chip .cnt {
  background: rgba(0,0,0,0.1);
  padding: 2px 6px;
  border-radius: 10px;
  margin-left: 4px;
  font-size: 11px;
}
.chip.active .cnt { background: rgba(255,255,255,0.25); }
select.status-select {
  padding: 4px 8px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
}
@media (max-width: 600px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  th, td { padding: 10px 6px; font-size: 13px; }
}
</style>
</head>
<body>

<div class="header">
  <h1>🛡️ 避難所管理後台</h1>
  <span class="badge">{{ stats.total_people }} 人</span>
</div>

<div class="stats-row">
  <div class="stat-card">
    <div class="num">{{ stats.total_registrations }}</div>
    <div class="label">登記筆數</div>
  </div>
  <div class="stat-card">
    <div class="num">{{ stats.total_people }}</div>
    <div class="label">總人數(含同行)</div>
  </div>
  <div class="stat-card">
    <div class="num">{{ stats.by_status.get('checked_in', {}).get('people', 0) }}</div>
    <div class="label">已到場</div>
  </div>
  <div class="stat-card">
    <div class="num">{{ stats.by_status.get('pre_registered', {}).get('people', 0) }}</div>
    <div class="label">預先報到</div>
  </div>
  <div class="stat-card alert">
    <div class="num">{{ stats.special_needs_count }}</div>
    <div class="label">特殊需求</div>
  </div>
</div>

<div class="shelter-bar">
  <a class="chip {% if not selected_shelter %}active{% endif %}" href="/admin/shelter">
    全部 <span class="cnt">{{ stats.total_registrations }}</span>
  </a>
  {% for s in stats.by_shelter %}
  {% if s.total_people %}
  <a class="chip {% if selected_shelter == s.id %}active{% endif %}"
     href="/admin/shelter?shelter_id={{ s.id }}{% if selected_status %}&status={{ selected_status }}{% endif %}">
    {{ s.name.split(' ')[-1] if ' ' in s.name else s.name }}
    <span class="cnt">{{ s.total_people or 0 }}</span>
  </a>
  {% endif %}
  {% endfor %}
</div>

<div class="filters">
  <select onchange="filterStatus(this.value)">
    <option value="">所有狀態</option>
    <option value="pre_registered" {% if selected_status=='pre_registered' %}selected{% endif %}>📝 預先報到</option>
    <option value="checked_in" {% if selected_status=='checked_in' %}selected{% endif %}>✅ 已到場</option>
    <option value="left" {% if selected_status=='left' %}selected{% endif %}>🚪 已離開</option>
  </select>
</div>

<div class="table-wrap">
{% if evacuees %}
<table>
  <thead>
    <tr>
      <th>#</th>
      <th>姓名</th>
      <th>電話</th>
      <th>避難所</th>
      <th>人數</th>
      <th>狀態</th>
      <th>特殊需求</th>
      <th>登記時間</th>
    </tr>
  </thead>
  <tbody>
    {% for e in evacuees %}
    <tr>
      <td>{{ e.id }}</td>
      <td><strong>{{ e.name }}</strong></td>
      <td>{{ e.phone }}</td>
      <td>{{ e.shelter_name }}</td>
      <td>{{ e.num_people }}</td>
      <td>
        <select class="status-select" data-id="{{ e.id }}" onchange="changeStatus(this)">
          <option value="pre_registered" {% if e.status=='pre_registered' %}selected{% endif %}>📝 預先報到</option>
          <option value="checked_in" {% if e.status=='checked_in' %}selected{% endif %}>✅ 已到場</option>
          <option value="left" {% if e.status=='left' %}selected{% endif %}>🚪 已離開</option>
        </select>
      </td>
      <td>{% if e.special_needs %}<span class="special">{{ e.special_needs }}</span>{% else %}-{% endif %}</td>
      <td>{{ e.created_at }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<div class="empty">目前沒有登記資料</div>
{% endif %}
</div>

<script>
function filterStatus(val) {
  const url = new URL(window.location);
  if (val) url.searchParams.set('status', val);
  else url.searchParams.delete('status');
  window.location = url;
}

function changeStatus(el) {
  fetch('/admin/shelter/status', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ id: el.dataset.id, status: el.value })
  }).then(r => r.json()).then(d => {
    if (!d.ok) alert('更新失敗');
  });
}
</script>
</body>
</html>"""