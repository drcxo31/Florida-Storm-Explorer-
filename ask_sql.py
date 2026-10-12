"""
Step 2 (Week 1): Question in -> model writes SQL -> print it.
No queries are executed yet -- you check the SQL by eye first.

Before running:
  pip install anthropic
  export ANTHROPIC_API_KEY="your-key-here"   (Windows: set ANTHROPIC_API_KEY=...)

Run:  python ask_sql.py            (runs the test questions)
      python ask_sql.py "your question here"
"""

import sqlite3
import sys

import anthropic

MODEL = "claude-sonnet-5-5"
DB_PATH = "storms.db"

TEST_QUESTIONS = [
    "How many storm events were recorded in Florida each year?",
    "Which 5 counties had the most total property damage?",
    "What are the most common event types?",
    "How many deaths were caused by rip currents?",
    "Which year had the highest total property damage?",
    "List all tornado events in Marion County.",
    "What was the single most damaging event, and when did it happen?",
    "How many hurricane-related events happened in 2024?",
    "Which month of the year has the most events overall?",
    "Average property damage per flood event by county, top 10.",
]


def get_schema(conn):
    """Describe the table so the model knows what it's working with."""
    cols = conn.execute("PRAGMA table_info(storm_events)").fetchall()
    col_lines = "\n".join(f"  {c[1]} ({c[2]})" for c in cols)
    sample = conn.execute("SELECT * FROM storm_events LIMIT 3").fetchall()
    event_types = [r[0] for r in conn.execute(
        "SELECT DISTINCT event_type FROM storm_events ORDER BY 1")]
    return (
        f"Table: storm_events\nColumns:\n{col_lines}\n\n"
        f"Sample rows:\n" + "\n".join(str(r) for r in sample) + "\n\n"
        f"Valid event_type values: {', '.join(event_types)}"
    )


SYSTEM_PROMPT = """You write SQLite queries for a table of NOAA storm events in Florida.

{schema}

Notes:
- area_type is 'county', 'forecast_zone', or 'marine'. Hurricanes, floods and
  heat are often logged by forecast zone, not county. For county questions,
  match area_name with LIKE and mention if zones may be missed.
- area_name is title case, e.g. 'Marion'. Forecast zones can have names like
  'Coastal Lee', so use LIKE '%Lee%' rather than exact matches.
- Damage columns are already in US dollars.
- event_date is text in YYYY-MM-DD format.
- Each row is ONE area's record, not one storm. A single hurricane creates
  many rows (one per county/zone hit). All rows from the same storm share an
  episode_id. When a question is about storms or "how many hurricanes",
  count DISTINCT episode_id; when it's about local impacts, count rows.
- "Flood" questions usually mean the flood family: 'Flood', 'Flash Flood',
  and 'Coastal Flood'. Include all three unless the user names one.
- "Hurricane-related" means: 'Hurricane (Typhoon)', 'Tropical Storm',
  'Tropical Depression', 'Storm Surge/Tide'.
- Return plain SQL with no comments.

Reply with ONE SELECT query only. No explanation, no markdown fences."""


def question_to_sql(client, schema, question):
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT.format(schema=schema),
        messages=[{"role": "user", "content": question}],
    )
    # The reply can include a "thinking" block before the answer,
    # so grab the first block that is actual text.
    text_blocks = [b.text for b in response.content if b.type == "text"]
    if not text_blocks:
        return "(No SQL returned -- try raising max_tokens)"
    sql = text_blocks[0].strip()
    # Strip fences in case the model adds them anyway
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    return sql


def main():
    conn = sqlite3.connect(DB_PATH)
    schema = get_schema(conn)
    client = anthropic.Anthropic()

    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else TEST_QUESTIONS
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}] {q}")
        print("-" * 60)
        print(question_to_sql(client, schema, q))


if __name__ == "__main__":
    main()
