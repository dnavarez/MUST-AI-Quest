# Inbox Helper

Groups incoming messages by what each sender wants and drafts a short
reply for each one, for a human to review. It never sends anything.
See `docs/intent.md` for the full design.

## Current status

Implemented so far (as Python modules; there is no command-line
program yet):
- loading and validating a CSV file of messages (`loader.py`);
- rule-based intent classification (`classifier.py`) and an evaluation
  script (`evaluate.py`);
- a detector for text that looks like instructions aimed at the tool
  (`possible_instruction_override`, `safety.py`);
- reply drafting (`drafter.py`): fixed templates with `[PLACEHOLDERS]`,
  no text copied from the message, guard checks, a neutral fallback for
  messages with the override warning, and no draft for empty messages.
  Every draft is `pending_review`; nothing is ever sent.

**Not implemented yet:** the review files (`review.md`, `review.csv`),
review decisions and the `finalize` step, and the command-line program.

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
