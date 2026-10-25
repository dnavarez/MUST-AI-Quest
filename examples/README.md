# Worked example

A complete run of the Inbox Helper on the 12 synthetic demo messages in
`data/messages.csv`. All names, addresses and messages are made up
(`@example.com`). Nothing in this folder was sent, and the tool cannot
send anything.

The example was produced by the commands below. They give the same
bytes every time, and `tests/test_examples.py` fails if these files ever
differ from what the current code produces.

## 1. Draft — `1_draft/`

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper draft data/messages.csv --out examples/1_draft
```

- `review.md`: the report to read, grouped by intent, with warnings,
  the original messages (as plain text), the keywords that matched and
  each suggested draft. Every draft is `pending_review`.
- `review.csv`: the same messages with empty `decision`, `edited_draft`
  and `reviewer_note` columns. In `demo-11`, the sender and subject start
  like a spreadsheet formula, so their cells start with a protective `'`.
- `review.manifest.json`: the name and SHA-256 fingerprint of
  `data/messages.csv`.

What the demo shows:

| Message | What happens |
|---|---|
| `demo-01` … `demo-06` | one message per intent: meeting, support, job, complaint, status update, thanks |
| `demo-07` | empty message: no draft, "human review needed" |
| `demo-08` | two requests (meeting and login problem): both recorded, the draft covers both |
| `demo-09` | rule-override attempt: warning, neutral fallback draft, no refund or approval |
| `demo-10` | "My order hasn't arrived yet": the draft asks for the order reference and promises nothing |
| `demo-11` | formula-like sender and subject: protected with a leading `'` in `review.csv` |
| `demo-12` | **a genuine classifier mistake** (see below) |

**The classifier gets `demo-12` wrong.** "I have been on hold for forty
minutes three times this week and nobody has called me back" is a
complaint to a human reader, but it contains none of the complaint
keywords, so it is classified `other_or_unclear` and gets a generic
"could you tell me more" draft. The keyword rules were not changed for
this demo; mistakes like this are why every draft needs a human
review. (See *Known limitations and risks* in `docs/intent.md`.)

## 2. Review — `2_reviewed/`

A copy of `1_draft/review.csv` with the reviewer's decisions filled in,
and a copy of `review.manifest.json` beside it (`finalize` looks for the
manifest next to the review file). Only the `decision`, `edited_draft`
and `reviewer_note` columns differ from `1_draft/review.csv`. The
decisions were written with Python's `csv` module, not a spreadsheet
program, so this example does not show what a spreadsheet would do to
the file.

| Decision | Messages |
|---|---|
| approve | `demo-01`, `demo-03`, `demo-06` |
| edit | `demo-02` (name and answer filled in), `demo-08` (both parts answered) |
| reject | `demo-09` (rule-override attempt), `demo-11` (no reply needed) |
| pending (blank) | `demo-04`, `demo-05`, `demo-07`, `demo-10`, `demo-12` |

## 3. Finalize — `3_final/`

```bash
PYTHONPATH=src .venv/bin/python -m inbox_helper finalize data/messages.csv --review examples/2_reviewed/review.csv --out examples/3_final
```

- `approved_unsent.md`: headed **NOT SENT**; the input and review
  fingerprints; the counts (3 approved, 2 edited, 2 rejected, 5 pending);
  the ids of pending and rejected messages; and each reply to send by
  hand, with its warnings.
- `approved_unsent.csv`: one row per approved or edited reply (5 rows),
  status `approved_unsent`.

Every reply still has unresolved placeholders such as `[YOUR NAME]`,
listed under *Reply warnings*. **Approving or editing a reply does not
fill them in:** the three approved replies still contain content
placeholders such as `[CONFIRM AVAILABILITY OR PROPOSE A TIME]`, and
every placeholder must be replaced with real content, or removed,
before anyone sends the reply. The edited reply to `demo-08` also gets
a warning for commitment wording ("I will"); warnings never block a
reply, they ask the reviewer to check.

To regenerate the example after an intended change, in this order:

1. Delete `1_draft/` and run the `draft` command above.
2. Keep the old `2_reviewed/review.csv` aside. Copy the new
   `1_draft/review.csv` and `1_draft/review.manifest.json` into
   `2_reviewed/`. Then, for each message id, copy the `decision`,
   `edited_draft` and `reviewer_note` values from the old reviewed CSV
   into the new one (the table above lists only the decisions).
3. Delete `3_final/` and run the `finalize` command above.
4. Run the tests: `tests/test_examples.py` checks that all three steps
   match.
