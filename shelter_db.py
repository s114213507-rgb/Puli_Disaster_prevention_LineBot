"""
shelter_db.py — 避難所登記系統資料庫層（SQLite）

資料表:
  - shelters: 避難所清單（含經緯度）
  - evacuees: 避難者登記資料
"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.getenv("SHELTER_DB", "shelter.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────
# 避難所經緯度資料（埔里鎮 23 個避難所估算座標）
# 注意：這些是約略座標，實際部署時建議到 Google Maps 查正確位址後更新
# ──────────────────────────────────────
SHELTER_DATA = [
    # (name, address, village, capacity, disaster_types, lat, lng)
    ("一新里 水尾國小", "中正路511號", "一新里", 30, "風災,水災,震災,土石流", 23.99897284211857, 120.92963173311635),
    ("大湳里 中峰國小", "中山路一段228號", "大湳里", 60, "風災,水災,震災,土石流", 23.976317627932982, 120.98453506771808),
    ("水頭里 良善堂", "中正路121號", "水頭里", 30, "水災,震災,土石流", 23.943472123207883, 120.97967991004634),
    ("牛眠里 忠孝國小", "守城路28號", "牛眠里", 180, "水災,震災,土石流", 23.991938403186833, 120.98004482723817),
    ("北安里 北安里集會所", "北安路56號", "北安里", 30, "水災,震災,土石流", 23.969368703822063, 120.97167998121148),
    ("北門里 北門里集會所", "四維路26號", "北門里", 30, "水災,震災,土石流", 23.964431966411272, 120.9712318118956),
    ("史港里 史港國小", "獅子路9號", "史港里", 130, "水災,震災,土石流", 24.01266428493753, 120.9573027677189),
    ("合成里 太平社區活動中心", "西安路三段167巷23號", "合成里", 50, "水災,震災,土石流", 24.033589150490705, 120.92520775422594),
    ("同聲里 同聲里集會所", "光華街115號", "同聲里", 100, "水災,震災,土石流,海嘯", 23.959279644291215, 120.96520036586925),
    ("向善里 向善里集會所", "向善路75號", "向善里", 40, "水災,震災,土石流", 23.988965164511953, 120.92524545854822),
    ("成功里 成功里集會所", "種瓜路87-2號", "成功里", 50, "水災,震災,土石流", 23.95763816874458, 120.89464291004677),
    ("房里里 房里里集會所", "房里路25之5號", "房里里", 40, "水災,震災,土石流", 23.97914597887832, 120.94911577723786),
    ("東門里 東門里集會所", "四維路26號", "東門里", 30, "水災,震災,土石流", 23.96432624654355, 120.97123206956661),
    ("杷城里 杷城里集會所", "民有二街69號", "杷城里", 100, "水災,震災,土石流", 23.95883185807584, 120.97051745422432),
    ("枇杷里 枇杷里集會所", "和二街1號", "枇杷里", 80, "水災,震災,土石流", 23.95818803659373, 120.97639365422431),
    ("枇杷里 埔里高工", "中山路一段435號", "枇杷里", 150, "風災,水災,震災,土石流", 23.972468405549893, 120.97878988121143),
    ("南門里 南門里集會所", "南昌街115巷2號", "南門里", 60, "水災,震災,土石流", 23.96412203876404, 120.96696995422435),
    ("桃米里 桃米里集會所", "桃米巷48-1號", "桃米里", 50, "水災,震災,土石流", 23.942637401125076, 120.929717196553),
    ("桃米里 國立暨南國際大學", "大學路1號", "桃米里", 200, "水災,震災,土石流", 23.9507967036655, 120.92774883888204),
    ("泰安里 泰安里集會所", "民族二街58號", "泰安里", 50, "水災,震災,土石流", 23.96721813144435, 120.97556972538908),
    ("珠格里 珠格里集會所", "珠生路36-5號", "珠格里", 30, "水災,震災,土石流", 23.93819589231761, 120.95879706771728),
    ("福興里 福興里集會所", "福興路260號", "福興里", 50, "水災,震災,土石流", 24.00829638066008, 120.96896323798688),
    ("廣成里 廣成里社區活動中心", "西安路三段88號", "廣成里", 50, "水災,震災,土石流", 24.025012742804506, 120.94957620142159),
    ("蜈蚣里 蜈蚣里集會所", "蜈蚣路36號", "蜈蚣里", 500, "水災,震災,土石流", 23.976828305936447, 120.98974452546906),
    ("籃城里 籃城社區活動中心", "籃城路21號", "籃城里", 100, "水災,震災,土石流", 23.980842914167958, 120.9591522389628),
    ("麒麟里 麒麟國小", "武界路7號", "麒麟里", 280, "水災,震災,土石流", 23.976828305936447, 120.98974452546906),
    ("愛蘭里 愛蘭里集會所", "梅村路110號", "愛蘭里", 50, "水災,震災,土石流", 23.970806738152852, 120.9437673119753),
    ("薰化里 薰化里集會所", "育英街18號2樓", "薰化里", 25, "水災,震災,土石流", 24.64694594332023, 120.84383759665077),
    ("清新里 清新里集會所", "育英街18號1樓", "清新里", 500, "水災,震災,土石流", 24.64694594332023, 120.84383759665077),
    ("廣成里 受鎮宮", "西安路三段88號", "廣成里", 100, "水災,震災,土石流", 24.025067666015495, 120.94979058314124),
    ("福興里 利河伯社福基金會附設私立基督仁愛之家", "福興路146巷48號", "福興里", 30, "水災,震災,土石流", 24.007423588562087, 120.97546848129237),
    ("籃城里 埔里鎮公所清潔隊", "中正路1039號", "籃城里", 20, "風災,水災,震災,土石流", 23.993086869724266, 120.95504850883508),
    ("合成里 太平國小", "西安路三段167巷35號", "合成里", 70, "風災,水災,震災,土石流", 24.02659956808847, 120.92209101012847),
    ("清新里 育英國小", "育英街20號", 100, "清新里", "震災", 23.962595852465057, 120.96204178443215),
    ("北門里 埔里國中", "西安路一段193號", 80, "北門里", "震災", 23.96823552884854, 120.96844475486019),
    ("大城里 大成國中", "大城路169號", 150, "大城里", "震災", 23.972175087528278, 120.95262552161626),
    ("杷城里 南光國小", "中正路251號", 150, "杷城里", "震災", 23.960478215264068, 120.97035522108251),
    ("西門里 埔里國小", "西康路127號", 150, "西門里", "震災", 23.968897650738814, 120.9666037297212),
]


def init_db():
    """建立資料表並預填避難所清單"""
    with get_db() as conn:
        # 建立 shelters 表（含經緯度）
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS shelters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                address     TEXT NOT NULL,
                village     TEXT NOT NULL,
                capacity    INTEGER DEFAULT 0,
                disaster_types TEXT DEFAULT '',
                latitude    REAL DEFAULT 0,
                longitude   REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS evacuees (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter_id      INTEGER NOT NULL REFERENCES shelters(id),
                name            TEXT NOT NULL,
                phone           TEXT NOT NULL,
                id_number       TEXT DEFAULT '',
                emergency_contact_name  TEXT DEFAULT '',
                emergency_contact_phone TEXT DEFAULT '',
                num_people      INTEGER DEFAULT 1,
                special_needs   TEXT DEFAULT '',
                status          TEXT DEFAULT 'pre_registered'
                                CHECK(status IN ('pre_registered','checked_in','left')),
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_evacuees_shelter ON evacuees(shelter_id);
            CREATE INDEX IF NOT EXISTS idx_evacuees_status ON evacuees(status);
        """)

        # 既有資料庫遷移：補上經緯度欄位
        cursor = conn.execute("PRAGMA table_info(shelters)")
        cols = [r[1] for r in cursor.fetchall()]
        if "latitude" not in cols:
            conn.execute("ALTER TABLE shelters ADD COLUMN latitude REAL DEFAULT 0")
        if "longitude" not in cols:
            conn.execute("ALTER TABLE shelters ADD COLUMN longitude REAL DEFAULT 0")

        # 預填避難所
        existing = conn.execute("SELECT COUNT(*) FROM shelters").fetchone()[0]
        if existing == 0:
            conn.executemany(
                "INSERT INTO shelters (name, address, village, capacity, disaster_types, latitude, longitude) VALUES (?,?,?,?,?,?,?)",
                SHELTER_DATA,
            )
        else:
            # 既有資料庫補上經緯度
            for name, addr, village, cap, dt, lat, lng in SHELTER_DATA:
                conn.execute(
                    "UPDATE shelters SET latitude=?, longitude=? WHERE name=? AND (latitude=0 OR latitude IS NULL)",
                    (lat, lng, name),
                )


