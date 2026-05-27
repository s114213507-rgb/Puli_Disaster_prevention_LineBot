import os
import logging
from flask import Flask, request
from dotenv import load_dotenv
 
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    ImageSendMessage,
    FlexSendMessage,
)
 
from rag_core import rag_answer
from news_fetcher import get_latest_disaster_info
 
load_dotenv()
 
# ──────────────────────────────────────
# LINE Bot 憑證（一律從 .env 讀取，不在程式碼中保留任何機密）
# ──────────────────────────────────────
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "")
 
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "500"))
 
# ──────────────────────────────────────
# 啟動前檢查：缺少必要設定就直接停止，避免帶著空憑證啟動
# ──────────────────────────────────────
_missing = []
if not LINE_CHANNEL_ACCESS_TOKEN:
    _missing.append("LINE_CHANNEL_ACCESS_TOKEN")
if not LINE_CHANNEL_SECRET:
    _missing.append("LINE_CHANNEL_SECRET")
if not BASE_URL:
    _missing.append("BASE_URL")
 
if _missing:
    raise SystemExit(
        "❌ 缺少必要環境變數：" + "、".join(_missing) +
        "\n請複製 .env.example 為 .env 並填入正確的值後再啟動。"
    )
 
# ──────────────────────────────────────
# 初始化
# ──────────────────────────────────────
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
 
app = Flask(__name__, static_url_path="/static", static_folder="static")
 
# 註冊避難所登記系統路由
from shelter_routes import shelter_bp
from shelter_map import map_bp
app.register_blueprint(shelter_bp)
app.register_blueprint(map_bp)
 
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)
 
 
# ──────────────────────────────────────
# Flex Citation 組裝
# ──────────────────────────────────────
def build_citation_flex(citations):
    if not citations:
        return None
 
    bubbles = []
    for c in citations[:3]:
        title = c.get("title") or "原始文件"
        page = c.get("page")
        section = c.get("section") or ""
        url = c.get("url") or ""
 
        if not url:
            continue
 
        page_text = f"第 {page} 頁" if isinstance(page, int) and page > 0 else "頁碼未知"
        sec_text = section if section else "（未提供章節）"
 
        bubble = {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "📌 原始文件引用",
                        "weight": "bold",
                        "size": "lg",
                    },
                    {
                        "type": "text",
                        "text": title,
                        "wrap": True,
                        "size": "sm",
                        "color": "#555555",
                    },
                    {
                        "type": "text",
                        "text": page_text,
                        "weight": "bold",
                        "size": "md",
                    },
                    {
                        "type": "text",
                        "text": sec_text,
                        "wrap": True,
                        "size": "sm",
                        "color": "#666666",
                    },
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "查看原始頁面",
                            "uri": url,
                        },
                    }
                ],
            },
        }
        bubbles.append(bubble)
 
    if not bubbles:
        return None
 
    return FlexSendMessage(
        alt_text="原始文件引用",
        contents={"type": "carousel", "contents": bubbles},
    )
 
 
def image_ref_to_url(img_ref: str) -> str:
    if img_ref.lower().endswith((".png", ".jpg", ".jpeg")):
        return f"{BASE_URL}/static/images/{img_ref}"
    return f"{BASE_URL}/static/images/{img_ref}.jpg"
 
 
