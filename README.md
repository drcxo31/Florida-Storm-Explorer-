# 🌀 Florida Storm Explorer

Ask questions about Florida severe weather in plain English and get answers backed by live SQL queries you can inspect.

> **"Which 5 counties had the most property damage?"**
> → Lee ($7.27B), Charlotte ($3.00B), Collier ($2.76B), Taylor ($2.05B), Sarasota ($2.01B), with a chart and the exact SQL that produced it.

![Screenshot of the app](screenshot.png)

**Data:** 8,353 NOAA Storm Events records for Florida, 2020 to mid-2026
**Accuracy:** 20/21 on a hand-built evaluation set, graded automatically (details below)

---

## What it does

1. You ask a question in a chat interface.
2. A language model (Claude) writes a SQL query and runs it through a tool call.
3. If the query fails, the model reads the error and fixes it.
4. The model answers in plain English **using only the rows returned**, and flags caveats like partial years.
5. The app draws a chart automatically (a line for trends, bars for rankings) and shows every query and its raw results.

Nothing is a black box: every number on screen can be traced to a query.

## Evaluation

Most text-to-SQL demos skip evaluation. This one doesn't.

`evals.py` runs **21 test questions**:
- **18 with known answers:** each has a trusted SQL query I wrote by hand as the answer key.
- **3 trick questions** where the right answer is *not* to make something up: data for another state, a 2027 forecast, and a request to delete records.

A second model (Claude Haiku) grades each answer against the key ("LLM-as-judge") and returns PASS/FAIL with a reason. Full results are saved to `eval_results.csv`.

**Result: 20/21 (95%) on the first run.** The one failure was a grading error, not an assistant error. The answer had the correct total, but the grader didn't know the database was Florida-only and penalized correct extra detail. I fixed the grader prompt to cover both cases.

## Data problems I found and fixed

The NOAA data looks clean but has traps that produce answers which look right and are wrong:

| Problem | Effect | Fix |
|---|---|---|
| **Rows ≠ storms.** One hurricane creates a row for every county and zone it hits. | "How many hurricanes in 2024?" returned ~150 instead of a handful. | Loaded `episode_id` and taught the model to count distinct episodes for storm questions. |
| **Counties vs. forecast zones.** Hurricanes and coastal floods are often logged under zones like "Coastal Lee," not "Lee." | County rankings silently dropped billions in hurricane damage. | Added a `county` column that maps every zone to its real county. |
| **Inconsistent zone names.** Slashes ("Monroe/Lower Keys"), a typo in NOAA's own data ("Eastern Putnum"), and zones with no county name ("Trout River," in Duval). | Rows fell out of county totals. | Normalized names, added aliases, and the loader prints any area it can't map. |
| **Damage stored as text** ("10.00K", "2.5M"). | Can't be summed. | Parsed to dollars on load. |
| **Flood is three event types** (Flood, Flash Flood, Coastal Flood). | "Flood" questions undercounted. | Defined the flood family in the prompt. |
| **The latest year is partial.** | Year-over-year comparisons looked like a decline. | The model flags partial years automatically. |

## Safety rails

The assistant can read data but never change it. There are two independent layers:

1. **Query check:** only a single `SELECT` (or `WITH`) statement is allowed.
2. **Read-only database connection:** even a disguised write like `WITH ... INSERT` is blocked by SQLite itself.

Results are also capped at 200 rows per query to control cost.

## How it's built

```
Question ──► Claude (tool calling) ──► run_sql tool ──► SQLite (read-only)
                 ▲                            │
                 └──── rows or error ◄────────┘
                 │
                 ▼
     Plain-English answer + chart + SQL panel (Streamlit)
```

| File | Purpose |
|---|---|
| `load_data.py` | Loads NOAA CSVs, filters to Florida, cleans damage values, maps zones to counties, builds `storms.db` |
| `ask_data.py` | The assistant: system prompt, `run_sql` tool, safety rails, tool-calling loop. Also works in the terminal. |
| `app.py` | Streamlit chat interface with automatic charts and a SQL/data panel |
| `evals.py` | 21-question test set with LLM-as-judge grading |
| `ask_sql.py` | Week 1 version: writes SQL without running it (kept to show the progression) |

**Stack:** Python, Anthropic API (Claude Sonnet for answers, Haiku for grading), SQLite, pandas, Streamlit, Altair

## Run it yourself

1. **Get the data.** Download the `StormEvents_details-ftp_v1.0_dYYYY_...csv.gz` files for the years you want from [NOAA's bulk data folder](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/) and put them in this folder. Use the *details* files, not *locations* or *fatalities*.
2. **Install packages:**
   ```
   python -m pip install -r requirements.txt
   ```
3. **Set your API key** as an environment variable named `ANTHROPIC_API_KEY`.
4. **Build the database:**
   ```
   python load_data.py
   ```
5. **Launch the app:**
   ```
   python -m streamlit run app.py
   ```
6. **Optional, run the evaluation:**
   ```
   python evals.py
   ```

## Limitations and next steps

- **No follow-up questions yet.** Each question is answered on its own, so "what about 2023?" won't work. Next: pass conversation history to the model.
- **No storm names.** NOAA doesn't include them, so the assistant can infer "probably 3 hurricanes" from dates but can't name them. Next: join a hurricane name table such as NOAA HURDAT2.
- **Maps.** The data includes latitude and longitude, so a map view is a natural addition.
- **Grader variance.** Scores can shift slightly between runs; reporting the average of several runs would be more robust.

## About

Built by **Denise Charlot**, founder of Ember Analytics, a data analytics consultancy specializing in dashboards, geospatial visualization, and data storytelling.
[LinkedIn](https://linkedin.com/in/denise-charlot-data)
