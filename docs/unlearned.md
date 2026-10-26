# What I unlearned

I came to this quest as a mobile developer and a beginner in Python.
I built Inbox Helper, a small command-line tool that drafts email
replies for human review, working AI-first with Claude Code (and
ChatGPT for the initial setup).

## 1. "The AI wrote it, so it probably works"

Before this project, this was partly my habit.

What the record shows: AI changes were logged as AI-generated, and
every commit went through a security and a code-quality review before
I approved its exact contents. Those reviews kept finding real
problems, including one that the AI had just introduced while fixing
an earlier finding (in `docs/quest_requirements.md`, 2026-10-26).
Review agents also broke the protected-file rules twice: one ran the
evaluation tests, which probably read the frozen evaluation data
(unchanged), and a later one's wildcard command read protected test
files. Both are recorded in the log, and the rules were tightened each
time.

## 2. "Tests pass, so the app works"

Before this project, this was partly my habit.

What the record shows: the permitted test suite passed (785 tests),
but I ran the whole flow myself for the first time only after v1 was
finished (2026-10-25). I felt relieved when it worked. The output
showed "approved" replies still containing `[PLACEHOLDERS]`, a
complaint (`demo-12`) filed as "unclear", a repeated "No draft. No
draft:", and escaped `\.` in the plain-text view. On Day 1, an audit
also found an evaluation report whose numbers were all correct but
whose parts did not add up.
Seeing it run taught me nothing beyond the relief. What I would do
differently: run the app myself at the end of each stage, and ask the
AI to demonstrate the working app sooner.

## 3. "Keep tuning until the score looks good"

Before this project, this was my habit.

What the record shows: the rules were tuned (the AI did the coding; I
made the decisions) on the development set only, and the frozen test
set was scored only once after tuning. Strict accuracy rose from 16/26
to 20/26 on development, but only from 13/24 to 14/24 on test (both
with the reviewed labels), so most of the gain did not transfer. I
reported that instead of tuning further, and left the `demo-12` miss
visible rather than adding a rule just for it.

## 4. "Build everything, then check"

Before this project, this was my habit.

What the record shows: I worked in small, separately approved stages
(Stages 1–5, then the human code review), with a plan I approved
before each stage. Two caveats: Stages 1 and 2 were committed
together, and I ran the app myself only at the end.

## What I would keep doing

Working in small stages, with my approval before each one; having
independent security and code-quality reviews; and logging what the
AI did separately from my own decisions.