# ──────────────────────────────────────
# Webhook
# ──────────────────────────────────────
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
 
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Bad Request", 400
    except Exception as e:
        app.logger.error(f"Webhook error: {e}")
        return "OK", 200
 
    return "OK", 200
 
 
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_query = (event.message.text or "").strip()
 
        if not user_query:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入問題，我可以協助查詢防災手冊內容。"),
            )
            return
 
        # 輸入長度限制
        if len(user_query) > MAX_QUERY_LENGTH:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"訊息太長了，請控制在 {MAX_QUERY_LENGTH} 字以內。"),
            )
            return
 
        # ── 關鍵字攔截：避難所登記 ──
        SHELTER_KEYWORDS = ["填寫避難所資料", "避難所登記", "避難登記", "避難所報到"]
        if any(kw in user_query for kw in SHELTER_KEYWORDS):
            register_url = f"{BASE_URL}/register"
            flex = FlexSendMessage(
                alt_text="避難所登記系統",
                contents={
                    "type": "bubble",
                    "size": "mega",
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📋 避難所登記系統",
                                "weight": "bold",
                                "size": "xl",
                            },
                            {
                                "type": "text",
                                "text": "請點選下方按鈕填寫基本資料，以便我們在災害發生時掌握避難人數。",
                                "wrap": True,
                                "size": "sm",
                                "color": "#666666",
                            },
                        ],
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#1a5276",
                                "action": {
                                    "type": "uri",
                                    "label": "📝 填寫避難資料",
                                    "uri": register_url,
                                },
                            },
                        ],
                    },
                },
            )
            line_bot_api.reply_message(event.reply_token, flex)
            return
 
        # ── 關鍵字攔截：避難所地圖 ──
        MAP_KEYWORDS = ["避難所地圖", "查看地圖", "地圖", "找最近避難所", "附近避難所"]
        if any(kw in user_query for kw in MAP_KEYWORDS):
            map_url = f"{BASE_URL}/map"
            flex = FlexSendMessage(
                alt_text="避難所地圖",
                contents={
                    "type": "bubble",
                    "size": "mega",
                    "hero": {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#1a5276",
                        "paddingAll": "20px",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🗺️",
                                "size": "5xl",
                                "align": "center",
                                "color": "#ffffff",
                            },
                        ],
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "避難所地圖",
                                "weight": "bold",
                                "size": "xl",
                            },
                            {
                                "type": "text",
                                "text": "點開地圖可以：",
                                "size": "sm",
                                "color": "#666666",
                                "margin": "md",
                            },
                            {
                                "type": "text",
                                "text": "📍 查看您附近的避難所",
                                "size": "sm",
                                "margin": "sm",
                            },
                            {
                                "type": "text",
                                "text": "🚶 一鍵找到最近避難所",
                                "size": "sm",
                                "margin": "sm",
                            },
                            {
                                "type": "text",
                                "text": "📊 看每個避難所即時狀態",
                                "size": "sm",
                                "margin": "sm",
                            },
                            {
                                "type": "text",
                                "text": "📝 直接從地圖前往報到",
                                "size": "sm",
                                "margin": "sm",
                            },
                        ],
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#1a5276",
                                "action": {
                                    "type": "uri",
                                    "label": "🗺️ 開啟地圖",
                                    "uri": map_url,
                                },
                            },
                        ],
                    },
                },
            )
            line_bot_api.reply_message(event.reply_token, flex)
            return
 
        # ── 關鍵字攔截：最新災害資訊 ──
        NEWS_KEYWORDS = ["取得最新資訊", "最新資訊", "最新災情", "即時資訊", "災害資訊"]
        if any(kw in user_query for kw in NEWS_KEYWORDS):
            info = get_latest_disaster_info()
            messages = [TextSendMessage(text=info["text"])]
 
            if info.get("flex"):
                messages = [
                    FlexSendMessage(
                        alt_text="最新防災資訊",
                        contents=info["flex"],
                    )
                ]
 
            line_bot_api.reply_message(event.reply_token, messages)
            return
 
        result = rag_answer(user_query)
        reply_text = result.get("text", "")
        image_refs = result.get("images", []) or []
        citations = result.get("citations", []) or []
 
        image_urls = [image_ref_to_url(r) for r in image_refs][:2]
 
        # LINE 一次 reply 最多 5 則訊息
        # 文字(1) + 圖片(最多2) + Flex(1) = 最多 4，安全
        messages = [TextSendMessage(text=reply_text)]
 
        for url in image_urls:
            messages.append(
                ImageSendMessage(original_content_url=url, preview_image_url=url)
            )
 
        flex_msg = build_citation_flex(citations)
        if flex_msg:
            messages.append(flex_msg)
 
        line_bot_api.reply_message(event.reply_token, messages)
 
    except Exception as e:
        app.logger.error(f"處理訊息時發生錯誤: {e}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="系統發生錯誤，請稍後再試。"),
            )
        except Exception:
            pass
 
 
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}
 
 
@app.route("/", methods=["GET"])
def home():
    return "LINE Bot is running"
 
 
if __name__ == "__main__":
    # 憑證檢查已於載入時完成（見檔案上方），此處直接啟動
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
