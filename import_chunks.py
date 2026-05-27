"""
import_chunks.py — 將手動切好的 JSON 匯入 Qdrant

用法:
    python import_chunks.py --json manual_chunks.json --recreate
"""
import json, argparse, logging
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, PayloadSchemaType
from tqdm import tqdm
from dotenv import load_dotenv
import os

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "disaster_rules")
EMBED_MODEL = os.getenv("EMBED_MODEL", "")
PDF_URL = os.getenv("PDF_URL", "")  # 如果有公開 URL 就填

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="chunks JSON 檔案路徑")
    parser.add_argument("--recreate", action="store_true", help="重建 collection")
    args = parser.parse_args()

    # 讀取 chunks
    with open(args.json, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    log.info(f"讀入 {len(chunks)} 個 chunks")

    # 載入 embedding 模型
    log.info(f"載入模型: {EMBED_MODEL}")
    encoder = SentenceTransformer(EMBED_MODEL)
    dim = encoder.get_sentence_embedding_dimension()

    # 連接 Qdrant
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    if args.recreate:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
            log.info(f"已刪除 {COLLECTION}")

    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        client.create_payload_index(COLLECTION, "category", PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "chunk_type", PayloadSchemaType.KEYWORD)
        log.info(f"已建立 {COLLECTION} (dim={dim})")

    # 向量化
    texts = [c["text"] for c in chunks]
    log.info("向量化中...")
    embeddings = encoder.encode(texts, show_progress_bar=True, batch_size=32, normalize_embeddings=True)

    # 計算 ID offset（追加模式）
    info = client.get_collection(COLLECTION)
    id_offset = info.points_count
    log.info(f"現有 {id_offset} 筆，從 ID {id_offset} 開始寫入")

    # 寫入
    default_pdf = "31522_南投縣埔里鎮災害應變中心作業手冊(114.5.5修訂).pdf"
    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, embeddings)):
        page = chunk.get("page")
        # 每個 chunk 可以有自己的 source_pdf（社區志工文件），或用預設值
        src_pdf = chunk.get("source_pdf", default_pdf)

        points.append(PointStruct(
            id=id_offset + i,
            vector=vec.tolist(),
            payload={
                "text": chunk["text"],
                "source_pdf": src_pdf,
                "page": page,
                "section_path": chunk.get("section_path", ""),
                "chunk_type": chunk.get("chunk_type", "text"),
                "category": chunk.get("category", "general"),
                "image_refs": chunk.get("image_refs", []),
            },
        ))

    batch_size = 100
    for start in tqdm(range(0, len(points), batch_size), desc="寫入 Qdrant"):
        client.upsert(collection_name=COLLECTION, points=points[start:start+batch_size])

    log.info(f"✅ 完成！{len(points)} 個 chunks 已寫入 {COLLECTION}")

if __name__ == "__main__":
    main()
