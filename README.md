# Inbox Helper

Groups incoming messages by what each sender wants and drafts a short
reply for each one, for a human to review. It never sends anything.
See `docs/intent.md` for the full design.

## Current status

Implemented so far:
- the `draft` command, which writes `review.md` (to read) and
  `review.csv` (for decisions) — see *Drafting replies for review*;
- loading and validating a CSV file of messages (`loader.py`);
- rule-based intent classification (`classifier.py`) and an evaluation
  script (`evaluate.py`);
- a detector for text that looks like instructions aimed at the tool
  (`possible_instruction_override`, `safety.py`);
- reply drafting (`drafter.py`): fixed templates with `[PLACEHOLDERS]`,
  no text copied from the message, guard checks, a neutral fallback for
  messages with the override warning, and no draft for empty messages.
  Every draft is `pending_review`; nothing is ever sent.

**Not implemented yet:** recording review decisions and the `finalize`
step (Stage 4), and sample data with worked examples (Stage 5).

The override detector is simple pattern matching: it can miss attacks
and can flag harmless text, so a warning only means "review carefully".
A first baseline accuracy has been measured, and the classifier has
since been tuned using the development set only; see below.

## Setup

Requires Python 3 and pytest. This project uses a local virtual
environment in `.venv` (Python 3.14.7 and pytest 9.1.1 at the time of
writing). There are no other dependencies.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest
```

## Input format

A UTF-8 CSV file with a header row containing these columns:

| Column    | Meaning                         |
|-----------|---------------------------------|
| `id`      | a unique label for the message  |
| `sender`  | who sent it                     |
| `subject` | the subject line                |
| `body`    | the message text                |

Extra columns are ignored. An empty file, or a file missing any of the
four columns, is rejected with an error that says what is wrong.

## Drafting replies for review

From the project folder:

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper draft path/to/messages.csv --out output/
```

This writes two files and **sends nothing**:

- `output/review.md` — for reading. Messages grouped by intent, each
  with its warnings, the original text (shown as plain text), the
  keywords that matched, and the suggested draft or why there is none.
- `output/review.csv` — for decisions. One row per message with blank
  `decision`, `edited_draft` and `reviewer_note` columns. (Recording
  decisions and the `finalize` step are not implemented yet.)

Every draft has status `pending_review`. If `review.md` or `review.csv`
already exists in the output folder, the command stops without changing
them, because they may contain your review work; add `--overwrite` only
if you want to replace them. Invalid input stops with an error and
writes nothing. The `output/` folder is ignored by Git.

Message text is untrusted: in `review.md` it is always shown inside
code blocks (ids and senders as inline code), and in `review.csv`
cells that a spreadsheet could treat as a formula start with `'` —
except the `id` column, which is always written exactly as loaded
(surrounding spaces removed). The command also refuses to run when the input file is one of
the output files, even with `--overwrite`.

Message ids must not start with `=`, `+`, `-` or `@`, and must not
contain line breaks, control or invisible characters, unusual space
characters, or two spaces in a row; otherwise the command stops with
an error naming the row. Different ids can still look alike (for
example accented or full-width letters), and a spreadsheet program may
change ids such as `001` or `1E3` when opening `review.csv`, so check
ids carefully. See *Known limitations* under *Mandatory human review*
in `docs/intent.md`.

## Running the tests

From the project folder:

```bash
.venv/bin/python -m pytest -v
```

## Running the classification evaluation

Compares the classifier with the labelled messages in `data/` and prints
a Markdown report. This is a measurement, separate from the tests above;
it does not fail when accuracy is low.

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper.evaluate data/eval_dev.csv data/eval_test.csv
```

Results with human-reviewed labels:
- `docs/eval_dev_c1-c5_2026-10-23.md`: tuned classifier, dev set.
- `docs/eval_test_checkpoint_c1-c5_2026-10-23.md`: tuned classifier,
  frozen test set (one-time checkpoint).
- `docs/eval_post_review_2026-10-23.md`: untuned classifier, dev and
  test sets.

Earlier reports, kept as records (they used the AI-proposed labels
before review):
- `docs/eval_baseline_2026-10-23_corrected.md`: corrected report format.
- `docs/eval_baseline_2026-10-23.md`: the original report; same counts,
  but its breakdown did not add up.

The evaluation labels were human-reviewed by the author with AI
assistance. Results are preliminary: the classifier, the messages and
the first labels were produced with AI assistance.
