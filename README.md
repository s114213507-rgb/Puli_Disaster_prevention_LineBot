# 🛡️ 噗哩揪安心 — 社區防災虛擬里長

> 一套以檢索增強生成（RAG）技術打造的社區防災問答與避難協調系統，將沉睡於官方文件中的防災知識，轉化為居民用 LINE 即可隨時對話、附來源可查證的「虛擬里長」。以南投縣埔里鎮為實作場域。

---

## 📖 專案簡介

「噗哩揪安心」是一個整合三層知識的社區防災系統：

- **官方規範**：埔里鎮災害應變中心作業手冊
- **社區組織知識**：慈恩社區發展協會志工大隊組織文件
- **即時動態狀態**：避難所容量、避難人數、即時災情

系統服務三種使用者——一般居民、需避難居民、社區管理員，提供五大功能模組。

### 核心功能

| 模組 | 說明 |
|------|------|
| 🤖 虛擬里長問答（RAG） | 自然語言問答，回答附原始文件來源與頁碼引用，並自動配對相關流程圖 |
| 🗺️ 避難所互動地圖 | 即時定位、顏色標示各避難所狀態、Haversine 演算法找最近且未額滿的避難所 |
| 📝 線上事前報到 | 居民出發前線上登記基本資料與特殊需求，到場一鍵驗證 |
| 📊 數位管理後台 | 即時統計總避難人數、各避難所滿載率、特殊需求清冊 |
| 📡 即時災情資訊 | 串接中央氣象署地震／警特報與新聞，不經 AI 生成以確保準確 |

---

## 🏗️ 系統架構

```
                 ┌──────────────┐
   LINE 使用者 ──▶│   LINE 平台   │
                 └──────┬───────┘
                        │ Webhook (HTTPS)
                        ▼
              ┌───────────────────┐
              │   Cloudflare       │  永久固定網域 + 自動 HTTPS
              │   Tunnel           │
              └─────────┬─────────┘
                        ▼
        ┌───────────────────────────────┐
        │      Flask App (model.py)      │
        │  ┌──────────┬───────────────┐  │
        │  │ 關鍵字攔截 │   RAG 問答   │  │
        │  └────┬─────┴───────┬───────┘  │
        │       │             │           │
        │  ┌────▼────┐  ┌─────▼──────┐    │
        │  │ 避難所   │  │ rag_core   │    │
        │  │ 登記/地圖│  │            │    │
        │  └────┬────┘  └──┬─────┬───┘    │
        └───────┼──────────┼─────┼────────┘
                ▼          ▼     ▼
          ┌─────────┐ ┌────────┐ ┌──────────┐
          │ SQLite  │ │ Qdrant │ │ LM Studio │
          │(避難所)  │ │(向量庫) │ │  (LLM)   │
          └─────────┘ └────────┘ └──────────┘
```

---

## 🧰 依賴環境

### 執行環境

| 項目 | 版本 / 需求 |
|------|------------|
| **Python** | 3.11（建議；3.10 亦可） |
| **作業系統** | Windows / Linux / macOS |
| **Qdrant** | 向量資料庫，需獨立執行（Docker 或本機） |
| **LM Studio** | 本地 LLM 推論伺服器（提供 OpenAI 相容 API） |
| **記憶體** | 建議 16GB 以上（跑 8B 模型約需 6GB VRAM） |

### Python 套件

```
flask
python-dotenv
requests
tqdm
line-bot-sdk
sentence-transformers
qdrant-client
```

### 使用的模型

| 用途 | 模型 |
|------|------|
| 中文 Embedding | `BAAI/bge-small-zh-v1.5`（512 維） |
| 大型語言模型 | `Llama-Breeze2-8B-Instruct`（聯發科，繁中強化） |

---

## 🚀 安裝與啟動

### 步驟 1：取得專案

```bash
git clone https://github.com/s114213507-rgb/Puli_Disaster_prevention_LineBot.git
cd Puli_Disaster_prevention_LineBot
```

### 步驟 2：建立虛擬環境並安裝套件

```bash
# 使用 conda
conda create -n rag-qdrant python=3.11
conda activate rag-qdrant

# 或使用 venv
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 步驟 3：啟動 Qdrant 向量資料庫

```bash
# 使用 Docker（推薦）
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

### 步驟 4：啟動 LM Studio

