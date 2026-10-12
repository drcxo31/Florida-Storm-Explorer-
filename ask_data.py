"""
Week 2: Ask a question -> model writes SQL -> runs it (read-only) -> answers
in plain English. If a query fails, the error goes back to the model to fix.

Run:  python ask_data.py "Which county had the most lightning injuries?"
      python ask_data.py            (interactive: keep asking until blank line)
"""

import json
import re
import sqlite3
import sys

import anthropic

MODEL = "claude-sonnet-5-5"
DB_PATH = "storms.db"
MAX_ROWS = 200      # most rows ever sent back to the model
MAX_STEPS = 6       # most back-and-forth rounds per question


def get_schema():
    with sqlite3.connect(DB_PATH) as conn:
        cols = conn.execute("PRAGMA table_info(storm_events)").fetchall()
        sample = conn.execute("SELECT * FROM storm_events LIMIT 3").fetchall()
        types = [r[0] for r in conn.execute(
            "SELECT DISTINCT event_type FROM storm_events ORDER BY 1")]
        years = conn.execute("SELECT MIN(year), MAX(year) FROM storm_events").fetchone()
    col_lines = "\n".join(f"  {c[1]} ({c[2]})" for c in cols)
    return (
        f"Table: storm_events (Florida, {years[0]}-{years[1]})\nColumns:\n{col_lines}\n\n"
        "Sample rows:\n" + "\n".join(str(r) for r in sample) + "\n\n"
        f"Valid event_type values: {', '.join(types)}"
    )


SYSTEM_PROMPT = """You answer questions about NOAA storm events in Florida by
querying a SQLite database with the run_sql tool.

{schema}

Data notes:
- Each row is ONE area's record, not one storm. A single hurricane creates
  many rows. Rows from the same storm share an episode_id. For "how many
  storms/hurricanes", count DISTINCT episode_id; for local impacts, count rows.
- county is the real Florida county (e.g. 'Lee'), already mapped from forecast
  zones like 'Coastal Lee'. Use county, not area_name, for county questions.
  county is NULL for marine areas.
- "Flood" means 'Flood', 'Flash Flood', and 'Coastal Flood' unless one is named.
- "Hurricane-related" means 'Hurricane (Typhoon)', 'Tropical Storm',
  'Tropical Depression', 'Storm Surge/Tide'.
- Damage columns are US dollars. event_date is YYYY-MM-DD text.
- The latest year is partial. Say so when comparing years.

How to answer:
- Always get numbers from run_sql. Never guess or use outside knowledge.
- If a query errors, read the error, fix the SQL, and try again.
- Answer in 1-3 plain sentences. Format money like $1.2M or $450K.
- Mention any caveat that changes how the number should be read.
- Don't explain causes ("likely due to X") unless a query showed it.
- If the question is outside this data (other states, the future), say so."""

TOOLS = [{
    "name": "run_sql",
    "description": "Run one read-only SQLite SELECT query on storm_events. "
                   f"Returns up to {MAX_ROWS} rows as JSON.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A single SELECT query"}},
        "required": ["query"],
    },
}]


def run_sql(query):
    """Safety rails: SELECT only, one statement, read-only connection, row cap."""
    q = query.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", q):
        return "Error: only SELECT queries are allowed.", True
    if ";" in q:
        return "Error: send one query at a time.", True
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = conn.execute(q)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        conn.close()
    except sqlite3.Error as e:
        return f"SQL error: {e}", True
    result = {"columns": columns, "rows": rows[:MAX_ROWS]}
    if len(rows) > MAX_ROWS:
        result["note"] = f"Truncated to first {MAX_ROWS} rows."
    return json.dumps(result, default=str), False


def ask(client, system, question, show_sql=True, sql_log=None, trace=None):
    """trace (optional list) collects {"sql", "result", "error"} for each query."""
    messages = [{"role": "user", "content": question}]
    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL, max_tokens=4000, system=system,
            tools=TOOLS, messages=messages,
        )
        # Keep the full reply (including any thinking) in the history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text").strip()

        results = []
        for block in response.content:
            if block.type == "tool_use":
                sql = block.input.get("query", "")
                if sql_log is not None:
                    sql_log.append(" ".join(sql.split()))
                if show_sql:
                    print(f"  SQL: {' '.join(sql.split())}")
                output, is_error = run_sql(sql)
                if trace is not None:
                    trace.append({"sql": sql, "result": output, "error": is_error})
                if is_error and show_sql:
                    print(f"  -> {output} (retrying)")
                results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": output, "is_error": is_error,
                })
        messages.append({"role": "user", "content": results})
    return "(Stopped: too many steps without an answer.)"


def main():
    client = anthropic.Anthropic()
    system = SYSTEM_PROMPT.format(schema=get_schema())

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"\nQ: {question}")
        print(f"\nA: {ask(client, system, question)}\n")
        return

    print("Ask about Florida storm events (blank line to quit).")
    while True:
        question = input("\nQ: ").strip()
        if not question:
            break
        print(f"\nA: {ask(client, system, question)}")


if __name__ == "__main__":
    main()