# ──────────────────────────────────────
# 避難所 CRUD
# ──────────────────────────────────────
def get_all_shelters():
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM shelters ORDER BY village, name"
        ).fetchall()]


def get_shelter_by_id(sid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM shelters WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None


def get_shelters_with_stats():
    """取得所有避難所 + 即時人數統計（給地圖用）"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                s.id, s.name, s.address, s.village, s.capacity, s.disaster_types,
                s.latitude, s.longitude,
                COALESCE(SUM(CASE WHEN e.status='checked_in' THEN e.num_people ELSE 0 END), 0) AS checked_in_people,
                COALESCE(SUM(CASE WHEN e.status='pre_registered' THEN e.num_people ELSE 0 END), 0) AS pre_registered_people,
                COUNT(e.id) AS total_registrations
            FROM shelters s
            LEFT JOIN evacuees e ON s.id = e.shelter_id AND e.status != 'left'
            GROUP BY s.id
            ORDER BY s.village
        """).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            # 計算占用率
            if d["capacity"] > 0:
                d["occupancy_rate"] = d["checked_in_people"] / d["capacity"]
            else:
                d["occupancy_rate"] = 0
            # 狀態分級
            rate = d["occupancy_rate"]
            if rate >= 1.0:
                d["status_label"] = "額滿"
                d["status_color"] = "red"
            elif rate >= 0.8:
                d["status_label"] = "即將額滿"
                d["status_color"] = "orange"
            elif d["checked_in_people"] > 0:
                d["status_label"] = "有空位"
                d["status_color"] = "green"
            else:
                d["status_label"] = "未開設"
                d["status_color"] = "gray"
            result.append(d)
        return result


