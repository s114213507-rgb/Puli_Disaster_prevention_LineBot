"""
news_fetcher.py — 即時災害資訊爬取模組（全台版）

資料來源:
  1. 中央氣象署 Open Data — 最近地震報告（全台）
  2. 中央氣象署 Open Data — 天氣警特報（全台）
  3. Google News RSS — 台灣災害相關新聞

使用前:
  到 https://opendata.cwa.gov.tw/ 註冊取得 API 授權碼
  在 .env 加上 CWA_API_KEY=你的授權碼
"""
import os
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

log = logging.getLogger(__name__)

CWA_API_KEY = os.getenv("CWA_API_KEY", "")
REQUEST_TIMEOUT = 10


def fetch_earthquakes(limit=5):
    if not CWA_API_KEY:
        return []
    try:
        url = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"
            f"?Authorization={CWA_API_KEY}&limit={limit}&format=JSON"
        )
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        results = []
        for eq in data.get("records", {}).get("Earthquake", []):
            info = eq.get("EarthquakeInfo", {})
            epicenter = info.get("Epicenter", {})
            mag = info.get("EarthquakeMagnitude", {})
            results.append({
                "type": "earthquake",
                "time": info.get("OriginTime", ""),
                "location": epicenter.get("Location", ""),
                "magnitude": mag.get("MagnitudeValue", ""),
                "depth": info.get("FocalDepth", ""),
                "url": eq.get("Web", "") or eq.get("ReportImageURI", ""),
                "content": eq.get("ReportContent", ""),
            })
        return results
    except Exception as e:
        log.error(f"地震資料取得失敗: {e}")
        return []


def fetch_weather_warnings():
    if not CWA_API_KEY:
        return []
    try:
        url = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-002"
            f"?Authorization={CWA_API_KEY}&format=JSON"
        )
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        results = []
        for record in data.get("records", {}).get("record", []):
            content_text = ""
            contents = record.get("contents", {})
            if isinstance(contents, dict):
                c = contents.get("content", {})
                content_text = c.get("contentText", "") if isinstance(c, dict) else ""

            hazards = record.get("hazardConditions", {}).get("hazards", {})
            if isinstance(hazards, dict):
                hazards = [hazards]
            if not isinstance(hazards, list):
                continue
            for hazard in hazards:
                info_list = hazard.get("info", {})
                if isinstance(info_list, dict):
                    info_list = [info_list]
                for info in info_list:
                    areas = info.get("affectedAreas", {}).get("location", [])
                    if isinstance(areas, dict):
                        areas = [areas]
                    area_names = [a.get("locationName", "") for a in areas if isinstance(a, dict)]
                    results.append({
                        "type": "warning",
                        "title": f"{info.get('phenomena','')}{info.get('significance','')}",
                        "areas": ", ".join(area_names[:8]) + ("…" if len(area_names) > 8 else ""),
                        "content": content_text[:120],
                        "time": record.get("datasetInfo", {}).get("issueTime", ""),
                    })
        return results
    except Exception as e:
        log.error(f"警特報取得失敗: {e}")
        return []


def fetch_disaster_news(limit=8):
    all_results = []
    seen = set()
    queries = ["台灣+地震", "台灣+颱風+水災+淹水+土石流", "台灣+災害+災情"]
    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            r = requests.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                source = item.findtext("source", "")
                key = title[:20]
                if key in seen:
                    continue
                seen.add(key)
                all_results.append({"type": "news", "title": title, "url": link, "source": source, "time": pub_date})
        except Exception as e:
            log.error(f"新聞取得失敗 ({q}): {e}")
    return all_results[:limit]


