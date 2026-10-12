# 2-Minute Demo Script: Florida Storm Explorer

**Before recording**
- Start the app, press Ctrl+Shift+R, and click "Clear chat."
- Zoom the browser to 110–125% so text is readable in the video.
- Run each question once beforehand so you know what will happen (answers vary slightly).
- Record with Windows' built-in Snipping Tool (Record button) or OBS (free). Voiceover is optional; on-screen captions work too.

---

**0:00–0:15 · The hook**
> "This is Florida Storm Explorer. You ask questions about six years of NOAA severe weather data in plain English, and it answers using live SQL queries you can check."

*Show the empty app with the sidebar visible.*

**0:15–0:40 · First question: rankings**
Click **"Which 5 counties had the most property damage?"**
> "It wrote a query, ran it, and answered with a chart. Lee County is at the top. That's Hurricane Ian."

**0:40–1:00 · Show your work**
Open **"Show SQL and data."**
> "Every number traces back to a query. Here's the exact SQL and the rows it returned. Nothing is a black box."

**1:00–1:25 · The data trap**
Click **"How many hurricanes affected Florida in 2024?"**
> "This one is tricky. NOAA logs one row per county a storm hits, so counting rows gives you about 150 'hurricanes.' The assistant counts distinct storms instead, and even notices same-day records are probably the same hurricane."

**1:25–1:40 · Safety**
Type: **"Delete all the 2020 records."**
> "It can only read. The query is checked, and the database itself is read-only, so even a disguised write gets blocked."

**1:40–2:00 · Credibility close**
Show `eval_results.csv` or the terminal score from `evals.py`.
> "I tested it on 21 questions with known answers, including trick questions, and it scored 95%. The full write-up is in the README. Thanks for watching."

---

**Tips**
- If an answer comes out awkward, just re-record. Nobody sees the takes.
- Put the video on YouTube (unlisted is fine) or Loom, link it at the top of the README, and post it on LinkedIn.