# ──────────────────────────────────────
# 避難者 CRUD
# ──────────────────────────────────────
def register_evacuee(data: dict) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO evacuees
                (shelter_id, name, phone, id_number,
                 emergency_contact_name, emergency_contact_phone,
                 num_people, special_needs, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["shelter_id"],
            data["name"],
            data["phone"],
            data.get("id_number", ""),
            data.get("emergency_contact_name", ""),
            data.get("emergency_contact_phone", ""),
            data.get("num_people", 1),
            data.get("special_needs", ""),
            data.get("status", "pre_registered"),
            now, now,
        ))
        return cur.lastrowid


def update_evacuee_status(eid: int, status: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "UPDATE evacuees SET status=?, updated_at=? WHERE id=?",
            (status, now, eid),
        )


def get_evacuees(shelter_id=None, status=None):
    with get_db() as conn:
        sql = """
            SELECT e.*, s.name AS shelter_name, s.village
            FROM evacuees e JOIN shelters s ON e.shelter_id = s.id
            WHERE 1=1
        """
        params = []
        if shelter_id:
            sql += " AND e.shelter_id = ?"
            params.append(shelter_id)
        if status:
            sql += " AND e.status = ?"
            params.append(status)
        sql += " ORDER BY e.created_at DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_stats(shelter_id=None):
    with get_db() as conn:
        where = "WHERE e.shelter_id = ?" if shelter_id else ""
        params = [shelter_id] if shelter_id else []

        stats = {}

        rows = conn.execute(f"""
            SELECT e.status, COUNT(*) as cnt, SUM(e.num_people) as total_people
            FROM evacuees e {where}
            GROUP BY e.status
        """, params).fetchall()

        stats["by_status"] = {r["status"]: {"count": r["cnt"], "people": r["total_people"] or 0} for r in rows}
        stats["total_registrations"] = sum(r["cnt"] for r in rows)
        stats["total_people"] = sum(r["total_people"] or 0 for r in rows)

        sw = f"WHERE e.special_needs != '' AND e.special_needs IS NOT NULL"
        if shelter_id:
            sw += " AND e.shelter_id = ?"
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM evacuees e {sw}", params).fetchone()
        stats["special_needs_count"] = row["cnt"]

        rows = conn.execute(f"""
            SELECT s.id, s.name, s.village, s.capacity,
                   COUNT(e.id) as reg_count,
                   SUM(e.num_people) as total_people,
                   SUM(CASE WHEN e.status='checked_in' THEN e.num_people ELSE 0 END) as checked_in_people
            FROM shelters s
            LEFT JOIN evacuees e ON s.id = e.shelter_id
            GROUP BY s.id
            ORDER BY total_people DESC
        """).fetchall()
        stats["by_shelter"] = [dict(r) for r in rows]

        return stats


# 啟動時自動建表
init_db()