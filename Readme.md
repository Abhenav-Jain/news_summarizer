# 📰 AI News Summarizer

A general-purpose, production-minded news summarizer. Enter any topic and it
searches the web (Tavily), then uses Mistral to produce a structured brief with
**sentiment analysis**, **key-entity extraction**, **topic comparison**,
**history**, and **PDF/Markdown export** — all on free API tiers.

## Features

- **🔍 Summarize any topic** — headline, key bullets, and a takeaway.
- **😀 Sentiment analysis** — label (Positive/Neutral/Negative/Mixed) + score.
- **🏷️ Key entities** — people, organizations, and locations, auto-extracted.
- **⚖️ Compare topics** — analyze 2–3 topics side by side.
- **🕘 History** — every summary saved locally in SQLite, browsable anytime.
- **⚡ Smart caching** — repeated queries are served from cache, saving API calls
  (stays on free tiers). 6-hour freshness window.
- **⬇️ Export** — download any brief as Markdown or PDF.
- **🧩 Single LLM call** — summary + sentiment + entities come back together,
  so it's one request instead of three (cheaper and faster).

## Project structure

```
news_summarizer/
├── app.py            # Streamlit UI (Summarize / Compare / History tabs)
├── summarizer.py     # Core pipeline: search -> analyze -> structured result
├── cache.py          # SQLite cache + history store
├── exporters.py      # Markdown and PDF export
├── requirements.txt
├── .env.example      # Template for API keys
├── .gitignore
└── README.md
```

## Setup

1. Create and activate a virtual environment:

   **Windows (PowerShell):**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   **macOS / Linux:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and add your keys (free tiers available at
   tavily.com and console.mistral.ai):
   ```
   TAVILY_API_KEY=...
   MISTRAL_API_KEY=...
   ```

## Run

**Streamlit app:**
```bash
streamlit run app.py
```
Opens at http://localhost:8501

**Command line (quick test):**
```bash
python summarizer.py "latest developments in AI regulation"
```

## How caching keeps it cheap

Each (topic + model + source-count) combination is hashed and stored in
`news_cache.db`. If you re-run the same query within 6 hours, the result is
returned instantly with **no API call**. Toggle this off in the sidebar if you
always want fresh results.

## Notes

- `news_cache.db` and `.env` are gitignored — your keys and local data stay private.
- PDF export uses `fpdf2` (pure Python — no system dependencies).