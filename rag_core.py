
import os
import textwrap
import logging
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
import requests

load_dotenv()

log = logging.getLogger(__name__)

# ──────────────────────────────────────
# 環境變數
# ──────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "disaster_rules")

RETRIEVE_K = int(os.getenv("RETRIEVE_K", ""))   # 先拉 8 筆
TOP_K = int(os.getenv("TOP_K", ""))              # 最終取 3 筆（配合 Breeze-7B 4096 context）

LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "")

# ──────────────────────────────────────
# Embedding 模型（中文）
# ──────────────────────────────────────
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
 
# bge 模型在 query 時需要加 prefix 才能提升效果
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关段落："
 
log.info(f"載入 Embedding 模型: {EMBED_MODEL_NAME}")
encoder = SentenceTransformer(EMBED_MODEL_NAME)
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
 
 
# ──────────────────────────────────────
# 類別偵測
# ──────────────────────────────────────
CATEGORY_KEYWORDS = {
    "evacuation": ["避難", "避難所", "收容", "安置", "疏散", "撤離"],
    "earthquake": ["地震", "餘震", "震度", "耐震"],
    "landslide": ["土石流", "崩塌", "山崩", "地滑"],
    "typhoon": ["颱風", "豪雨", "淹水", "水災", "洪水", "風災"],
    "contact": ["電話", "聯絡", "通報", "名冊", "聯繫"],
    "equipment": ["設備", "器材", "物資", "清單", "備品"],
    "procedure": ["流程", "步驟", "SOP", "程序", "開設"],
}
 
# 問題類型 → 偏好的 chunk_type
QUERY_TYPE_PREFERENCE = {
    "contact": "table",
    "equipment": "table",
    "procedure": "text",
}
 
 
def detect_category(query: str) -> str:
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in query for k in keywords):
            return cat
    return "general"
 
 
# ──────────────────────────────────────
# Embedding
# ──────────────────────────────────────
def embed_query(text: str) -> List[float]:
    """
    對查詢文字進行向量嵌入。
    bge 模型要求 query 加上特定 prefix 以區分 query 和 passage。
    """
    prefixed = BGE_QUERY_PREFIX + text
    return encoder.encode(prefixed, normalize_embeddings=True).tolist()
 
 
def embed_passage(text: str) -> List[float]:
    """對文件段落進行向量嵌入（不加 prefix）"""
    return encoder.encode(text, normalize_embeddings=True).tolist()
 
 
# ──────────────────────────────────────
# 向量搜尋 + 簡易 Rerank
# ──────────────────────────────────────
def search_disaster_knowledge(
    query: str,
    category: str = "general",
    retrieve_k: int = RETRIEVE_K,
    top_k: int = TOP_K,
) -> List[Dict[str, Any]]:
    """
    1. 用向量搜尋取回 retrieve_k 筆候選結果
    2. 根據 category + chunk_type 進行簡易 rerank
    3. 回傳 top_k 筆最佳結果
    """
    vector = embed_query(query)
 
    # 建立篩選條件
    query_filter = None
    if category != "general":
        query_filter = Filter(
            should=[
                FieldCondition(key="category", match=MatchValue(value=category)),
                FieldCondition(key="category", match=MatchValue(value="general")),
            ]
        )
 
    results = qdrant.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=query_filter,
        limit=retrieve_k,
        with_payload=True,
        with_vectors=False,
    ).points
 
    # 組裝候選結果
    candidates: List[Dict[str, Any]] = []
    for hit in results:
        payload = hit.payload or {}
        txt = payload.get("text")
        if not txt:
            continue
 
        candidates.append({
            "text": txt,
            "score": hit.score,
            "source_pdf": payload.get("source_pdf") or "",
            "pdf_url": payload.get("pdf_url") or "",
            "source_md": payload.get("source_md") or payload.get("source") or "",
            "page": payload.get("page"),
            "section_path": payload.get("section_path") or payload.get("section_title") or "",
            "chunk_type": payload.get("chunk_type") or "text",
            "category": payload.get("category") or "general",
            "image_refs": payload.get("image_refs") or [],
        })
 
    # 簡易 rerank：根據類別偏好調整分數
    preferred_type = QUERY_TYPE_PREFERENCE.get(category)
    if preferred_type:
        for c in candidates:
            if c["chunk_type"] == preferred_type:
                c["score"] += 0.05  # 小幅加分
 
    # 按調整後分數排序，取 top_k
    candidates.sort(key=lambda x: x["score"], reverse=True)
 
    return candidates[:top_k]
 
 
