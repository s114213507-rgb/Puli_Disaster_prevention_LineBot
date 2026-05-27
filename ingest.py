import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# ──────────────────────────────────────
# 設定
# ──────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "disaster_rules")

# Embedding 模型：中文專用，512 維，最大 512 tokens
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "")
EMBED_DIM = 512

# Chunking 參數
MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "512"))
OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP", "80"))

# 類別關鍵字（與 rag_core.py 保持一致）
CATEGORY_KEYWORDS = {
    "evacuation": ["避難", "避難所", "收容", "安置", "疏散", "撤離"],
    "earthquake": ["地震", "餘震", "震度", "耐震"],
    "landslide": ["土石流", "崩塌", "山崩", "地滑"],
    "typhoon": ["颱風", "豪雨", "淹水", "水災", "洪水", "風災"],
    "contact": ["電話", "聯絡", "通報", "名冊", "聯繫"],
    "equipment": ["設備", "器材", "物資", "清單", "備品"],
    "procedure": ["流程", "步驟", "SOP", "程序", "開設"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────
# 1. PDF 解析（Docling）
# ──────────────────────────────────────
def parse_pdf(pdf_path: str):
    """
    用 Docling 解析 PDF，回傳結構化的 Document 物件。
    Docling 會自動辨識：標題層級、段落、表格、圖片、清單。
    """
    from docling.document_converter import DocumentConverter

    log.info(f"正在解析 PDF: {pdf_path}")
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    log.info(f"PDF 解析完成，共 {result.document.num_pages()} 頁")
    return result


# ──────────────────────────────────────
# 2. 結構感知切割（Docling HybridChunker）
# ──────────────────────────────────────
def chunk_document(docling_result, max_tokens: int = MAX_TOKENS) -> List[Dict[str, Any]]:
    """
    使用 Docling 的 HybridChunker 進行結構感知切割。

    HybridChunker 的特性：
    - 表格會被保留為獨立 chunk（不會被切斷）
    - 清單項目會被合併在一起
    - 每個 chunk 頂部帶有所屬章節標題
    - 圖片說明會被獨立切割
    """
    from docling.chunking import HybridChunker

    log.info(f"開始切割文件（max_tokens={max_tokens}）")

    chunker = HybridChunker(
        tokenizer=EMBED_MODEL_NAME,
        max_tokens=max_tokens,
        merge_peers=True,
    )

    raw_chunks = list(chunker.chunk(docling_result.document))
    log.info(f"Docling 切出 {len(raw_chunks)} 個原始 chunk")

    # 轉換成我們需要的格式，補充 metadata
    chunks = []
    for i, chunk in enumerate(raw_chunks):
        meta = chunk.meta or {}

        # 取得頁碼（Docling 的 meta 結構可能因版本而異）
        page = _extract_page(meta)

        # 取得章節路徑
        headings = _extract_headings(meta)
        section_path = " > ".join(headings) if headings else ""

        # 判斷 chunk 類型
        chunk_type = _detect_chunk_type(chunk.text, meta)

        # 判斷內容類別
        category = _detect_category(chunk.text, section_path)

        # 收集圖片引用
        image_refs = _extract_image_refs(meta)

        chunks.append({
            "text": chunk.text.strip(),
            "page": page,
            "section_path": section_path,
            "chunk_type": chunk_type,
            "category": category,
            "image_refs": image_refs,
            "chunk_index": i,
        })

    # 過濾掉空白或太短的 chunk
    chunks = [c for c in chunks if len(c["text"]) >= 20]
    log.info(f"過濾後剩餘 {len(chunks)} 個有效 chunk")

    # ⚠ 拆分超大 chunk（尤其是表格）
    max_chars = int(max_tokens * 0.7)  # 保守估計：1中文字≈1.5 token
    before = len(chunks)
    chunks = _split_oversized_chunks(chunks, max_chars=max_chars)
    if len(chunks) != before:
        log.info(f"拆分超大 chunk: {before} → {len(chunks)} 個")

    # 重新編號
    for i, c in enumerate(chunks):
        c["chunk_index"] = i

    return chunks


def _extract_page(meta) -> Optional[int]:
    """從 Docling meta 中提取頁碼"""
    # Docling 不同版本的 meta 結構可能不同，嘗試多種方式
    if hasattr(meta, "doc_items"):
        for item in meta.doc_items:
            if hasattr(item, "prov") and item.prov:
                for prov in item.prov:
                    if hasattr(prov, "page_no"):
                        return prov.page_no
    if isinstance(meta, dict):
        return meta.get("page") or meta.get("page_no")
    return None


def _extract_headings(meta) -> List[str]:
    """從 Docling meta 中提取章節標題層級"""
    if hasattr(meta, "headings"):
        return meta.headings or []
    if isinstance(meta, dict):
        return meta.get("headings", [])
    return []


def _extract_image_refs(meta) -> List[str]:
    """從 Docling meta 中提取圖片引用"""
    refs = []
    if hasattr(meta, "doc_items"):
        for item in meta.doc_items:
            if hasattr(item, "image") and item.image:
                refs.append(str(item.image))
    if isinstance(meta, dict):
        refs.extend(meta.get("image_refs", []))
    return refs


def _detect_chunk_type(text: str, meta) -> str:
    """判斷 chunk 類型：text / table / image_caption / list"""
    # 檢查 Docling meta 中的類型標記
    if hasattr(meta, "doc_items"):
        for item in meta.doc_items:
            label = getattr(item, "label", "") or ""
            if "table" in label.lower():
                return "table"
            if "picture" in label.lower() or "figure" in label.lower():
                return "image_caption"
            if "list" in label.lower():
                return "list"

    # 啟發式判斷：如果文字中有大量 | 符號，可能是表格
    if text.count("|") > 5:
        return "table"

    return "text"


def _detect_category(text: str, section_path: str) -> str:
    """根據內容和章節路徑判斷類別"""
    combined = text + " " + section_path
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in combined for k in keywords):
            return cat
    return "general"


def _split_oversized_chunks(chunks: List[Dict[str, Any]], max_chars: int = 350) -> List[Dict[str, Any]]:
    """
    將超過 max_chars 的 chunk 拆分成更小的片段。

    表格 chunk：按行分組，每組帶表頭（第一行）
    文字 chunk：按換行符切割，合併到不超過上限
    """
    result = []

    for chunk in chunks:
        text = chunk["text"]

        # 不超過上限，直接保留
        if len(text) <= max_chars:
            result.append(chunk)
            continue

        lines = text.split("\n")

        if chunk["chunk_type"] == "table":
            # 表格拆分：第一行通常是表頭，每個子 chunk 都帶表頭
            header = lines[0] if lines else ""
            data_lines = lines[1:] if len(lines) > 1 else lines

            current_lines = [header] if header else []
            current_len = len(header)

            for line in data_lines:
                line = line.strip()
                if not line:
                    continue

                if current_len + len(line) + 1 > max_chars and len(current_lines) > 1:
                    # 存下當前 chunk
                    sub = chunk.copy()
                    sub["text"] = "\n".join(current_lines)
                    result.append(sub)
                    # 新 chunk 帶表頭重新開始
                    current_lines = [header] if header else []
                    current_len = len(header)

                current_lines.append(line)
                current_len += len(line) + 1

            # 最後一段
            if current_lines and (len(current_lines) > 1 or not header):
                sub = chunk.copy()
                sub["text"] = "\n".join(current_lines)
                result.append(sub)

        else:
            # 文字拆分：按段落/換行合併
            current_lines = []
            current_len = 0

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if current_len + len(line) + 1 > max_chars and current_lines:
                    sub = chunk.copy()
                    sub["text"] = "\n".join(current_lines)
                    result.append(sub)
                    # 保留最後一行作為 overlap
                    overlap = current_lines[-1] if current_lines else ""
                    current_lines = [overlap] if overlap else []
                    current_len = len(overlap)

                current_lines.append(line)
                current_len += len(line) + 1

            if current_lines:
                sub = chunk.copy()
                sub["text"] = "\n".join(current_lines)
                result.append(sub)

    return result


# ──────────────────────────────────────
# 3. Fallback: 手動切割（當 Docling 無法使用時）
# ──────────────────────────────────────
def fallback_parse_and_chunk(pdf_path: str, max_chars: int = 800, overlap_chars: int = 150) -> List[Dict[str, Any]]:
    """
    備用方案：使用 pdfplumber 解析 + 手動切割。
    適用於 Docling 安裝失敗或不支援的環境。

    安裝: pip install pdfplumber
    """
    import pdfplumber

    log.info(f"[Fallback] 使用 pdfplumber 解析: {pdf_path}")

    chunks = []
    chunk_index = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # 提取表格
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                # 將表格轉成文字格式
                headers = table[0] if table else []
                rows = table[1:] if len(table) > 1 else []
                table_text = _table_to_text(headers, rows)
                if len(table_text) >= 20:
                    chunks.append({
                        "text": table_text,
                        "page": page_num,
                        "section_path": "",
                        "chunk_type": "table",
                        "category": _detect_category(table_text, ""),
                        "image_refs": [],
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

            # 提取純文字（排除表格區域）
            text = page.extract_text() or ""
            text = text.strip()
            if not text:
                continue

            # 按段落切割
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

            # 將小段落合併、大段落拆分
            buffer = ""
            for para in paragraphs:
                if len(buffer) + len(para) + 1 <= max_chars:
                    buffer = buffer + "\n" + para if buffer else para
                else:
                    if buffer and len(buffer) >= 20:
                        chunks.append({
                            "text": buffer,
                            "page": page_num,
                            "section_path": "",
                            "chunk_type": "text",
                            "category": _detect_category(buffer, ""),
                            "image_refs": [],
                            "chunk_index": chunk_index,
                        })
                        chunk_index += 1
                        # 保留 overlap
                        overlap = buffer[-overlap_chars:] if len(buffer) > overlap_chars else ""
                        buffer = overlap + "\n" + para if overlap else para
                    else:
                        buffer = para

            # 處理最後的 buffer
            if buffer and len(buffer) >= 20:
                chunks.append({
                    "text": buffer,
                    "page": page_num,
                    "section_path": "",
                    "chunk_type": "text",
                    "category": _detect_category(buffer, ""),
                    "image_refs": [],
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

    log.info(f"[Fallback] 共切出 {len(chunks)} 個 chunk")
    return chunks


def _table_to_text(headers: list, rows: list) -> str:
    """將表格轉換為結構化文字"""
    lines = []
    clean_headers = [str(h).strip() if h else "" for h in headers]

    for row in rows:
        clean_row = [str(cell).strip() if cell else "" for cell in row]
        pairs = []
        for h, v in zip(clean_headers, clean_row):
            if h and v:
                pairs.append(f"{h}: {v}")
            elif v:
                pairs.append(v)
        if pairs:
            lines.append("｜".join(pairs))

    return "\n".join(lines)


# ──────────────────────────────────────
# 4. 向量化 + 存入 Qdrant
# ──────────────────────────────────────
def embed_and_store(
    chunks: List[Dict[str, Any]],
    source_pdf: str,
    pdf_url: str = "",
    collection: str = COLLECTION,
    recreate: bool = False,
):
    """
    將 chunks 向量化後存入 Qdrant。
    """
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        PointStruct,
        VectorParams,
        Distance,
        PayloadSchemaType,
    )

    # 初始化 embedding 模型
    log.info(f"載入 Embedding 模型: {EMBED_MODEL_NAME}")
    encoder = SentenceTransformer(EMBED_MODEL_NAME)

    # 連接 Qdrant
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # 建立或重建 collection
    existing = [c.name for c in client.get_collections().collections]

    if recreate and collection in existing:
        log.info(f"刪除現有 collection: {collection}")
        client.delete_collection(collection)
        existing.remove(collection)

    if collection not in existing:
        log.info(f"建立 collection: {collection} (dim={EMBED_DIM})")
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        # 建立 payload index 以加速篩選
        client.create_payload_index(collection, "category", PayloadSchemaType.KEYWORD)
        client.create_payload_index(collection, "chunk_type", PayloadSchemaType.KEYWORD)
        client.create_payload_index(collection, "source_pdf", PayloadSchemaType.KEYWORD)

    # 計算現有最大 ID（用於追加模式）
    collection_info = client.get_collection(collection)
    start_id = collection_info.points_count

    # 批次向量化
    log.info(f"開始向量化 {len(chunks)} 個 chunk ...")
    texts = [c["text"] for c in chunks]

    # 對中文 bge 模型，query 時需要加 prefix，但存入時不需要
    embeddings = encoder.encode(
        texts,
        show_progress_bar=True,
        batch_size=32,
        normalize_embeddings=True,
    )

    # 組裝 points
    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        page = chunk["page"]
        jump_url = ""
        if pdf_url:
            jump_url = f"{pdf_url}#page={page}" if isinstance(page, int) and page > 0 else pdf_url

        points.append(
            PointStruct(
                id=start_id + i,
                vector=vector.tolist(),
                payload={
                    "text": chunk["text"],
                    "source_pdf": source_pdf,
                    "pdf_url": pdf_url,
                    "page": page,
                    "section_path": chunk["section_path"],
                    "chunk_type": chunk["chunk_type"],
                    "category": chunk["category"],
                    "image_refs": chunk["image_refs"],
                    "chunk_index": chunk["chunk_index"],
                },
            )
        )

    # 分批寫入（每批 100 個，避免 payload 太大）
    batch_size = 100
    for batch_start in tqdm(range(0, len(points), batch_size), desc="寫入 Qdrant"):
        batch = points[batch_start : batch_start + batch_size]
        client.upsert(collection_name=collection, points=batch)

    log.info(f"✅ 成功寫入 {len(points)} 個 chunk 到 {collection}")

    # 輸出統計
    _print_stats(chunks)


def _print_stats(chunks: List[Dict[str, Any]]):
    """輸出切割統計資訊"""
    from collections import Counter

    type_counts = Counter(c["chunk_type"] for c in chunks)
    cat_counts = Counter(c["category"] for c in chunks)
    text_lengths = [len(c["text"]) for c in chunks]

    log.info("=" * 50)
    log.info("📊 Chunk 統計")
    log.info(f"   總數: {len(chunks)}")
    log.info(f"   平均長度: {sum(text_lengths) / len(text_lengths):.0f} 字")
    log.info(f"   最短: {min(text_lengths)} 字 / 最長: {max(text_lengths)} 字")
    log.info(f"   類型分布: {dict(type_counts)}")
    log.info(f"   類別分布: {dict(cat_counts)}")
    log.info("=" * 50)


# ──────────────────────────────────────
# 5. 主程式
# ──────────────────────────────────────
def process_single_pdf(
    pdf_path: str,
    pdf_url: str = "",
    collection: str = COLLECTION,
    max_tokens: int = MAX_TOKENS,
    recreate: bool = False,
    use_fallback: bool = False,
):
    """處理單一 PDF 檔案"""
    source_pdf = Path(pdf_path).name

    if use_fallback:
        chunks = fallback_parse_and_chunk(pdf_path)
    else:
        try:
            result = parse_pdf(pdf_path)
            chunks = chunk_document(result, max_tokens=max_tokens)
        except ImportError:
            log.warning("Docling 未安裝，自動切換到 fallback 模式（pdfplumber）")
            chunks = fallback_parse_and_chunk(pdf_path)
        except Exception as e:
            log.error(f"Docling 解析失敗: {e}")
            log.info("嘗試使用 fallback 模式 ...")
            chunks = fallback_parse_and_chunk(pdf_path)

    if not chunks:
        log.error(f"未能從 {pdf_path} 提取任何 chunk")
        return

    embed_and_store(
        chunks=chunks,
        source_pdf=source_pdf,
        pdf_url=pdf_url,
        collection=collection,
        recreate=recreate,
    )

    # 同時輸出一份 JSON 備份，方便除錯
    backup_path = Path(pdf_path).stem + "_chunks.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Chunk 備份已存到: {backup_path}")


def main():
    parser = argparse.ArgumentParser(description="防災手冊 PDF → Qdrant Ingestion")
    parser.add_argument("--pdf", type=str, help="單一 PDF 檔案路徑")
    parser.add_argument("--pdf-dir", type=str, help="PDF 資料夾路徑（批次處理）")
    parser.add_argument("--pdf-url", type=str, default="", help="PDF 的公開 URL（用於 citation 跳頁）")
    parser.add_argument("--collection", type=str, default=COLLECTION, help="Qdrant collection 名稱")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS, help="每個 chunk 最大 token 數")
    parser.add_argument("--recreate", action="store_true", help="刪除並重建 collection")
    parser.add_argument("--fallback", action="store_true", help="強制使用 pdfplumber（不用 Docling）")

    args = parser.parse_args()

    if not args.pdf and not args.pdf_dir:
        parser.print_help()
        sys.exit(1)

    pdf_files = []
    if args.pdf:
        pdf_files.append(args.pdf)
    if args.pdf_dir:
        pdf_dir = Path(args.pdf_dir)
        pdf_files.extend(sorted(str(p) for p in pdf_dir.glob("*.pdf")))

    if not pdf_files:
        log.error("找不到任何 PDF 檔案")
        sys.exit(1)

    log.info(f"共找到 {len(pdf_files)} 個 PDF 檔案待處理")

    for i, pdf_path in enumerate(pdf_files):
        log.info(f"\n{'='*60}")
        log.info(f"處理第 {i+1}/{len(pdf_files)} 個: {pdf_path}")
        log.info(f"{'='*60}")

        # 只有第一個檔案且有 --recreate 時才重建
        process_single_pdf(
            pdf_path=pdf_path,
            pdf_url=args.pdf_url,
            collection=args.collection,
            max_tokens=args.max_tokens,
            recreate=(args.recreate and i == 0),
            use_fallback=args.fallback,
        )

    log.info("\n🎉 全部處理完成！")


if __name__ == "__main__":
    main()
