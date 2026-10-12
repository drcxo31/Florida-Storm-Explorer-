"""
Week 3: Chat interface for the Florida storm data assistant.

Before running:  pip install streamlit
Run:             streamlit run app.py
(It opens in your browser. Stop it with Ctrl+C in the terminal.)
"""

import json

import altair as alt
import anthropic
import pandas as pd
import streamlit as st

from ask_data import SYSTEM_PROMPT, ask, get_schema

st.set_page_config(page_title="Florida Storm Explorer", page_icon="🌀")

EXAMPLES = [
    "Which 5 counties had the most property damage?",
    "How many hurricanes affected Florida in 2024?",
    "Storm events per year",
    "Which counties have the most tornadoes?",
]
LINE_X = {"year", "month", "m", "event_date"}


@st.cache_resource
def setup():
    return anthropic.Anthropic(), SYSTEM_PROMPT.format(schema=get_schema())


def main_result(trace):
    """Pick the query result to chart: the successful one with the most rows."""
    good = [t for t in trace if not t["error"]]
    if not good:
        return None
    frames = []
    for t in good:
        data = json.loads(t["result"])
        frames.append(pd.DataFrame(data["rows"], columns=data["columns"]))
    return max(frames, key=len)


def show_chart(df):
    if df is None or len(df) < 2 or df.shape[1] < 2:
        return
    x = df.columns[0]
    if str(x).lower().endswith("id"):   # ID numbers make meaningless charts
        return
    numeric =[c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric:
        return
    y = numeric[0]
    plot = pd.DataFrame({"label": df[x].astype(str), "value": df[y]}).head(25)

    if str(x).lower() in LINE_X:
        chart = alt.Chart(plot).mark_line(point=True).encode(
            x=alt.X("label:O", title=x, sort=None),
            y=alt.Y("value:Q", title=y),
            tooltip=["label", "value"],
        )
    else:
        chart = alt.Chart(plot).mark_bar().encode(
            x=alt.X("value:Q", title=y),
            y=alt.Y("label:N", title=x, sort="-x"),
            tooltip=["label", "value"],
        )
    st.altair_chart(chart, width="stretch")


def render_answer(answer, trace):
    # Streamlit reads $...$ as math, so escape dollar signs
    st.markdown(answer.replace("$", "\\$"))
    show_chart(main_result(trace))
    if trace:
        with st.expander("Show SQL and data"):
            for t in trace:
                st.code(t["sql"], language="sql")
                if t["error"]:
                    st.caption(f"⚠️ {t['result']} (the assistant retried)")
                else:
                    data = json.loads(t["result"])
                    st.dataframe(pd.DataFrame(data["rows"], columns=data["columns"]),
                                 hide_index=True)


# ---------- Page ----------
st.title("🌀 Florida Storm Explorer")
st.caption("Ask questions about NOAA storm events in Florida, 2020 to mid-2026. "
           "Answers come from live SQL queries, which you can inspect.")

with st.sidebar:
    st.subheader("Try asking")
    for ex in EXAMPLES:
        if st.button(ex, width="stretch"):
            st.session_state.pending = ex
    st.divider()
    st.markdown(
        "**How it works**\n\n"
        "1. A language model writes SQL for your question\n"
        "2. The query runs on a read-only database\n"
        "3. The model answers using only the returned rows\n\n"
        "Each question is answered on its own, so include full details "
        "(\"tornadoes in Marion County in 2024\", not \"what about 2024?\")."
    )
    if st.button("Clear chat", width="stretch"):
        st.session_state.messages = []
        st.rerun()

try:
    client, system = setup()
except Exception as e:
    st.error(f"Setup failed: {e}. Check that storms.db exists and your API key is set.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_answer(msg["content"], msg["trace"])

question = st.chat_input("Ask about Florida storms...")
if "pending" in st.session_state:
    question = st.session_state.pop("pending")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        trace = []
        with st.spinner("Querying the data..."):
            try:
                answer = ask(client, system, question, show_sql=False, trace=trace)
            except anthropic.APIError as e:
                answer = f"Sorry, the model request failed: {e}"
        render_answer(answer, trace)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "trace": trace})
