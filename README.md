# Inbox Helper

Groups incoming messages by what each sender wants and drafts a short
reply for each one, for a human to review. It never sends anything.
See `docs/intent.md` for the full design.

## Current status

Implemented so far:
- the `draft` command, which writes `review.md` (to read),
  `review.csv` (for decisions) and `review.manifest.json` (the input's
  fingerprint) — see *Drafting replies for review*;
- the `finalize` command, which checks a completed `review.csv`
  against the original input and writes the approved replies to
  `approved_unsent.md` and `approved_unsent.csv`, marked **not sent** —
  see *Finalizing reviewed replies*;
- loading and validating a CSV file of messages (`loader.py`);
- rule-based intent classification (`classifier.py`) and an evaluation
  script (`evaluate.py`);
- a detector for text that looks like instructions aimed at the tool
  (`possible_instruction_override`, `safety.py`);
- reply drafting (`drafter.py`): fixed templates with `[PLACEHOLDERS]`,
  no text copied from the message, guard checks, a neutral fallback for
  messages with the override warning, and no draft for empty messages.
  Every draft is `pending_review`; nothing is ever sent;
- 12 synthetic demo messages (`data/messages.csv`) and a worked example
  of the whole process (`examples/`) — see *Trying it with the sample
  data*;
- named acceptance tests for v1 criteria 1, 2, 3 and 5
  (`tests/test_acceptance.py`); criterion 4 is covered in
  `tests/test_cli.py`.

**Still open:** the human code and dependency review, which the author
does by hand (see *Acceptance criteria (v1)* in `docs/intent.md`). It is
not done yet.

The override detector is simple pattern matching: it can miss attacks
and can flag harmless text, so a warning only means "review carefully".
A first baseline accuracy has been measured, and the classifier has
since been tuned using the development set only; see below.

## Setup

Requires Python 3.11 or newer and pytest. This project uses a local virtual
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

This writes three files and **sends nothing**:

- `output/review.md` — for reading. Messages grouped by intent, each
  with its warnings, the original text (shown as plain text), the
  keywords that matched, and the suggested draft or why there is none.
- `output/review.csv` — for decisions. One row per message with blank
  `decision`, `edited_draft` and `reviewer_note` columns; fill them in
  and then run `finalize` (see below).
- `output/review.manifest.json` — the input file's name and SHA-256
  fingerprint, so `finalize` can check that a review is used with the
  exact input it was made from. Keep it next to `review.csv`.

Every draft has status `pending_review`. If any of the three files
already exists in the output folder (a broken symbolic link counts too),
the command stops without changing them, because they may contain your
review work; add `--overwrite` only if you want to replace them. Invalid
input stops with an error and writes nothing, and so does an input file
that changes while it is being read, or whose name contains control or
invisible characters. The `output/` folder is ignored by Git.

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

## Finalizing reviewed replies

After filling in `decision` (`approve`, `edit` or `reject`; blank means
still pending), `edited_draft` and `reviewer_note` in `review.csv`:

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper finalize path/to/messages.csv --review output/review.csv --out output/final/
```

This **sends nothing**. It checks the review and writes two files:

- `approved_unsent.md` — a report headed **NOT SENT**, with the review
  file's fingerprint and the input's fingerprint (or, for a review
  accepted with `--allow-unbound`, a note that the input binding was not
  checked), the counts for every decision, the ids of
  rejected and pending messages, and each approved or edited reply with
  its warnings.
- `approved_unsent.csv` — one row per approved or edited reply, with
  status `approved_unsent`. Copy replies from here into your own email
  tool and send them yourself. A `'` at the start of a cell was added
  so that a spreadsheet does not run it as a formula; it is not part of
  the reply.

Rejected and pending messages are never written as rows. Both files
are readable only by you (file mode `0600`).

**Checks before anything is written.** The review must be the review of
this exact input: `finalize` compares the input's SHA-256 with
`review.manifest.json` next to the review file, then checks every row of
`review.csv` against messages rebuilt from the input (see
`docs/intent.md`). A missing manifest (for example, a review folder made
before the manifest existed) is refused unless you add `--allow-unbound`;
the review is then only checked against the input's messages, and both
the command and `approved_unsent.md` say that the input binding was not
checked. `--allow-unbound` never accepts a damaged manifest or a
fingerprint that does not match. The manifest protects against mix-ups,
not deliberate tampering: it is not signed.

Existing `approved_unsent.*` files are only replaced with `--overwrite`.
The output files are never the input, the review file or the manifest,
even with `--overwrite`. Errors exit with code 2. They name files,
rows and reasons and are designed not to show message or reply text
(a short value pasted into an id or decision cell can still appear; see
*Known limitations* in `docs/intent.md`).

**If writing fails part-way.** The two files are written one after the
other, so an error can leave them incomplete. The error then starts
"The finalized files in … were left incomplete" and lists what is on
disk (new version written, removed, still from a previous run, not
written, or state could not be confirmed). Do not use those files; run
the command again with `--overwrite`. Temporary files are normally
removed; if one could not be removed, its path is printed (as part of
the error or as a `Note:` line). Such files are named
`.approved_unsent.*.tmp`, may contain reply text, and should be deleted.
If you interrupt the command (Ctrl-C) while it writes, Python's error
output lists the temporary files it could not remove, but there is no
summary of which output files were changed. In rare cases a temporary
file can also be left without being reported, so check the folder for
`.approved_unsent.*.tmp` files, delete any you find, and run again with
`--overwrite`.

## Trying it with the sample data

`data/messages.csv` holds 12 made-up messages (all addresses are
`@example.com`): one for each of the six main intents, an empty message
(which, like unclear messages, is `other_or_unclear`), a message with
two requests, an attempt to give the tool instructions, a late order, a
sender and subject that look like spreadsheet formulas, and one message
the classifier gets wrong. `examples/` shows the whole process for these
messages — the review files, the same review with decisions filled in,
and the finalized replies — and `examples/README.md` explains each file.

To run it yourself:

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper draft data/messages.csv --out output/demo/
```

Fill in some decisions in `output/demo/review.csv` (or copy
`examples/2_reviewed/review.csv` over it), then:

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper finalize data/messages.csv --review output/demo/review.csv --out output/demo/final/
```

Nothing is sent. `tests/test_examples.py` checks that the files in
`examples/` are exactly what the current code produces.

## Running the tests

From the project folder:

```bash
.venv/bin/python -m pytest -q --ignore=tests/test_eval_dataset.py --ignore=tests/test_evaluate.py
```

The two excluded files check the frozen evaluation data and the
evaluation script; they are run only as part of an evaluation, not as
routine tests.

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
