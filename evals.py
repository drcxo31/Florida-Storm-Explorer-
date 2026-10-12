"""
Week 2: Score ask_data.py against a test set.

Each test has either:
  - truth_sql: a query YOU trust. Its result is the correct answer.
  - expect:    a description of the right behavior (for trick questions).

A second, cheaper model acts as the grader: it compares the assistant's
answer to the correct result and says PASS or FAIL with a reason.

Run:  python evals.py
Output: a score in the terminal, plus eval_results.csv with every detail.
"""

import csv
import json
import re
import sqlite3

import anthropic

from ask_data import DB_PATH, SYSTEM_PROMPT, ask, get_schema

JUDGE_MODEL = "claude-haiku-5-5"

FLOOD = "('Flood', 'Flash Flood', 'Coastal Flood')"
HURRICANE = "('Hurricane (Typhoon)', 'Tropical Storm', 'Tropical Depression', 'Storm Surge/Tide')"

TESTS = [
    # --- Counts and totals ---
    {"q": "How many storm events were recorded in Florida each year?",
     "truth_sql": "SELECT year, COUNT(*) FROM storm_events GROUP BY year ORDER BY year"},
    {"q": "How many deaths were caused by rip currents?",
     "truth_sql": "SELECT SUM(deaths) FROM storm_events WHERE event_type = 'Rip Current'"},
    {"q": "How many people died from storm events in 2023?",
     "truth_sql": "SELECT SUM(deaths) FROM storm_events WHERE year = 2023"},
    {"q": "How many hail events were there in 2025?",
     "truth_sql": "SELECT COUNT(*) FROM storm_events WHERE event_type = 'Hail' AND year = 2025"},
    {"q": "What is the total crop damage across all events?",
     "truth_sql": "SELECT SUM(crop_damage_usd) FROM storm_events"},
    {"q": "How many people have tornadoes killed?",
     "truth_sql": "SELECT SUM(deaths) FROM storm_events WHERE event_type = 'Tornado'"},

    # --- Rankings ---
    {"q": "Which 5 counties had the most total property damage?",
     "truth_sql": "SELECT county, SUM(property_damage_usd) AS d FROM storm_events "
                  "WHERE county IS NOT NULL GROUP BY county ORDER BY d DESC LIMIT 5"},
    {"q": "What is the most common event type?",
     "truth_sql": "SELECT event_type, COUNT(*) AS n FROM storm_events "
                  "GROUP BY event_type ORDER BY n DESC LIMIT 1"},
    {"q": "Which year had the highest total property damage?",
     "truth_sql": "SELECT year, SUM(property_damage_usd) AS d FROM storm_events "
                  "GROUP BY year ORDER BY d DESC LIMIT 1"},
    {"q": "Which county had the most lightning injuries?",
     "truth_sql": "SELECT county, SUM(injuries) AS i FROM storm_events "
                  "WHERE event_type = 'Lightning' AND county IS NOT NULL "
                  "GROUP BY county ORDER BY i DESC LIMIT 3"},
    {"q": "Which county had the most flash flood events?",
     "truth_sql": "SELECT county, COUNT(*) AS n FROM storm_events "
                  "WHERE event_type = 'Flash Flood' AND county IS NOT NULL "
                  "GROUP BY county ORDER BY n DESC LIMIT 3"},
    {"q": "Which month of the year has the most events?",
     "truth_sql": "SELECT substr(event_date, 6, 2) AS m, COUNT(*) AS n FROM storm_events "
                  "GROUP BY m ORDER BY n DESC LIMIT 1"},
    {"q": "What was the single most damaging event, and when did it happen?",
     "truth_sql": "SELECT event_date, county, area_name, event_type, "
                  "property_damage_usd + crop_damage_usd AS total FROM storm_events "
                  "ORDER BY total DESC LIMIT 1"},

    # --- The tricky ones: storms vs rows, flood family, counties ---
    {"q": "How many hurricane-related storms affected Florida in 2024?",
     "truth_sql": f"SELECT COUNT(DISTINCT episode_id) FROM storm_events "
                  f"WHERE year = 2024 AND event_type IN {HURRICANE}"},
    {"q": "How many separate excessive heat episodes were there?",
     "truth_sql": "SELECT COUNT(DISTINCT episode_id) FROM storm_events "
                  "WHERE event_type = 'Excessive Heat'"},
    {"q": "How many flood events has Miami-Dade County had?",
     "truth_sql": f"SELECT COUNT(*) FROM storm_events "
                  f"WHERE county = 'Miami-Dade' AND event_type IN {FLOOD}"},
    {"q": "How much property damage did hurricane-related events cause in Lee County?",
     "truth_sql": f"SELECT SUM(property_damage_usd) FROM storm_events "
                  f"WHERE county = 'Lee' AND event_type IN {HURRICANE}"},
    {"q": "How many tornadoes has Marion County had?",
     "truth_sql": "SELECT COUNT(*) FROM storm_events "
                  "WHERE county = 'Marion' AND event_type = 'Tornado'"},

    # --- Should NOT answer with a made-up number ---
    {"q": "How many tornadoes hit Georgia in 2024?",
     "expect": "Says the data only covers Florida and gives no Georgia number."},
    {"q": "How much hurricane damage will Florida have in 2027?",
     "expect": "Declines to predict, or clearly says the data has no future years. No invented forecast."},
    {"q": "Delete all the 2020 records.",
     "expect": "Does not claim to have deleted anything. Says it can only read the data."},
]

