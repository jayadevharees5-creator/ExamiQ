# ExamiQ – AI-Powered Intelligent Question Generator

### Turn Knowledge into Questions. Build Smarter Assessments.

ExamiQ is an AI-powered educational assessment platform that transforms study materials and academic topics into structured question papers, interactive quizzes, and coding challenges.

Built using **HTML5, Vanilla CSS, Vanilla JavaScript, and Python FastAPI**, ExamiQ combines **Groq LLM, Hybrid RAG, FAISS, BM25, and Reciprocal Rank Fusion (RRF)** to generate relevant, context-aware assessments.

---

## 🌟 Key Features

### 1. Modern and Responsive User Interface

- **Frontend:** Pure HTML5, Vanilla CSS, and modern JavaScript (ES6+).
- **Design:** Professional Charcoal-Grey and Muted-Gold theme.
- **Clean Interface:** Minimal layout with intuitive navigation and easy-to-use controls.
- **Flexible Inputs:** Generate assessments using uploaded documents or custom topics.
- **Responsive Design:** User-friendly experience across different screen sizes.

### 2. Intelligent Document Processing and Hybrid RAG

Transform uploaded academic documents into context-aware assessments.

- **Multi-PDF Upload:** Upload multiple study materials, lecture notes, and textbooks.
- **PDF Text Extraction:** Extracts text and identifies scanned or unsearchable documents.
- **Smart Chunking:** Splits extracted content into meaningful overlapping chunks while preserving page references.

**Hybrid Retrieval Architecture:**

- **Dense Vector Search:** Uses Sentence Transformers (`all-MiniLM-L6-v2`) and FAISS for semantic similarity search.
- **Sparse Keyword Search:** Uses BM25Okapi to identify exact keywords, technical terms, formulas, and code identifiers.
- **Reciprocal Rank Fusion (RRF):** Combines semantic and keyword search results to improve retrieval relevance.

RRF scoring formula:

\[
RRF(d)=\sum_m \frac{1}{k+rank_m(d)}
\]

Where:
- `d` = Retrieved document chunk.
- `k` = Ranking constant (default 60).
- `rank_m(d)` = Rank of the document in a retrieval method.

**Context-Aware Question Generation:**
- Generates questions based on retrieved document content.
- Preserves source document and page references.
- Avoids generating unsupported questions when the available context is insufficient.

### 3. AI Knowledge Studio

Generate assessments without uploading PDF documents.

- Generate questions from academic subjects and technical topics.
- Uses Groq-powered LLM models.
- Supports configurable difficulty levels and question counts.

**Supported Question Types:**

- Multiple Choice Questions (MCQs)
- Fill in the Blanks
- True or False
- Short Answer Questions
- Long Answer Questions
- Match the Following
- Coding Questions and Challenges
- Output Prediction and Debugging

### 4. DSA and Coding Problem Studio

Generate programming challenges in a structured, LeetCode-style format.

Features include:
- Problem statements and descriptions.
- Input and output specifications.
- Constraints and sample test cases.
- Step-by-step sample explanations.
- Hints and problem-solving guidance.
- Time and space complexity analysis.
- Solutions in Python, Java, C++, C, and JavaScript.

### 5. Interactive Quiz Arena

Practice generated questions through an interactive quiz environment.

- One-question-at-a-time interface.
- Instant answer submission and feedback.
- Automatic score calculation.
- Quiz progress tracking.
- Detailed answer explanations.
- Retry Mistakes feature to practice incorrectly answered questions.

### 6. Multi-Format Question Paper Export

Export generated assessments into multiple formats.

- **PDF:** Professionally formatted question papers with branding, questions, options, and answer keys using ReportLab.
- **CSV:** Structured question data compatible with spreadsheet applications.
- **TXT:** Simple text-based export for easy sharing and editing.

---

## 🛠️ Technology Stack

