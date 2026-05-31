"""
Streamlit frontend for the AI News Summarizer.

Three tabs:
  1. Summarize  - analyze a single topic (summary + sentiment + entities + export)
  2. Compare    - analyze multiple topics side by side
  3. History    - browse previously generated summaries (from SQLite)

Run with:
    streamlit run app.py
"""

import datetime as _dt

import streamlit as st

import cache
from summarizer import analyze_topic, compare_topics
from exporters import to_markdown, to_pdf


# --------------------------------------------------------------------------- #
# Page config + light styling
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="AI News Summarizer", page_icon="📰", layout="wide")

st.markdown(
    """
    <style>
      .stTabs [data-baseweb="tab-list"] { gap: 8px; }
      .stTabs [data-baseweb="tab"] {
          padding: 8px 18px; border-radius: 8px 8px 0 0;
      }
      .sentiment-pill {
          display:inline-block; padding:4px 12px; border-radius:999px;
          font-weight:600; font-size:0.85rem;
      }
      .src-card {
          border:1px solid rgba(128,128,128,0.25); border-radius:10px;
          padding:10px 14px; margin-bottom:8px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📰 AI News Summarizer")
st.caption(
    "Search the web on any topic and get a structured brief with sentiment, "
    "key entities, comparison, history, and export — powered by Tavily + Mistral."
)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Settings")
    model = st.selectbox(
        "Model",
        ["mistral-small-2506", "mistral-large-latest", "open-mistral-nemo"],
        index=0,
    )
    max_results = st.slider("Number of sources", 3, 10, 5)
    temperature = st.slider("Creativity", 0.0, 1.0, 0.3, 0.1)
    use_cache = st.toggle("Use cache (saves API calls)", value=True)

    st.markdown("---")
    st.caption("Set TAVILY_API_KEY and MISTRAL_API_KEY in a .env file.")


# --------------------------------------------------------------------------- #
# Shared render helpers
# --------------------------------------------------------------------------- #
_SENTIMENT_COLORS = {
    "Positive": "#1b9e4b",
    "Negative": "#d62728",
    "Neutral": "#7f7f7f",
    "Mixed": "#b8860b",
}


def sentiment_pill(sentiment: dict):
    label = sentiment.get("label", "Neutral")
    color = _SENTIMENT_COLORS.get(label, "#7f7f7f")
    score = sentiment.get("score", 0.0)
    st.markdown(
        f'<span class="sentiment-pill" style="background:{color};color:white;">'
        f"{label} · {score:+.2f}</span>",
        unsafe_allow_html=True,
    )
    if sentiment.get("reason"):
        st.caption(sentiment["reason"])


def render_result(result: dict, show_export: bool = True, key_prefix: str = ""):
    if result.get("cached"):
        st.info("⚡ Loaded from cache (no API call used).", icon="⚡")

    st.subheader(result.get("headline", ""))
    sentiment_pill(result.get("sentiment", {}))

    st.markdown("#### Key Points")
    for b in result.get("bullets", []):
        st.markdown(f"- {b}")

    if result.get("takeaway"):
        st.markdown(f"> **Takeaway:** {result['takeaway']}")

    ent = result.get("entities", {})
    c1, c2, c3 = st.columns(3)
    c1.markdown("**👤 People**\n\n" + ("\n".join(f"- {x}" for x in ent.get("people", [])) or "—"))
    c2.markdown("**🏢 Organizations**\n\n" + ("\n".join(f"- {x}" for x in ent.get("organizations", [])) or "—"))
    c3.markdown("**📍 Locations**\n\n" + ("\n".join(f"- {x}" for x in ent.get("locations", [])) or "—"))

    if result.get("sources"):
        with st.expander(f"📚 Sources ({len(result['sources'])})"):
            for i, s in enumerate(result["sources"], 1):
                st.markdown(f"{i}. [{s['title']}]({s['url']})")

    if show_export:
        e1, e2 = st.columns(2)
        e1.download_button(
            "⬇️ Markdown",
            data=to_markdown(result),
            file_name="news_brief.md",
            mime="text/markdown",
            key=f"{key_prefix}_md",
            use_container_width=True,
        )
        try:
            e2.download_button(
                "⬇️ PDF",
                data=to_pdf(result),
                file_name="news_brief.pdf",
                mime="application/pdf",
                key=f"{key_prefix}_pdf",
                use_container_width=True,
            )
        except Exception:
            e2.button("PDF unavailable (install fpdf2)", disabled=True,
                      key=f"{key_prefix}_pdf_err", use_container_width=True)


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_summarize, tab_compare, tab_history = st.tabs(
    ["🔍 Summarize", "⚖️ Compare", "🕘 History"]
)


# ---- Tab 1: Summarize ----------------------------------------------------- #
with tab_summarize:
    topic = st.text_input(
        "Topic",
        placeholder="e.g. latest developments in AI regulation",
        key="single_topic",
    )
    if st.button("Summarize", type="primary", key="run_single"):
        if not topic.strip():
            st.warning("Please enter a topic.")
        else:
            try:
                with st.spinner(f"Analyzing “{topic}” ..."):
                    res = analyze_topic(
                        topic, max_results=max_results, model=model,
                        temperature=temperature, use_cache=use_cache,
                    )
                st.session_state["single_result"] = res
            except EnvironmentError as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"Something went wrong: {e}")

    if "single_result" in st.session_state:
        st.divider()
        render_result(st.session_state["single_result"], key_prefix="single")


# ---- Tab 2: Compare ------------------------------------------------------- #
with tab_compare:
    st.caption("Enter 2–3 topics to analyze side by side.")
    cc = st.columns(3)
    t1 = cc[0].text_input("Topic A", key="cmp_a", placeholder="e.g. Tesla")
    t2 = cc[1].text_input("Topic B", key="cmp_b", placeholder="e.g. Rivian")
    t3 = cc[2].text_input("Topic C (optional)", key="cmp_c")

    if st.button("Compare", type="primary", key="run_compare"):
        topics = [t for t in (t1, t2, t3) if t.strip()]
        if len(topics) < 2:
            st.warning("Enter at least two topics to compare.")
        else:
            try:
                with st.spinner("Analyzing topics ..."):
                    st.session_state["compare_results"] = compare_topics(
                        topics, max_results=max_results, model=model,
                        temperature=temperature,
                    )
            except Exception as e:  # noqa: BLE001
                st.error(f"Something went wrong: {e}")

    if "compare_results" in st.session_state:
        st.divider()
        results = st.session_state["compare_results"]
        cols = st.columns(len(results))
        for col, res in zip(cols, results):
            with col:
                st.markdown(f"### {res['topic']}")
                render_result(res, show_export=False, key_prefix=f"cmp_{res['topic'][:10]}")


# ---- Tab 3: History ------------------------------------------------------- #
with tab_history:
    h1, h2 = st.columns([3, 1])
    h1.caption("Previously generated summaries (stored locally in SQLite).")
    if h2.button("🗑️ Clear history"):
        cache.clear_history()
        st.success("History cleared.")

    history = cache.get_history(limit=50)
    if not history:
        st.info("No history yet. Generate a summary in the Summarize tab.")
    else:
        for item in history:
            ts = _dt.datetime.fromtimestamp(item.get("_created_at", 0))
            with st.expander(
                f"{item.get('_topic', '')}  ·  {ts:%Y-%m-%d %H:%M}  ·  {item.get('_model','')}"
            ):
                render_result(item, key_prefix=f"hist_{item.get('_created_at')}")