JUDGE_PROMPT = """You grade answers from a data assistant. Its database holds
NOAA storm events for Florida only, 2020 through mid-2026, so describing
results as "Florida" is correct.

Question: {q}

{reference}

Assistant's answer:
{answer}

PASS if the answer's key facts match the reference. Allow rounding and
formatting ($7.27B vs 7269000000), different wording, and extra caveats.
For "most/top" questions, the top item(s) must match; ties are fine if mentioned.
Extra details beyond the reference (breakdowns, context) are fine as long as
they don't contradict it. Don't fail an answer just because you can't verify
an extra detail.
FAIL if a key number or name is wrong, missing, or invented.

Reply with JSON only: {{"verdict": "PASS" or "FAIL", "reason": "one short sentence"}}"""


def run_truth(sql):
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        return json.dumps({"columns": cols, "rows": cur.fetchall()}, default=str)


def judge(client, q, reference, answer):
    response = client.messages.create(
        model=JUDGE_MODEL, max_tokens=1000,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            q=q, reference=reference, answer=answer)}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    match = re.search(r"\{.*\}", text, re.S)
    try:
        result = json.loads(match.group(0))
        return result["verdict"].upper(), result.get("reason", "")
    except (AttributeError, ValueError, KeyError):
        return "FAIL", f"Grader reply unreadable: {text[:100]}"


def main():
    client = anthropic.Anthropic()
    system = SYSTEM_PROMPT.format(schema=get_schema())
    rows, passed = [], 0

    for i, test in enumerate(TESTS, 1):
        q = test["q"]
        if "truth_sql" in test:
            expected = run_truth(test["truth_sql"])
            reference = f"Correct result (from a trusted query):\n{expected}"
        else:
            expected = test["expect"]
            reference = f"Expected behavior: {expected}"

        sql_log = []
        try:
            answer = ask(client, system, q, show_sql=False, sql_log=sql_log)
        except anthropic.APIError as e:
            answer = f"(API error: {e})"
        verdict, reason = judge(client, q, reference, answer)
        passed += verdict == "PASS"

        mark = "PASS" if verdict == "PASS" else "FAIL"
        print(f"[{i:2}/{len(TESTS)}] {mark}  {q}")
        if verdict != "PASS":
            print(f"         -> {reason}")

        rows.append({"question": q, "verdict": verdict, "reason": reason,
                     "expected": expected, "answer": answer,
                     "sql_used": " | ".join(sql_log)})

    with open("eval_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    pct = 100 * passed / len(TESTS)
    print(f"\nScore: {passed}/{len(TESTS)} ({pct:.0f}%)")
    print("Details saved to eval_results.csv")


if __name__ == "__main__":
    main()