1. 下載並安裝 [LM Studio](https://lmstudio.ai/)
2. 搜尋並下載模型：`Breeze2`（選 GGUF 量化版 Q4_K_M）
3. 載入模型後，於 Server 分頁啟動 API 服務（預設 `localhost:1234`）

### 步驟 5：設定環境變數

複製 `.env.example` 為 `.env` 並填入你的設定（見下方說明）。

### 步驟 6：匯入知識庫

```bash
# 匯入防災手冊 chunks（首次用 --recreate 重建）
python import_chunks.py --json manual_chunks.json --recreate

# 追加社區志工文件 chunks（不加 --recreate，追加至同一 collection）
python import_chunks.py --json community_chunks.json
```

### 步驟 7：啟動主程式

```bash
python model.py
# 預設執行於 http://0.0.0.0:5000
```

### 步驟 8：對外開放（LINE Webhook 需 HTTPS）

```bash
# 使用 Cloudflare Tunnel
cloudflared tunnel run <your-tunnel-name>
```

將 LINE Developers Console 的 Webhook URL 設為 `https://<你的網域>/callback`。

---

## ⚙️ 環境變數說明（.env）

```bash
# ── LINE Bot 憑證（必填，請至 LINE Developers Console 取得）──
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
LINE_CHANNEL_SECRET=your_channel_secret

# ── 對外網址（Cloudflare Tunnel 網域）──
BASE_URL=https://bot.your-domain.org

# ── Qdrant 向量資料庫 ──
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=disaster_rules

# ── Embedding 模型 ──
EMBED_MODEL=BAAI/bge-small-zh-v1.5

# ── LM Studio（本地 LLM）──
LMSTUDIO_URL=http://localhost:1234/v1/chat/completions
LMSTUDIO_MODEL=llama-breeze2-8b-instruct-text

# ── RAG 檢索參數 ──
RETRIEVE_K=12        # 先檢索的候選數
TOP_K=5              # 最終送入 LLM 的 chunk 數

# ── 中央氣象署 API（即時災情，選填）──
# 申請：https://opendata.cwa.gov.tw/
CWA_API_KEY=your_cwa_api_key

# ── 其他 ──
PORT=5000
SHELTER_DB=shelter.db
MAX_QUERY_LENGTH=500
```

---

## 💻 Client Sample Code（API 呼叫範例）

系統提供數個 HTTP 端點，以下為各端點的呼叫範例。

### 1. 健康檢查

```bash
curl https://bot.your-domain.org/health
# 回應：{"status": "ok"}
```

### 2. 取得避難所地圖資料（JSON API）

```bash
curl https://bot.your-domain.org/api/shelters/map
```

回應範例：

```json
{
  "shelters": [
    {
      "id": 13,
      "name": "東門里 東門里集會所",
      "address": "四維路26號",
      "village": "東門里",
      "capacity": 30,
      "latitude": 23.9655,
      "longitude": 120.9710,
      "checked_in_people": 12,
      "pre_registered_people": 5,
      "status_label": "有空位",
      "status_color": "green"
    }
  ]
}
```

### 3. Python 呼叫 RAG 核心（程式內部使用）

```python
from rag_core import rag_answer

result = rag_answer("東門里里長的電話是多少？")

print(result["text"])        # AI 生成的回答
print(result["citations"])   # 來源引用（PDF 檔名、頁碼、跳轉連結）
print(result["images"])      # 自動配對的相關圖片
```

回傳結構：

```python
{
    "text": "東門里的里長是江茂圳，電話是 0921-787347。",
    "citations": [
        {
            "title": "31522_南投縣埔里鎮災害應變中心作業手冊(114.5.5修訂).pdf",
            "page": 24,
            "section": "四、開設程序 > 附件 > 災情查報人員聯絡名冊",
            "url": "https://bot.your-domain.org/static/pdf/...#page=24"
        }
    ],
    "images": []
}
```

### 4. 更新避難者狀態（管理後台 API）

```bash
curl -X POST https://bot.your-domain.org/admin/shelter/status \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "status": "checked_in"}'
# 回應：{"ok": true}
```

### 5. LINE Bot 觸發關鍵字

使用者在 LINE 輸入以下關鍵字會觸發對應功能（不進入 RAG）：

| 關鍵字 | 功能 |
|--------|------|
| `填寫避難所資料`、`避難所登記` | 回傳線上報到連結 |
| `避難所地圖`、`找最近避難所` | 回傳互動地圖連結 |
| `取得最新資訊`、`最新災情` | 回傳即時地震／警報／新聞 |
| 其他任何防災問題 | 進入 RAG 問答 |

---

## 📁 專案結構

```
puli-disaster-bot/
├── model.py              # LINE Bot 主程式（Flask）
├── rag_core.py           # RAG 核心：檢索 + 生成 + 引用
├── ingest.py             # PDF 解析與 chunking
├── import_chunks.py      # 將 chunks 匯入 Qdrant
├── shelter_db.py         # 避難所資料庫層（SQLite）
├── shelter_routes.py     # 登記表單 + 管理後台
├── shelter_map.py        # 避難所地圖（Leaflet.js）
├── news_fetcher.py       # 即時災情爬取
├── manual_chunks.json    # 防災手冊知識庫
├── community_chunks.json # 社區志工文件知識庫
├── requirements.txt
├── .env.example
└── static/
    ├── pdf/              # 原始 PDF（供引用跳頁）
    └── images/           # 流程圖、組織圖截圖
```

---

## 🔒 風險控制設計

本系統針對防災「人命關天」場景，採取三項 AI 風險緩解機制：

1. **嚴格遵循文本**：核心 Prompt 強制約束「文件無記載則回答不知道，不延伸臆測」
2. **實證鏈結**：每則回答附來源引用卡，標明 PDF 與頁碼，可一鍵查證
3. **動態資訊不經 AI**：即時災情（地震、警報、避難人數）直接以結構化資料呈現，不經 LLM 生成

---

## 🛠️ 技術棧

- **後端**：Python 3.11 + Flask
- **向量資料庫**：Qdrant
- **Embedding**：sentence-transformers（BAAI/bge-small-zh-v1.5）
- **LLM**：Llama-Breeze2-8B-Instruct（透過 LM Studio）
- **PDF 解析**：Docling / pdfplumber
- **地圖**：Leaflet.js + OpenStreetMap（免費、無需 API key）
- **對話介面**：LINE Messaging API
- **部署**：Cloudflare Tunnel（永久 HTTPS）

---

## 📄 授權

本專案為學術研究與社會實踐用途。知識庫文件來源為埔里鎮公所及慈恩社區發展協會公開頒布之防災文件。

---

## 👥 作者

國立暨南國際大學 資訊管理學系