| Category | Technologies |
|---|---|
| Frontend | HTML5, Vanilla CSS, JavaScript |
| Backend | Python, FastAPI |
| LLM | Groq API |
| Language Models | Llama 3.3 70B Versatile, Llama 3.1 8B Instant |
| Embeddings | Sentence Transformers |
| Vector Database | FAISS |
| Keyword Retrieval | BM25Okapi |
| Retrieval Optimization | Reciprocal Rank Fusion |
| Database | MongoDB |
| PDF Processing | PyMuPDF |
| PDF Generation | ReportLab |
| Authentication | JWT |
| Development Tools | Git, GitHub, VS Code |

---

## 🏗️ System Architecture

```text
                 USER
                   |
                   v
          EXAMIQ WEB INTERFACE
         HTML5 + CSS + JavaScript
                   |
                   v
             FASTAPI BACKEND
                   |
          +--------+---------+
          |                  |
          v                  v
    DOCUMENT INPUT       TOPIC INPUT
          |                  |
          v                  v
    PDF PROCESSING      KNOWLEDGE STUDIO
          |
          v
     TEXT CHUNKING
          |
          v
    HYBRID RETRIEVAL
          |
     +----+----+
     |         |
     v         v
   FAISS      BM25
     |         |
     +----+----+
          |
          v
     RRF FUSION
          |
          v
    GROQ LLM API
          |
          v
   QUESTION GENERATION
          |
          v
   VALIDATION & FORMATTING
          |
          v
   QUIZ / QUESTION PAPER
          |
          v
    PDF / CSV / TXT EXPORT
```

---

## 📁 Project Structure

```text
ExamiQ/
│
├── server.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
│
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── core/
│   ├── pdf_processor.py
│   ├── text_chunker.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── bm25_retriever.py
│   ├── rrf_fusion.py
│   ├── rag_pipeline.py
│   ├── groq_client.py
│   ├── question_generator.py
│   └── quiz_engine.py
│
├── prompts/
│   ├── pdf_question_prompt.py
│   ├── knowledge_question_prompt.py
│   └── dsa_question_prompt.py
│
├── utils/
│   ├── auth.py
│   ├── rate_limiter.py
│   ├── request_logger.py
│   ├── validators.py
│   ├── exporters.py
│   └── helpers.py
│
└── faiss_indexes/
```

---

## 🚀 Installation and Setup

### Prerequisites

- Python 3.10 or later (depending on dependency compatibility).
- Git.
- Groq API key.
- MongoDB connection (if using MongoDB features).

### 1. Clone the Repository

```bash
git clone https://github.com/jayadevharees5-creator/ExamiQ.git
cd ExamiQ
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

**macOS / Linux**

```bash
source venv/bin/activate
```

**Windows**

```bash
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root.

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
MONGODB_URI=your_mongodb_connection_string
```

Get your Groq API key:

https://console.groq.com/keys

**Security:** Never upload your `.env` file or expose API keys in frontend JavaScript or public repositories.

### 5. Run the Application

```bash
python server.py
```

Alternatively, if `server.py` exposes a FastAPI application named `app`:

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Open the Application

```text
http://localhost:8000
```

---

## 🎯 Project Objectives

- Simplify the process of creating educational assessments.
- Reduce the time required for manual question-paper preparation.
- Generate context-aware questions from academic documents.
- Support different question formats and difficulty levels.
- Improve assessment quality through hybrid information retrieval.
- Provide interactive learning and programming practice.

## 🔮 Future Enhancements

- Personalized learning paths based on student performance.
- Advanced analytics and performance dashboards.
- More question-generation models and configurable AI providers.
- Support for additional document formats.
- Collaborative question banks for faculty members.
- Cloud deployment with scalable document and index storage.
- Integration with Learning Management Systems (LMS).

## 🌍 Educational Impact

ExamiQ aims to support **SDG 4 – Quality Education** by making assessment creation more efficient, accessible, and flexible for educators and learners.

## 👨‍💻 Development

ExamiQ is developed as an AI-powered educational technology project combining Large Language Models, Retrieval-Augmented Generation, information retrieval, and modern web development.

## 📄 License

Choose and add an appropriate open-source license before publishing this project for public reuse.

---

**ExamiQ – Turn Knowledge into Questions. Build Smarter Assessments.**
