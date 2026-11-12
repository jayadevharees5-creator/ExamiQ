# QuizForge AI — Intelligent Question Generator

**"Turn knowledge into questions."**

QuizForge AI is a modern AI-powered educational assessment platform built with **HTML5, Vanilla CSS, Vanilla JavaScript**, and a high-performance **Python FastAPI** backend powered by **Groq API, FAISS, BM25, and Reciprocal Rank Fusion (RRF)**.

---

## 🌟 Key Features

### 1. Modern HTML5, Vanilla CSS & Vanilla JavaScript UI
- **Zero Framework Bloat**: Pure HTML, CSS, and modern ES6+ JavaScript.
- **Charcoal-Grey & Muted-Gold Design**:
  - Background: `#17191D`
  - Cards: `#22252B`
  - Panels: `#2B2E35`
  - Gold Accent: `#D6B15E`
  - Light Gold: `#F0D58A`
  - Text: `#F5F5F2` (Main), `#A6A9B0` (Muted)
  - Borders: `#3A3D44`
- **No Forced Defaults**: All topic and prompt inputs start clean and blank with helpful placeholder text so you can ask whatever you want.
- **De-cluttered Interface**: No technical noise, debug dumps, or unnecessary widgets.

### 2. Document Intelligence (PDF-Based RAG + Hybrid RRF)
- **Multi-PDF Drag & Drop**: Ingest multiple study materials, lecture notes, or textbooks.
- **Scanned PDF Guard**: Checks text density across pages to alert users if a PDF consists of unsearchable scanned images instead of generating fabricated content.
- **Hybrid Retrieval**:
  - **Dense Vector Search**: Powered by Sentence Transformers (`all-MiniLM-L6-v2`) and FAISS IndexFlatIP (cosine similarity).
  - **Sparse Keyword Search**: Powered by BM25Okapi for exact formulas, abbreviations, and code identifiers.
- **Reciprocal Rank Fusion (RRF)**: Combines dense and sparse ranked lists using:
  $$RRF(d) = \sum_{m \in \{dense, bm25\}} \frac{1}{k + rank_m(d)}$$
  ($k=60$ default) to prioritize chunks with strong dual support.
- **Strict Grounding**: Requires explicit document title and page number citations on every question; explicitly declines when context is insufficient.

### 3. Knowledge Studio (General AI & DSA Problem Studio)
- **No PDF Required**: Generate comprehensive assessments on any technical or academic topic using Groq's high-speed LLM models (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, etc.).
- **DSA & Coding Problem Studio**: Generates LeetCode-style problem statements with input/output format, constraints, sample I/O with step-by-step traces, hints, time and space complexity, and complete solution code in Python, Java, C++, C, or JavaScript.
- **Supported Question Formats**:
  - Multiple Choice Questions (MCQ)
  - Fill in the Blanks
  - True or False
  - Short Answer Questions
  - Long Answer Questions
  - Match the Following
  - Coding Questions & Challenges
  - Output Prediction & Debugging

### 4. Interactive Quiz Arena
- Dedicated modal arena displaying one question at a time.
- Instant submission, immediate feedback, progress tracker, and live score calculation.
- Post-quiz review screen with detailed answer explanations.
- **"Retry Mistakes"**: Filter and re-attempt only the questions answered incorrectly.

### 5. Multi-Format Exporters
- **Download as PDF**: Generates publication-ready test papers with QuizForge branding, questions, choices, and an answer key using ReportLab.
- **Download as CSV**: Tabular format compatible with Google Forms, Excel, or LMS platforms.
- **Export as TXT**: Clean markdown/plain text for quick copy-pasting.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Groq API Key
You can set your API key in `.env`:
```ini
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```
Or click **"⚙️ Settings"** in the top right of the application to enter and save it directly in the browser!

*(Get your free Groq API key at [console.groq.com](https://console.groq.com/keys))*

### 3. Run the Application
```bash
python server.py
```
Or using uvicorn:
```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to:
**`http://localhost:8000`**

---

## 📁 Project Architecture

```
quizforge-ai/
│
├── server.py                   # FastAPI backend server & static asset mount
├── config.py                   # Centralized configuration & theme tokens
├── requirements.txt            # Project dependencies
├── .env.example                # Configuration template
├── .env                        # Local environment variables
│
├── static/
│   ├── index.html              # Clean semantic HTML5 layout & components
│   ├── style.css               # Vanilla CSS design system (Charcoal & Gold)
│   └── app.js                  # Vanilla JS state, API client & Quiz arena
│
├── faiss_indexes/              # Persistent per-user FAISS indexes & metadata
│
├── core/
│   ├── pdf_processor.py        # PyMuPDF text extraction & scanned detection
│   ├── text_chunker.py         # Overlapping text chunker preserving page citations
│   ├── embeddings.py           # Cached SentenceTransformer embedding generator
│   ├── vector_store.py         # FAISS IndexFlatIP dense vector store with disk persistence
│   ├── bm25_retriever.py       # BM25Okapi sparse keyword retriever
│   ├── rrf_fusion.py           # Reciprocal Rank Fusion implementation
│   ├── rag_pipeline.py         # Hybrid retrieval coordinator with index persistence
│   ├── groq_client.py          # Groq API client with JSON enforcement & retries
│   ├── question_generator.py   # High-level assessment orchestrator
│   └── quiz_engine.py          # Interactive quiz state machine
│
├── prompts/
│   ├── pdf_question_prompt.py        # Grounded RAG prompts
│   ├── knowledge_question_prompt.py  # General knowledge prompts
│   └── dsa_question_prompt.py        # Structured DSA problem prompts
│
├── utils/
│   ├── auth.py                 # JWT access tokens, signature verification & user auth
│   ├── rate_limiter.py         # Redis-backed distributed rate limiter with memory fallback
│   ├── request_logger.py       # Structured request logging (timestamps, users, endpoints)
│   ├── validators.py           # Schema sanitization & normalization
│   ├── exporters.py            # PDF (ReportLab), CSV, and TXT exporters
│   └── helpers.py              # Clipboard & text formatting utilities
│
└── README.md                   # Documentation & setup guide
```