# ──────────────────────────────────────
# Prompt 組裝
# ──────────────────────────────────────
def build_prompt(user_query: str, hits: List[Dict[str, Any]]) -> str:
    ctx_lines = []
    for i, h in enumerate(hits[:TOP_K], start=1):
        src = h.get("source_pdf") or h.get("source_md") or "原始文件"
        page = h.get("page")
        page_str = f"第{page}頁" if isinstance(page, int) and page > 0 else "頁碼未知"
        sec = h.get("section_path") or ""
        sec_str = f"｜{sec}" if sec else ""
        chunk_type = h.get("chunk_type") or "text"
        type_label = {"table": "📊表格", "image_caption": "🖼️圖片說明", "list": "📋清單"}.get(chunk_type, "📝文字")
 
        ctx_lines.append(f"[{i}] {type_label} ({src} {page_str}{sec_str})\n{h['text']}")
 
    context = "\n\n".join(ctx_lines)
 
    guide = textwrap.dedent("""
        你是「埔里防災小幫手」。請依據提供的資料回答。
        規則：
        1) 只使用【已檢索到的資料】做具體結論；缺資訊就明說「資料庫沒有此資訊」。
        2) 回答要簡潔、分點、可行動。
        3) 若使用到任何具體資訊（流程、外觀描述、設備、名冊等），請在該句末尾加引用：(原始PDF 第X頁｜章節)
        4) 不要捏造地址、電話、數值或流程。
        5) 如果資料中有表格內容（標記為📊表格），請忠實呈現表格中的數據。
        6) 回答長度控制在 300 字以內。
    """).strip()
 
    return f"{guide}\n\n【已檢索到的資料】\n{context}\n\n【使用者問題】\n{user_query}\n\n請回答："
 
 
# ──────────────────────────────────────
# LLM 呼叫
# ──────────────────────────────────────
def ask_llm(prompt: str) -> str:
    payload = {
        "model": LMSTUDIO_MODEL,
        "messages": [
            {"role": "system", "content": "你是一位嚴謹的防災知識助理，只根據提供的資料回覆。回答要簡潔精準。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
    }
    r = requests.post(LMSTUDIO_URL, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()
 
 
# ──────────────────────────────────────
# 主入口
# ──────────────────────────────────────
def rag_answer(user_query: str) -> dict:
    cat = detect_category(user_query)
    hits = search_disaster_knowledge(user_query, category=cat)
 
    # Citations — 自動從 source_pdf 組裝 PDF 跳頁連結
    BASE_URL = os.getenv("BASE_URL", "")
    citations = []
    seen_c = set()
    for h in hits:
        pdf = h.get("source_pdf") or ""
        page = h.get("page")
        sec = h.get("section_path") or ""
 
        if not pdf:
            continue
 
        key = (pdf, page, sec)
        if key in seen_c:
            continue
        seen_c.add(key)
 
        # 優先使用 payload 中的 pdf_url，否則用 BASE_URL/static/pdf/ 自動產生
        pdf_url = h.get("pdf_url") or ""
        from urllib.parse import quote
        if not pdf_url and BASE_URL:
            pdf_url = f"{BASE_URL}/static/pdf/{quote(pdf)}"
 
        jump_url = pdf_url
        if pdf_url and isinstance(page, int) and page > 0:
            jump_url = f"{pdf_url}#page={page}"
 
        if jump_url:
            citations.append({
                "title": pdf or "原始文件",
                "page": page if isinstance(page, int) else None,
                "section": sec,
                "url": jump_url,
            })
 
    # Images
    images = []
    seen_i = set()
    for h in hits:
        for ref in h.get("image_refs") or []:
            if ref and ref not in seen_i:
                seen_i.add(ref)
                images.append(ref)
 
    if not hits:
        return {
            "text": "資料庫沒有找到與此問題相關的內容。你可以改問：開設等級、通報流程、任務分工、設備清單、聯絡方式等。",
            "images": [],
            "citations": [],
        }
 
    prompt = build_prompt(user_query, hits)
 
    try:
        answer = ask_llm(prompt)
    except Exception as e:
        log.error(f"LLM 呼叫失敗: {e}")
        # LLM 掛了也照樣回 citations + images + 原文摘要
        fallback_texts = [h["text"][:100] + "..." for h in hits[:2]]
        answer = "抱歉，系統目前無法連線到語言模型。以下是找到的相關原文摘要：\n" + "\n".join(fallback_texts)
 
    return {
        "text": answer,
        "images": images[:2],
        "citations": citations[:3],
    }
 