def get_latest_disaster_info() -> dict:
    warnings = fetch_weather_warnings()
    earthquakes = fetch_earthquakes(limit=5)
    news = fetch_disaster_news(limit=6)
    now = datetime.now().strftime("%m/%d %H:%M")

    # ── 純文字版（備用 fallback）──
    lines = [f"📡 最新防災資訊（{now}）\n"]
    if warnings:
        lines.append("🔴【生效中警特報】")
        for w in warnings[:3]:
            lines.append(f"⚠️ {w['title']}｜{w['areas']}")
        lines.append("")
    if earthquakes:
        lines.append("🔶【最近地震】")
        for eq in earthquakes[:3]:
            t = eq["time"][5:16] if len(eq["time"]) > 16 else eq["time"]
            lines.append(f"📍 {t}｜M{eq['magnitude']}｜{eq['location']}")
        lines.append("")
    if news:
        lines.append("📰【近期災害新聞】")
        for n in news[:5]:
            lines.append(f"• {n['title']}")
    if not CWA_API_KEY:
        lines.append("\n💡 在 .env 設定 CWA_API_KEY 可取得地震及警特報")
    text = "\n".join(lines).strip()

    # ── Flex Carousel ──
    bubbles = []

    # 卡 1：警特報
    if warnings:
        body = [{"type": "text", "text": "🔴 生效中警特報", "weight": "bold", "size": "md", "color": "#c0392b"}]
        for w in warnings[:4]:
            body.append({"type": "separator", "margin": "md"})
            body.append({"type": "text", "text": f"⚠️ {w['title']}", "size": "sm", "weight": "bold", "margin": "md", "wrap": True})
            if w["areas"]:
                body.append({"type": "text", "text": w["areas"], "size": "xs", "color": "#888888", "wrap": True})
        bubbles.append({
            "type": "bubble", "size": "kilo",
            "header": _header("⚠️ 警特報", "#c0392b"),
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body},
        })

    # 卡 2：地震
    if earthquakes:
        body = [{"type": "text", "text": "🔶 最近地震", "weight": "bold", "size": "md"}]
        for eq in earthquakes[:4]:
            t = eq["time"][5:16] if len(eq["time"]) > 16 else eq["time"]
            loc = eq["location"][:25] + ("…" if len(eq["location"]) > 25 else "")
            body.append({"type": "separator", "margin": "md"})
            body.append({"type": "text", "text": f"M{eq['magnitude']}｜{t}", "size": "sm", "weight": "bold", "margin": "md"})
            body.append({"type": "text", "text": loc, "size": "xs", "color": "#666666", "wrap": True})

        bubble = {
            "type": "bubble", "size": "kilo",
            "header": _header("🔶 地震", "#e67e22"),
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body},
        }
        first_url = next((eq["url"] for eq in earthquakes if eq.get("url")), "")
        if first_url:
            bubble["footer"] = _footer_buttons([("查看完整報告", first_url)])
        bubbles.append(bubble)

    # 卡 3+：新聞（每 2 則一張）
    for i in range(0, len(news[:6]), 2):
        batch = news[i:i + 2]
        body = [{"type": "text", "text": "📰 災害新聞", "weight": "bold", "size": "md"}]
        btns = []
        for j, n in enumerate(batch):
            title = n["title"][:45] + ("…" if len(n["title"]) > 45 else "")
            source = (n.get("source") or "")[:12]
            body.append({"type": "separator", "margin": "md"})
            body.append({"type": "text", "text": title, "size": "sm", "wrap": True, "margin": "md"})
            if source:
                body.append({"type": "text", "text": f"— {source}", "size": "xs", "color": "#999999"})
            if n.get("url"):
                btns.append((f"閱讀全文 {i + j + 1}", n["url"]))

        bubble = {
            "type": "bubble", "size": "kilo",
            "header": _header("📰 新聞", "#2c3e50"),
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body},
        }
        if btns:
            bubble["footer"] = _footer_buttons(btns)
        bubbles.append(bubble)

    if not bubbles:
        return {"text": text, "flex": None}

    return {"text": text, "flex": {"type": "carousel", "contents": bubbles[:10]}}


# ── helpers ──
def _header(text, color):
    return {"type": "box", "layout": "vertical", "backgroundColor": color, "paddingAll": "14px",
            "contents": [{"type": "text", "text": text, "color": "#ffffff", "weight": "bold", "size": "md"}]}

def _footer_buttons(items):
    return {"type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [{"type": "button", "style": "link", "height": "sm",
                          "action": {"type": "uri", "label": label, "uri": url}} for label, url in items]}