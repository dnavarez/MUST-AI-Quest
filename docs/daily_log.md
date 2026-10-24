# Five-Day Work Log

## Day 1 — 2026-10-23

### Goal
Understand the challenge and define the initial direction for
the Inbox Helper.

### Work completed
- Started the MUST AI Quest.
- Selected the Inbox Helper as the proposed challenge direction.
- Verified the local Python virtual environment and pytest.
- Verified that Claude Code launches successfully.
- Initialized the local Git repository.
- Created the initial project folders.
- Created docs/intent.md with the initial problem, scope,
  safety boundaries, success criteria, and open questions.

### AI usage
- Used ChatGPT for step-by-step environment setup and planning.
- Record Claude Code usage, prompts, and outcomes here as they occur.
- Record which AI suggestions were accepted, modified, or rejected.

### Decisions and trade-offs
- Proposed human review before any suggested reply is used.
- Proposed synthetic sample messages to avoid exposing private data.
- Implementation approach remains undecided.

### Blockers and failed experiments
- None recorded so far. Update this section if issues occur.

### Next steps
- Review the exact challenge instructions.
- Confirm the required behavior and evaluation criteria.
- Choose and document the implementation approach.
- Build and test a small first version.

### Additional progress — 2026-10-23
- Reviewed the prepared sample-message and evaluation-case CSV files as reference material.
- Refined the proposed intent taxonomy to include meeting requests, support questions, job applications, complaints, status updates, thank-you messages, and unclear messages.
- Documented how to handle messages containing multiple intents.
- Documented that message content must not override application rules or bypass human review.
- Kept classification categories as hypotheses to test rather than claiming they are already validated.

### Next steps
- Review the design and choose a minimal implementation approach.
- Build the first small, testable slice.
- Record actual prompts, AI-generated changes, test results, and revisions as they occur.

### Additional progress — 2026-10-23 (Claude Code session)

#### Design documentation (`docs/intent.md`)
- AI suggestion (Claude Code): reviewed the intent document, listed
  ambiguities, and proposed a local, deterministic, rule-based Python
  CLI for v1 with no LLM, network access, or sending capability.
- My decisions: approved that design, then made corrections:
  - empty messages get no reply draft and are flagged for human review;
  - the primary intent is the first clearly identifiable request, and
    an ambiguous sentence before it makes the message `unclear`;
    this replaced the AI's suggested fixed category-priority tie-break;
  - the no-sending check is a code and dependency review, with an
    import-search test treated as a tripwire, not proof.
- AI-generated wording was revised in three rounds after my review.

#### First implementation slice: CSV loading
- Environment checked before changes: `.venv` with Python 3.14.7 and
  pytest 9.1.1. No other packages were installed.
- Files created (AI-generated, pending my review):
  - `src/inbox_helper/__init__.py`, `src/inbox_helper/models.py`
    (`Message` with `id`, `sender`, `subject`, `body`).
  - `src/inbox_helper/loader.py` (`load_messages`, `MessageFileError`):
    reads a CSV, rejects an empty file or missing required columns with
    a clear error, ignores extra columns, turns empty cells into empty
    strings, accepts Excel-style UTF-8 files.
  - `tests/test_loader.py` (9 tests: valid input, extra columns, Excel
    byte-order mark, header-only file, missing one column, missing
    several columns, three kinds of empty file).
  - `pyproject.toml` (pytest settings only, so tests can import `src/`).
  - `README.md` (status, setup, input format, how to run the tests).
- Not implemented: classification, drafting, report, command-line
  entry point.

#### Tests run
- Command: `.venv/bin/python -m pytest -v`
- First run: 9 passed, but one result was a **false pass**. A
  whitespace-only file raised a "missing required column(s)" error,
  and the test still passed because it only looked for the word
  "empty", which also appears in pytest's temporary folder name.
- Fix: the loader now treats a whitespace-only first line as an empty
  file, and the test checks the exact phrase "The CSV file is empty".
- Second run: 9 passed.

#### Problems and open points
- Lesson: error-message tests should match a specific phrase, not a
  single common word.
- AI default, needs my decision: a file with a header but no rows
  returns an empty list instead of an error.
- Not yet checked: blank or duplicate `id` values. `id` links each
  message to its draft, so this should be decided before the report
  is built.
- No `.gitignore` yet; `.venv/`, `.pytest_cache/` and `__pycache__/`
  show as untracked files.
- Nothing has been committed to Git.

### Additional progress — 2026-10-23 (Claude Code session, step 2)

#### My decisions (approved before this step)
- Keep: a CSV with valid headers but no data rows returns an empty list.
- Reject blank, whitespace-only, and duplicate message ids; trim spaces
  around ids; errors must name the CSV row and the problem.
- Add a `.gitignore` for `.venv/`, `__pycache__/`, `.pytest_cache/`,
  `.DS_Store`.

#### What changed (AI-generated, pending my review)
- `src/inbox_helper/loader.py`: ids are trimmed; blank ids and
  duplicate ids raise `MessageFileError`. Row numbers count the header
  as row 1, like a spreadsheet. Example messages:
  `<file>, row 3: the id is blank.` and
  `<file>, row 4: the id 'm1' is a duplicate of row 2.`
- `tests/test_loader.py`: 5 new id tests (surrounding spaces trimmed,
  blank id, whitespace-only id, duplicate id, ids that differ only by
  spaces). The header-only test was kept unchanged. All error tests
  now compare the **entire** error message with `==` instead of
  searching for a word, so they cannot pass because of text in
  pytest's temporary folder path.
- `.gitignore` added. Checked with `git status --ignored`: only
  `.DS_Store`, `.pytest_cache/`, `.venv/` and the two `__pycache__/`
  folders are ignored; source, tests, docs and README are not.

#### Tests run
- `.venv/bin/python -m pytest -v` → 14 passed.
- Check that the new tests can fail (AI suggestion): ran the new test
  file against the previous loader in a scratch copy of the project
  (outside this repo) → the 5 new id tests failed and the other 9
  passed, as expected.

#### Issues and notes
- No failures in the final run.
- Known limitation: the `csv` module skips completely blank lines, so
  if a file contains blank lines, the reported row number can be lower
  than the line number seen in a text editor.
- Nothing has been committed to Git.

### Additional progress — 2026-10-23 (Claude Code session, step 3)

#### My decision
- Approved the CSV loader and id validation; asked for the next slice:
  deterministic, rule-based intent classification per `docs/intent.md`.

#### What was implemented (AI-generated, pending my review)
- `src/inbox_helper/classifier.py` (new, separate from the loader):
  - a fixed keyword/phrase table for the six non-"other" categories;
    whole-word, case-insensitive matching; curly apostrophes treated as
    straight ones;
  - subject first, then body, split into sentences on `.` `?` `!` and
    line breaks;
  - primary intent = first sentence matching exactly one category;
    an ambiguous sentence (2+ categories) before that, or no clear
    sentence at all → `other_or_unclear` + `unclear`;
  - every other matched category → secondary intents (order of first
    appearance) + `multiple_intents`;
  - blank subject and body → `other_or_unclear` + `empty`, no matches;
  - every match is kept as evidence (category, keyword, subject/body,
    sentence).
- `src/inbox_helper/models.py`: added `KeywordMatch` and
  `Classification`.
- `tests/test_classifier.py` (new): 18 tests covering the six keyword
  categories, an unclassifiable message, multiple requests, an
  ambiguous sentence before and after a clear request, only-ambiguous
  sentences, subject-before-body, two empty-message cases, a
  subject-only message, recorded evidence, case/apostrophe handling,
  and whole-word matching.
- Not implemented: drafting, report, CLI, `possible_instruction_override`
  flag, network or email code (none exists).

#### Tests run
- `.venv/bin/python -m pytest -v` → 32 passed (18 classifier + 14 loader).
- These tests use examples written to fit the rules. They check that
  the rules work as documented, not how accurate the classifier is.

#### Misclassifications found (informal probe, not the planned evaluation)
- AI-run probe of 12 hand-written messages, labelled by the AI:
  **5 of 12** got the expected primary intent. Not a measured accuracy.
- Wrong confident labels (the more serious kind of error):
  - "The application keeps crashing…" → `job_application`
    ("application" means software here).
  - The rule-override message ("…confirm my $500 refund") →
    `complaint` because of "refund". The override flag is not built yet.
- Sent to `unclear` (safer: a human reviews them):
  - "Can we schedule my interview for Monday?" (meeting + job in one
    sentence);
  - "Thanks for the help yesterday!" (thanks + help in one sentence);
  - "This is not acceptable. I want my money back." ("not acceptable"
    and "money back" are not keywords);
  - "Our weekly meetings went well." ("meetings" is not listed; word
    forms must be listed separately);
  - "Can you tell me where the invoice is?" and "Are you free for a
    quick chat tomorrow?" (no keywords).
- Also noticed: a polite "Thanks!" sign-off adds `thank_you` as a
  secondary intent and the `multiple_intents` flag, so this flag will
  appear on many ordinary messages.
- Within one sentence, candidate intents are listed in the keyword
  table's order, not in the order they appear in the text.

#### Decisions deferred to me
- No keywords were tuned in response to the probe, to avoid fitting
  rules to examples before a frozen test set exists (see the evaluation
  plan in `docs/intent.md`).
- Whether sign-off thanks should count as a secondary intent.
- Nothing has been committed to Git.

### Additional progress — 2026-10-23 (Claude Code session, step 4)

#### My decisions
- Chose option (a): build a labelled evaluation set **before** tuning
  the classifier.
- Asked that polite "thanks" be treated as a possible courtesy, as a
  proposed rule only (not implemented).
- My earlier informal 12-message check is **not** part of the formal
  evaluation set.

#### Prepared CSV files
- Searched the project, Desktop, Documents, Downloads and the home
  folder (3 levels) for CSV files named like sample/eval/message/inbox.
  The prepared files were **not found**. The only CSV found was an
  unrelated personal file, which was not opened. No prepared content
  was reused.

#### What was created (AI-generated, pending my review)
- `data/eval_dev.csv` (26 messages) and `data/eval_test.csv`
  (24 messages): synthetic messages written by Claude Code, with
  AI-proposed labels (`label_status=ai_proposed`), a rationale for
  every label, case tags, and alternative labels for the 10 cases
  tagged `debatable`. The files were written with a one-off helper
  script kept outside the repository (for correct CSV quoting); the
  CSV files themselves are the source of truth.
- `src/inbox_helper/evaluate.py`: evaluation script (Markdown report).
- `tests/test_evaluate.py` (metric arithmetic on hand-made results) and
  `tests/test_eval_dataset.py` (dataset integrity). Neither asserts
  any accuracy level.
- `docs/eval_baseline_2026-10-23.md`: saved baseline report.
- `docs/intent.md`: proposed sign-off rule, data provenance, updated
  evaluation plan. `README.md`: evaluation command.
- The classifier was **not changed** (same MD5 fingerprint before and
  after: `c9a038354d33ab5af9605472b51acb17`).

#### Fingerprints of the evaluation files used for the baseline
- `data/eval_dev.csv` SHA-256
  `ee7d465c7e21106c66a7a05eb4ccb3d48b2b0dd53634d61d6cebdfbd0bb99e48`
- `data/eval_test.csv` SHA-256
  `317277ee1355b4d31c93037efba29f7d66e66f8d0b4f7bf9f4958b0beb2ad164`
- These will change if I edit labels during my review; the new values
  should then be recorded here as the frozen versions.

#### Tests run
- `.venv/bin/python -m pytest -q` → 45 passed (14 loader, 18
  classifier, 4 evaluation arithmetic, 9 dataset integrity).

#### Baseline results (untuned classifier, AI-proposed labels)
| Metric | Dev (26) | Test (24) |
|---|---|---|
| Strict accuracy | 16/26 (61.5%) | 15/24 (62.5%) |
| Lenient accuracy | 18/26 (69.2%) | 16/24 (66.7%) |
| Majority baseline | 6/26 (23.1%) | 5/24 (20.8%) |
| Sent to review | 5/26 (19.2%) | 4/24 (16.7%) |
| Confidently wrong | 3/26 (11.5%) | 4/24 (16.7%) |
| Abstention rate | 8/26 (30.8%) | 8/24 (33.3%) |
| Accuracy when it answered (lenient) | 15/18 (83.3%) | 12/16 (75.0%) |
| Expected secondary intents found | 0/2 | 1/2 |
| Empty messages flagged | 2/2 | 1/1 |

- It beats the majority baseline, but it is **not** reliable: about 1
  in 6 test messages got a confident wrong label.
- Confidently wrong examples: "application" meaning software or a
  grant (dev-12, test-12); a meeting mentioned as past information
  (dev-18); "Many thanks" sign-off chosen as the primary intent
  because the real question had no keywords (test-10); praise for
  support labelled `support_question` (test-21); first request missed
  because it had no keywords (dev-14, test-14).
- `easy` cases: 8/8 correct in both files. These were written using
  words the keywords cover, so they say little about real accuracy.
- `support_question` recall is lowest (2/6 dev, 1/5 test): many
  questions use no keyword.
- Sign-offs: 2 of 3 dev and 2 of 4 test `signoff` messages got an
  unexpected `thank_you` secondary intent.
- `override` messages scored as correct/acceptable on category only.
  The `possible_instruction_override` flag is not implemented, so these
  results say nothing about override safety.

#### Issues and limitations
- Fixed during this step: the report's table rows broke because I
  used `|` between subject and body; previews now use `[subject] body`.
- The same AI wrote the keyword rules, the messages and the labels, so
  results may be optimistic and labels may share the AI's blind spots.
- 24–26 messages per file: one message ≈ 4 percentage points.
- The most-common-label baseline uses the most common label within each
  file.
- Nothing has been committed to Git.

#### Next steps (proposed)
- Me: review every label in both files; change `label_status` to
  `human_reviewed`; record new fingerprints; then treat the test set as
  frozen.
- After that: tune keywords using the dev set only, and re-score the
  test set once at a checkpoint.

### Additional progress — 2026-10-23 (Claude Code session, step 5: metric audit)

#### My decision
- Before reviewing labels, I asked for an audit of the baseline
  report's metrics. No classifier, label or keyword changes allowed.

#### Audit method (AI-performed)
- Recounted every metric with a separate script that read the CSVs
  directly and did its own counting, without the evaluation module's
  counting code.
- Compared the saved report with a fresh run of the evaluation
  command: identical apart from the report's header.

#### Finding
- **No count was wrong.** Every number in the original report matched
  the independent recount.
- **Reporting inconsistency (test set):** the report listed 8
  abstentions but explained only 7 (3 where `other_or_unclear` was
  expected + 4 "sent to review"). The 8th was `test-18`: it abstained,
  and `other_or_unclear` is an acceptable alternative for it, so it
  was counted under "acceptable" and never shown as an abstention.
  The "Sent to review" row's description also matched test-18 even
  though test-18 was not counted there. The dev set had no such case,
  so its rows happened to add up.
- **Missing metrics:** accuracy among definite predictions was shown
  only in its lenient form, and accuracy with every abstention counted
  as incorrect was not shown.

#### Correction (AI-generated, pending my review)
- `src/inbox_helper/evaluate.py`: the report now starts with a
  reconciliation table (exact / acceptable / incorrect × definite /
  abstention). Every metric shows its numerator and denominator.
  Added "strict accuracy, every abstention incorrect" and "accuracy
  among definite (exact)". `summarize` stops with an error if the
  table does not add up to the message count.
- `tests/test_evaluate.py`: 3 regression tests built around a
  test-18-style case (acceptable abstention); the existing summary
  test now checks the reconciliation table.
- `docs/eval_baseline_2026-10-23_corrected.md`: new report from a fresh
  run. **The original `docs/eval_baseline_2026-10-23.md` is unchanged**
  and kept as the historical record; its numbers remain valid.
- `docs/intent.md` and `README.md`: metric definitions and pointers to
  the corrected report.
- Unchanged (verified by fingerprint): classifier, both datasets,
  original baseline report.

#### Corrected metrics (same counts, now reconciled)
| Metric | Dev (26) | Test (24) |
|---|---|---|
| Exact match: definite + abstention | 13 + 3 = 16 | 12 + 3 = 15 |
| Acceptable: definite + abstention | 2 + 0 = 2 | 0 + 1 = 1 |
| Incorrect: definite + abstention | 3 + 5 = 8 | 4 + 4 = 8 |
| Definite / abstentions | 18 / 8 | 16 / 8 |
| Strict accuracy | 16/26 (61.5%) | 15/24 (62.5%) |
| Lenient accuracy | 18/26 (69.2%) | 16/24 (66.7%) |
| Strict, every abstention incorrect (new) | 13/26 (50.0%) | 12/24 (50.0%) |
| Accuracy among definite, exact (new) | 13/18 (72.2%) | 12/16 (75.0%) |
| Accuracy among definite, lenient | 15/18 (83.3%) | 12/16 (75.0%) |

#### Tests run
- `.venv/bin/python -m pytest -q` → 48 passed.
- The 3 new regression tests cannot pass on the previous
  `evaluate.py` (checked in a scratch copy: the test file fails to
  import because the reconciliation table did not exist).

#### Lesson
- A report can have correct numbers and still mislead if its parts do
  not visibly add up. Showing where every item landed, and making the
  script check the sums, catches this.
- Nothing has been committed to Git.

### Label review — 2026-10-23 (batch 1: dev-01 to dev-10)

- Claude Code presented the 10 labels with rationales; it proposed no
  label changes and raised two questions.
- **My decisions:**
  - Accepted the labels for dev-01 to dev-10 unchanged.
  - Approved the polite sign-off rule: a closing "Thanks!" or "Thank
    you!" is courtesy, not a separate `thank_you` intent, when the
    message has another clear primary purpose; genuine gratitude as the
    main purpose remains `thank_you`. Not yet implemented in the
    classifier.
  - Option A for the `easy` tag: "straightforward for a human reader",
    independent of the classifier's keywords.
- Recorded in `docs/intent.md`. No CSV changes; rows stay `ai_proposed`
  until all batches are reviewed.

### Label review — 2026-10-23 (batch 2: dev-11 to dev-20)

- Claude Code presented the 10 labels, proposed one change (dev-14)
  and raised three definition questions (D1–D3).
- **My decisions:**
  - D1: requests for help, information, or documents count as
    `support_question`; definition updated in `docs/intent.md`.
  - D2: support vs. complaint — `support_question` when the sender
    asks for help, information, or a document (including help fixing
    something after a problem); `complaint` when the main point is
    dissatisfaction or reporting a service failure without asking how
    to resolve it. To be applied in future reviews.
  - D3: interview scheduling is `meeting_request`, with
    `job_application` acceptable; applies to test-13 too.
  - Other dev-11 to dev-20 labels unchanged.
- **Approved label changes, not yet applied to the CSV:**
  - dev-14 `acceptable_primary`: `other_or_unclear` → (none)
  - dev-14 `case_tags`: `multi_intent;debatable` → `multi_intent`
- No CSV changes; rows stay `ai_proposed` until all batches are
  reviewed.

### Label review — 2026-10-23 (batch 3: dev-21 to dev-26)

- Claude Code proposed two changes (dev-22, dev-23) that follow from my
  batch 2 definitions, and one new convention (D4). It checked that none
  of the dev changes alter any baseline outcome.
- **My decisions:**
  - dev-22 and dev-23: changes approved (below).
  - D4: when a request for information clearly belongs to a more
    specific category, that category takes priority over
    `support_question`; `support_question` is for general help,
    information, or document requests. Recorded in `docs/intent.md`.
  - dev-21, dev-24, dev-25, dev-26 unchanged.
- **Approved label changes, not yet applied (dev file complete):**
  - dev-14 `acceptable_primary`: `other_or_unclear` → (none);
    `case_tags`: `multi_intent;debatable` → `multi_intent`
  - dev-22 `acceptable_primary`: `complaint` → (none);
    `case_tags`: `overlap;debatable` → `overlap`
  - dev-23 `acceptable_primary`: `complaint` → (none);
    `case_tags`: `misleading_keyword;debatable` → `misleading_keyword`
  - No primary or secondary labels change in the dev file.

### Label review — 2026-10-23 (batch 4: test-01 to test-12)

- Claude Code proposed changes for test-08 and test-12 and raised D5
  (implied help requests) for test-11, showing the baseline effect of
  each proposal.
- **My decisions:**
  - test-12: approved (same pattern as dev-23).
  - test-08: Option A. This lowers strict test accuracy from 15/24 to
    14/24; I accepted that because defensible labels matter more than
    the score.
  - D5: Option 1 — a problem report about a product or service the
    sender is trying to use counts as an implied request for help.
    Recorded in `docs/intent.md`.
  - Other test-01 to test-12 labels unchanged.
- **Approved label changes, not yet applied:**
  - test-08 `expected_primary`: `other_or_unclear` → `support_question`;
    `acceptable_primary`: `support_question` → `other_or_unclear`;
    tags unchanged (`vague;no_keyword;debatable`)
  - test-11 `acceptable_primary`: (none) → `complaint`;
    `case_tags`: `software_application` → `software_application;debatable`
  - test-12 `acceptable_primary`: `complaint` → (none);
    `case_tags`: `misleading_keyword;debatable` → `misleading_keyword`

### Label review — 2026-10-23 (batch 5: test-13 to test-24)

- Claude Code proposed changes for test-14, test-18 and test-24, and
  raised D6 (opening thanks) and D7 (status sentence before a request),
  showing the baseline effect of each proposal.
- **My decisions:**
  - D6: the courtesy-thanks rule covers opening as well as closing
    thanks; genuine gratitude as the main purpose remains `thank_you`.
    test-13 unchanged.
  - D7: Option A — keep the reading-order rule; test-15 tagged
    `debatable` with `support_question` acceptable. Option B (a new
    "context sentence" rule) not adopted.
  - test-14, test-18, test-24: approved (below). test-18 and test-24
    lower the baseline score; accepted in favour of defensible labels.
  - All other test-13 to test-24 labels unchanged.
- **Approved label changes, not yet applied:**
  - test-14 `acceptable_primary`: `complaint` → (none); `case_tags`:
    `multi_intent;no_keyword;debatable` → `multi_intent;no_keyword`;
    rationale: sender asks for the invoice discrepancy to be checked,
    so support is the intent rather than a complaint.
  - test-15 `acceptable_primary`: (none) → `support_question`;
    `case_tags`: `multi_intent` → `multi_intent;debatable`.
  - test-18 `acceptable_primary`: `other_or_unclear` → (none);
    rationale: sender clearly reports the problem is resolved and asks
    for no action.
  - test-24 `expected_primary`: `thank_you` → `status_update`;
    `acceptable_primary`: `status_update` → `thank_you`; tags unchanged
    (`signoff;debatable`); rationale: receipt confirmation is the
    primary status update under the courtesy-thanks convention;
    gratitude is a defensible alternative.

### Label review complete — summary of all approved, unapplied changes

| Row | Change |
|---|---|
| dev-14 | acceptable `other_or_unclear` → none; remove `debatable` |
| dev-22 | acceptable `complaint` → none; remove `debatable` |
| dev-23 | acceptable `complaint` → none; remove `debatable` |
| test-08 | primary `other_or_unclear` → `support_question`; acceptable `support_question` → `other_or_unclear` |
| test-11 | acceptable none → `complaint`; add `debatable` |
| test-12 | acceptable `complaint` → none; remove `debatable` |
| test-14 | acceptable `complaint` → none; remove `debatable`; rationale updated |
| test-15 | acceptable none → `support_question`; add `debatable` |
| test-18 | acceptable `other_or_unclear` → none; rationale updated |
| test-24 | primary `thank_you` → `status_update`; acceptable `status_update` → `thank_you`; rationale updated |

- All 50 rows reviewed by me; 40 unchanged. CSVs not yet edited; rows
  still `ai_proposed`. CSV fingerprints still match the baseline.

### Label review applied — 2026-10-23

#### My decision
- Approved applying the 10 reviewed changes in one step and marking
  all 50 rows `human_reviewed`. Confirmed the D6 wording (courtesy
  thanks are not a separate or first intent when another clear primary
  purpose exists; genuine gratitude remains `thank_you`).

#### What was done (AI-performed, following my approved list)
- A one-off script (kept outside the repository) applied the changes.
  For every field it checked that the current value matched the value
  I had reviewed before changing it; all matched.
- Verified with a field-by-field comparison against copies of the old
  files: same row ids, order and columns; the 10 approved rows changed
  only the approved fields plus `label_status` and `rationale`; the
  other 40 rows changed only `label_status`. All 50 rows are now
  `human_reviewed`.
- Before writing, confirmed that rewriting the unchanged CSVs reproduces
  them byte-for-byte, so no unrelated formatting changed.

#### Tests run
- `.venv/bin/python -m pytest -v` → 48 passed, including all 9 dataset
  integrity checks. No fixes were needed.

#### Frozen dataset fingerprints (SHA-256)
- `data/eval_dev.csv`
  `a19d0d36e271e55435245d07a229b08c8774dd1c24bf65e62cdee2a946284a1b`
- `data/eval_test.csv`
  `b74fe9fb2a3ef8fa77f58c1e7e84bbf1f6d370e13907b92a90dc20d9a3e5526c`
- Pre-review fingerprints (first baseline) are recorded in the step 4
  entry above.

#### Post-review evaluation (untuned classifier, human-reviewed labels)
Report: `docs/eval_post_review_2026-10-23.md`. Earlier reports unchanged.

| Metric | Dev (26) | Test (24) | Test before review |
|---|---|---|---|
| Strict accuracy | 16/26 (61.5%) | 13/24 (54.2%) | 15/24 (62.5%) |
| Lenient accuracy | 18/26 (69.2%) | 15/24 (62.5%) | 16/24 (66.7%) |
| Strict, every abstention incorrect | 13/26 (50.0%) | 11/24 (45.8%) | 12/24 (50.0%) |
| Majority baseline | 6/26 (23.1%) | 6/24 (25.0%) | 5/24 (20.8%) |
| Confidently wrong | 3/26 (11.5%) | 4/24 (16.7%) | 4/24 (16.7%) |
| Sent to review | 5/26 (19.2%) | 5/24 (20.8%) | 4/24 (16.7%) |
| Abstention rate | 8/26 (30.8%) | 8/24 (33.3%) | 8/24 (33.3%) |
| Accuracy among definite (exact) | 13/18 (72.2%) | 11/16 (68.8%) | 12/16 (75.0%) |
| Accuracy among definite (lenient) | 15/18 (83.3%) | 12/16 (75.0%) | 12/16 (75.0%) |

- Dev results are unchanged by the review (as projected).
- Test results fell as projected: test-08 and test-24 moved from exact
  to acceptable; test-18 moved from acceptable to sent to review. The
  majority baseline rose because test-08 is now `support_question`.
- The classifier still beats the majority baseline but is not
  reliable: about 1 in 6 test messages gets a confident wrong label.

#### Why this is still preliminary
- Labels are human-reviewed **with AI assistance**: Claude Code wrote
  the messages, proposed every label and every change; I made the
  decisions.
- The keyword rules were also AI-written, so the rules, data and labels
  may share blind spots.
- 24–26 messages per file; one message is about 4 percentage points.
- Nothing has been committed to Git.

### Classifier tuning C1–C5 (dev only) — 2026-10-23

#### My decisions
- Approved C1–C5 only, with refinements: keep genuine help requests next
  to thanks; refund demand alone is not a complaint; no blanket rule for
  status keywords in questions; keep other job evidence; add negative
  tests such as "live chat isn't working"; add a prompt-injection
  regression test. Rejected O1–O4 (single-example changes).
- Development must not use `data/eval_test.csv` or its results.

#### What was implemented (AI-generated, pending my review)
- `src/inbox_helper/classifier.py`:
  - C1: if any category other than `thank_you` is found, thanks is
    courtesy (kept as evidence, never primary or secondary). "Help" in
    "thanks … for your/the help" is not a help request.
  - C2: removed `refund` from complaint keywords; added `damaged`.
  - C3: "update" does not count as status inside "give/send/get/provide
    me|us an update", "any update", "update me|us".
  - C4: removed `interview` from job keywords.
  - C5: added meeting phrases `a chat`, `quick chat`, `set up a time`.
- `tests/test_classifier.py`: 21 new tests; 1 existing test updated.

#### Deviations from the approved wording (explained before coding)
- C5: added the phrases "a chat" and "quick chat" instead of the bare
  word "chat". The bare word would have turned "Our live chat isn't
  working" into a meeting request, because "isn't working" is not a
  support keyword; adding it would have been an unapproved change.
- The existing test `test_subject_is_read_before_body` used subject
  "Thank you" and expected `thank_you` as primary. That expectation
  contradicts the approved D6 rule, so it was moved to a new test with
  the D6 answer (`meeting_request`); reading order is now tested with
  subject "Meeting" + a support question.

#### Tests run
- Old test suite against the new classifier first: 1 failure, the
  expected D6 one above; 47 passed.
- Final: `.venv/bin/python -m pytest -q` → 69 passed.
- New tests against the old classifier (scratch copy): 15 failed, as
  intended; 6 passed — these are guard tests checking that the changes
  do not over-reach (e.g. "live chat isn't working" is not a meeting;
  a status statement phrased as a question is still status).

#### Dev results (measured; test set not scored)
Report: `docs/eval_dev_c1-c5_2026-10-23.md`.

| Metric (dev, 26) | Before C1–C5 | After C1–C5 |
|---|---|---|
| Strict accuracy | 16/26 (61.5%) | 20/26 (76.9%) |
| Lenient accuracy | 18/26 (69.2%) | 20/26 (76.9%) |
| Strict, every abstention incorrect | 13/26 (50.0%) | 16/26 (61.5%) |
| Confidently wrong | 3/26 (11.5%) | 3/26 (11.5%) |
| Sent to review | 5/26 (19.2%) | 3/26 (11.5%) |
| Abstention rate | 8/26 (30.8%) | 7/26 (26.9%) |
| Accuracy among definite (exact) | 13/18 (72.2%) | 16/19 (84.2%) |
| Expected secondary intents found | 0/2 | 1/2 |
| Messages with unexpected secondary intents | 5/26 | 2/26 |

- Per-message comparison: 4 better (dev-13, dev-16, dev-20, dev-21),
  4 same outcome with cleaner secondary intents (dev-10, dev-11, dev-15,
  dev-23), **0 worse**.
- dev-17 is still `complaint`, but now from "arrived damaged" instead of
  the injected "refund" text.
- The dev set was used to choose these changes, so these dev numbers
  are optimistic by design. Only the frozen test checkpoint can show
  whether they generalise.

#### Remaining limitations
- Still confidently wrong on dev: dev-12 (software "application"),
  dev-14 (document request with no keyword), dev-18 (past meeting).
- Still sent to review: dev-19, dev-22, dev-23.
- `possible_instruction_override` is **not implemented**. C1–C5 do not
  detect or prevent prompt injection and do not guarantee safety.
- Honesty note: the AI had already seen the test messages earlier in
  this session (while writing and reviewing them). It did not open the
  test file or test results during this tuning, but the next test score
  is not fully independent.
- Nothing has been committed to Git.

### Frozen test checkpoint — 2026-10-23

- **My decision:** approved running the test checkpoint exactly once,
  with no changes based on its results.
- Ran `PYTHONPATH=src .venv/bin/python -m inbox_helper.evaluate
  data/eval_test.csv` once; output saved directly to the new report
  `docs/eval_test_checkpoint_c1-c5_2026-10-23.md` (no existing report
  overwritten). Comparison values for the untuned classifier were read
  from the saved `docs/eval_post_review_2026-10-23.md`, not re-run.
- Fingerprints before the run: `eval_test.csv` b74fe9fb…, `eval_dev.csv`
  a19d0d36… (unchanged); classifier MD5 855131003c9a432aeef8874eab620cac.

| Metric | Dev before | Dev after | Test before | **Test after** |
|---|---|---|---|---|
| Strict accuracy | 16/26 (61.5%) | 20/26 (76.9%) | 13/24 (54.2%) | **14/24 (58.3%)** |
| Lenient accuracy | 18/26 (69.2%) | 20/26 (76.9%) | 15/24 (62.5%) | **16/24 (66.7%)** |
| Strict, every abstention incorrect | 13/26 | 16/26 | 11/24 | **12/24 (50.0%)** |
| Majority baseline | 6/26 | 6/26 | 6/24 | 6/24 (25.0%) |
| Confidently wrong | 3/26 | 3/26 | 4/24 | **4/24 (16.7%)** |
| Sent to review | 5/26 | 3/26 | 5/24 | **4/24 (16.7%)** |
| Abstention rate | 8/26 | 7/26 | 8/24 | 7/24 (29.2%) |
| Accuracy among definite (exact) | 13/18 | 16/19 | 11/16 | 12/17 (70.6%) |
| Unexpected secondary intents | 5 | 2 | 5 | 3 (none `thank_you`) |

- Only one test message changed outcome: test-13 (interview scheduling
  with opening thanks) went from sent to review to correct (C1 + C4).
  test-09 and test-13 also lost unwanted `thank_you` secondaries.
- The same 4 test messages are confidently wrong before and after:
  - test-10 "Where can I download … invoice? Many thanks, Priya" →
    `thank_you`: the question has no keyword, so thanks is the only
    category found and the courtesy rule cannot apply.
  - test-12 grant "application" → `job_application` (the same weakness
    as dev-12; the optional fix O1 was not adopted).
  - test-14 invoice check with no keyword, then a call → primary
    `meeting_request` (same weakness as dev-14; O2 not adopted).
  - test-21 thank-you note mentioning "support" and "issue" →
    `support_question` (the C1 limitation noted before the checkpoint).
- **Interpretation:** the dev gain (+4 messages) mostly did not
  transfer: the test gain was +1 message, within the noise of a
  24-message set. The tuning reduced unwanted secondaries and did not
  add confident errors, but the keyword approach is still unreliable:
  about 1 in 6 test messages gets a confident wrong label.
- **Limitations:** small sets (1 message ≈ 4 points); rules, messages
  and first labels produced with AI assistance; labels human-reviewed
  with AI assistance; the AI had seen the test messages earlier in the
  session, so this score is not fully independent;
  `possible_instruction_override` is still not implemented.
- The test set has now been used for this checkpoint. Further tuning
  judged against it would make it a second dev set.
- Nothing has been committed to Git.

### Application plan and Stage 1 (safety warnings) — 2026-10-23

#### My decisions
- Stopped classifier tuning; approved a five-stage plan to complete the
  application, one stage at a time with my review after each.
- Approved Decisions 1–5: drafts never quote message text; `[NAME]`
  instead of name guessing; file-based review (`review.md`,
  `review.csv`, `finalize`); reviewer note required to approve/edit
  override-flagged messages; `output/` ignored, curated files in
  `examples/`. Recorded in `docs/intent.md` as planned design.

#### Stage 1 implemented (AI-generated, pending my review)
- `src/inbox_helper/safety.py` (new): `safety_warnings(message)` and
  `find_override_signals(message)`. Six pattern groups; evidence records
  pattern, subject/body and sentence. Separate from the classifier.
- `src/inbox_helper/models.py`: added `OverrideSignal`.
- `tests/test_safety.py` (new, 25 tests): 11 phrasings that should be
  flagged, 9 ordinary look-alikes that should not, case/apostrophe,
  subject, evidence, empty message, and separation from the classifier.
- `tests/test_no_network.py` (new, 2 tests): fails on email/network,
  `subprocess`, `webbrowser` or dynamic imports in `src/`; includes a
  self-check that the tripwire catches a forbidden import.
- Not done yet: the warning is not used by drafting or review.

#### Tests and checks run
- `.venv/bin/python -m pytest -q` → 96 passed (69 earlier + 27 new).
- `classifier.py` and `evaluate.py` byte-identical before and after.
- `PYTHONPATH=src .venv/bin/python -m inbox_helper.evaluate
  data/eval_dev.csv` output identical to the saved dev report.
- Detector on the dev set only: flags dev-16 and dev-17 (the two
  messages tagged `override`), none of the other 24. Not independent
  evidence: the patterns were written with these examples in mind. The
  test set was not used.

#### Limitations
- Pattern matching on English text only; can miss reworded, misspelled,
  translated, split or hidden instructions; can flag harmless text.
  A warning is a review signal, not proof of malicious intent.
- The tripwire test is not proof that the program cannot reach the
  network; the primary check remains a human code and dependency review.
- Nothing has been committed to Git.

### Stage 2 (reply drafting) — 2026-10-23

#### My decision
- Approved Stage 1 and asked for Stage 2 only, with ten acceptance
  criteria (templates for all seven intents, secondary sentences, word
  limit, no draft for empty messages, neutral override fallback,
  placeholders, guard tests incl. negative tests, warnings never
  cleared, tests, docs only for verified behavior).

#### Implemented (AI-generated, pending my review)
- `src/inbox_helper/drafter.py` (new): `draft_reply(message,
  classification, warnings)`, `check_draft(text, message)`, fixed
  templates for all seven intents, fixed secondary sentences, safe
  fallback, guard checks (commitment/approval/money/deadline wording,
  currency symbols, numbers and date words not in the message, 100-word
  limit; placeholder text ignored).
- `src/inbox_helper/models.py`: added `Draft` (message id, text or
  None, status, warnings, note).
- `tests/test_drafter.py` (new, 55 tests).
- Design choice (AI proposal, for my review): when the primary intent
  is `other_or_unclear`, the draft only asks for clarification and does
  not add sentences for candidate intents.
- Not implemented yet: review files, review decisions/finalize, CLI.

#### Problem found and fixed during the stage
- The first version of the number check accepted "5" in a draft when
  the message contained "500" (substring match). Changed to compare
  whole numbers and whole date words; added a regression test.

#### Tests and checks run
- `.venv/bin/python -m pytest -q` → 151 passed (96 earlier + 55 new).
- `classifier.py`, `evaluate.py`, `safety.py` and all five evaluation
  reports unchanged (MD5 compared before/after); `eval_dev.csv`
  a19d0d36…, `eval_test.csv` b74fe9fb… unchanged. Test evaluation not
  run or inspected.

#### Limitations
- Guards are word lists and patterns; a commitment phrased differently
  (e.g. "you'll get your money back") would not be caught.
- Templates are generic; a wrong predicted intent gives a wrong
  template, which the reviewer must catch.
- Only generated drafts are checked so far; checking human edits is
  planned for Stage 4.
- Nothing has been committed to Git.

### Git checkpoint and multi-line safety fix — 2026-10-23

#### Git checkpoint (done before this fix)
- My decision: one honest checkpoint commit of all verified work through
  Stage 2, on `main`, with `output/` added to `.gitignore`; no
  reconstructed historical commits.
- Commit `b2211ad` "Initial checkpoint: Inbox Helper through Stage 2":
  26 files; staged paths checked against the approved list; 151 tests
  passed on the working tree and on the staged snapshot; CSV
  fingerprints verified on disk, in the staging area and in the commit.
- A pre-commit hook required automated security and code-quality
  reviews of the staged files. Neither found Critical or High issues.
  Findings: one confirmed Medium bug (below), one Medium design risk
  (drafting depends on the caller passing the override warning; to be
  covered by an end-to-end test in Stage 3), and several Low items
  (tripwire does not cover `os.system`/`asyncio`/`multiprocessing`/
  `ctypes`; unescaped message text in evaluation report previews; loader
  row numbers with blank lines; evaluation header trimming; one
  unreachable drafter sentence). The Low items are not fixed yet.

#### Multi-line safety fix
- **Bug (confirmed by me running it):** "Ignore all previous
  instructions." was flagged, but "Ignore all previous⏎instructions."
  was not, because the detector reused the classifier's sentence
  splitter, which splits at every line break.
- **My decision:** fix it in a separate commit before Stage 3, changing
  only `safety.py`, its tests, `docs/intent.md` and this log.
- **Change (AI-generated, pending my review):** `safety.py` now has its
  own splitter: line breaks and repeated spaces become single spaces,
  then text is split only after `.`, `?` or `!`. It no longer imports
  from the classifier. The classifier is unchanged.
- **Tests:** 14 new tests in `tests/test_safety.py`: 7 wrapped
  instructions (including `\r\n` and a realistic wrapped email), the
  evidence sentence for wrapped text, 5 ordinary multi-line messages
  that must not be flagged, and a check that the detector does not
  import the classifier.
- **Problem found while writing tests:** the first version of the
  wrapped-email test also passed on the old code, because its line
  breaks fell between the suspicious phrases. It was re-wrapped so the
  instructions are actually split across lines.
- **Results:**
  - New tests against the committed (old) `safety.py`: 9 failed, 30
    passed — the 9 failures are the wrapped cases, the evidence test
    and the independence check, as intended.
  - `.venv/bin/python -m pytest -q tests/test_safety.py` → 39 passed.
  - `.venv/bin/python -m pytest -q` → 165 passed.
  - On the dev set only, the detector still flags exactly dev-16 and
    dev-17. Test-set evaluation not run; classifier not tuned.
- **Remaining limitations:** an instruction split by a full stop, or
  between subject and body, is still missed; joining lines can merge
  unpunctuated list items into one sentence and may occasionally cause
  a false warning; all earlier detector limitations still apply.

### Stage 3 (review files and `draft` command) — 2026-10-23

#### My decisions
- Approved the Stage 3 plan and four decisions: refuse to overwrite
  existing review files unless `--overwrite`; protect formula-like CSV
  cells with `'` (Stage 4 compares against the original input); CSV in
  input order, UTF-8 with BOM; show invisible characters as `[U+XXXX]`
  in `review.md` only.
- Detection rules, classifier, drafter, frozen data and reports must not
  change; the frozen test evaluation must not be run or inspected.

#### Implemented (AI-generated, pending my review)
- `src/inbox_helper/review.py` (new): pipeline (`load_messages` →
  `classify` → `safety_warnings` → `draft_reply` with the warnings passed
  explicitly), `review.md` rendering with escaping and code blocks,
  `review.csv` rendering with formula protection, and writing via
  temporary files with the overwrite rule.
- `src/inbox_helper/__main__.py` (new):
  `python -m inbox_helper draft INPUT --out DIR [--overwrite]`; clear
  errors with exit code 2; summary that says nothing was sent.
- `tests/test_review.py` (new, 15 tests) and `tests/test_cli.py` (new,
  13 tests, counting parametrized cases), including the 10-message acceptance test, byte-identical
  output, invalid input, existing files, escaping, long evidence,
  invisible characters, formula protection, a dev-set check that dev-16
  and dev-17 get the fallback and warning, and a real `python -m` run.
- README, `docs/intent.md`: Stage 3 behavior, limitations, and the
  documented detector misses (quoted `>` lines, invisible characters,
  look-alike characters, hyphenated line breaks). No detection rules
  changed.

#### Problem found and fixed during the stage
- My first acceptance test searched the whole report for a fake
  `### Message m99` heading and failed — but that text was correctly
  inside the code block as message content. The test now checks only
  lines outside code blocks, like the other escaping tests.

#### Tests and checks run
- `.venv/bin/python -m pytest -q` → 193 passed (165 earlier + 28 new).
- Escaping check: in a temporary copy with escaping, the long fence and
  formula protection deliberately switched off, 6 of the new tests
  failed — the escaping and CSV tests do detect those failures.
- `git diff 66c72a6` on classifier, safety, drafter, loader, evaluate,
  models, their tests, `data/` and the evaluation reports: no changes.
  Frozen CSV fingerprints a19d0d36… and b74fe9fb… unchanged.
- My own security/quality review: no Critical or High issues found. The
  formal reviews required by the pre-commit hook have not been run yet.

#### Limitations
- The two review files are replaced one after the other; an error in
  that instant could leave a new `review.md` next to an old
  `review.csv`. Another program creating the files between the check and
  the write is not detected.
- Detector misses (unchanged): quoted `>` lines, invisible characters,
  look-alike characters, hyphenated line breaks, other wording or
  languages. Invisible characters are at least visible in `review.md`.
- Decisions, finalize and sample data are not implemented yet.
- Nothing has been staged or committed.

### Stage 3 revision before commit — 2026-10-23

#### Formal reviews of the first Stage 3 staging (pre-commit hook)
- Security review: no Critical, High or Medium findings; Low findings
  L1–L8 (GitHub-style links/emoji in the sender line, some invisible
  characters not shown, formula check only on the first character,
  non-atomic pair replacement, existence-check race and dangling
  symlinks, `--overwrite` able to destroy decisions incl. when the input
  is `review.csv`, input read twice, temp file after a hard kill).
- Code-quality review: no Critical or High; two Medium findings —
  (1) formula protection changed the `id` column, so `=a` and `'=a`
  both became `'=a` and `-7` became `'-7`; (2) ids `a b`, `a  b` and
  `a⏎b` produced the same Markdown heading. Plus Low findings.
- I (the AI) confirmed Medium 1, Medium 2 and L1 by running them.

#### My decisions
- Do not commit yet; make a focused revision: preserve ids exactly and
  reject formula-like ids and ids with line breaks/control characters;
  unambiguous headings; stronger formula protection for non-id cells;
  refuse an input that is one of the output files (also with
  `--overwrite`); show senders safely. Document the other Low findings.

#### What changed (AI-generated, pending my review)
- `review.py`: `check_ids` (formula-like starts incl. full-width
  look-alikes; line breaks/control characters; and — the AI's
  interpretation of "unambiguous", flagged for my review — invisible
  formatting characters, unusual space characters and two spaces in a
  row); `code_span` for ids, senders and the input file name; `id`
  column written unchanged; `protect_cell` checks after stripping
  leading whitespace and NFKC normalization; input/output overlap check
  (same path, `..`, links) before anything else.
- `__main__.py`: reports the new overlap error.
- Tests: 4 existing tests updated because they checked the old heading
  format (`### Message m2` → ``### Message `m2` ``); 40 new tests.
- `docs/intent.md`, `README.md`: new rules and the remaining Low
  findings listed as known limitations.

#### Problems during the revision
- Expected: 4 existing tests failed on the new heading format and were
  updated.
- My first new id-rejection test compared full error messages against
  short phrase fragments and failed although the program was right; it
  now checks the exact start of the message (file, row, id) and that the
  problem is named.

#### Tests and checks run
- `.venv/bin/python -m pytest -q` → 233 passed (165 earlier + 46 in
  `test_review.py` + 22 in `test_cli.py`).
- New command-line tests against the pre-revision code: 10 failed
  (including `--overwrite` with `review.csv` as input destroying the
  decisions), 12 passed. The new `test_review.py` cannot import against
  the old code (new functions did not exist).
- Protected files unchanged vs `66c72a6`. Frozen CSV fingerprints
  unchanged.
- Nothing committed.

### Stage 3 cleanup (Option 2) — 2026-10-23

#### Formal reviews of the revised staging
- Security and code-quality reviews: no Critical, High or Medium
  findings; both earlier Medium findings confirmed fixed. New Low
  findings: misleading error when an output path is a folder;
  overstated `check_ids` comment; visually similar Unicode ids still
  accepted; spreadsheets may reinterpret ids (`001`, `1E3`, dates) —
  important for Stage 4; a spaces-only sender looks blank; the
  id-column test could not detect re-introduced prefixing; no `'=a` or
  symbolic-link test.

#### My decision
- Option 2: fix the comment, document the limitations, add the `=a`
  and symbolic-link tests, make the id-column test able to fail, then
  re-verify and re-review before any commit.

#### What changed (AI-generated, pending my review)
- `review.py`: `check_ids` comment now states the actual guarantee (ids
  kept exactly and restricted by the rules; Unicode strings can still
  look identical). No behavior change.
- `tests/test_review.py`: replaced the weak id-column test with two
  tests — valid tricky ids (`'=a`, `001`, `1E3`, `MAR1`, …) unchanged in
  the CSV, and the CSV writer writing even `=a`, `-7`, `@x` exactly
  (rejection is `check_ids`' job). Reason: every id that passes
  validation is one `protect_cell` would not change, so only the second
  test can detect formula prefixing re-applied to the id column.
- `tests/test_cli.py`: `=a` added to the invalid-id command tests; new
  test that a symbolic link pointing to `review.csv` is refused with
  `--overwrite` and both files stay unchanged (skips only if the
  platform cannot create symbolic links; on this Mac it ran).
- `docs/intent.md`: the four limitations added to *Known limitations*;
  Stage 4 requirement recorded (validate each decision row against the
  original input, do not trust the id alone). `README.md`: short note.

#### Tests and checks run
- `.venv/bin/python -m pytest -q -rs` → 236 passed, 0 skipped.
- Deliberate breakages in temporary copies: re-applying formula
  prefixing to `id` → `test_csv_writer_never_prefixes_the_id_column`
  failed; replacing the overlap check with a plain path comparison →
  the symbolic-link and `..` tests failed.
- Nothing committed.

### Stage 4a (review-file validation) — 2026-10-24

#### My decisions
- Approved the Stage 4 design and a Stage 4a scope of validation only:
  new `finalize.py` and `test_finalize.py`; no command, no output files,
  no changes to Stage 3 code, frozen data or evaluation.
- Decisions: `approve`, `edit`, `reject` or blank (pending), ignoring
  case and surrounding spaces only; empty messages may only be rejected
  or left pending; an edit equal to the AI draft stays an edit; exact
  ids, never repaired; content compared allowing only the protective
  apostrophe, CRLF/LF and NFC; blank rows allowed only at the end.
- Placeholder rule, `reply_warnings` column and reuse of
  `drafter.check_draft` as non-blocking warnings approved for Stage 4b.
- After the reviews: header text never shown; untrusted ids and
  decisions shown only if they look like short codes; untrusted ids
  hidden when they contain 8 or more digits in total (chosen over 9 so
  that `acct:12345678` is hidden); a copy of a review file refused as
  input; invisible-only text does not count as a note or an edit.

#### Implemented (AI-generated, pending my review)
- `src/inbox_helper/finalize.py` (new): `validate_review(input_path,
  review_path)` rebuilds every entry from the input with the Stage 3
  pipeline, reads `review.csv` with a strict reader, matches rows by
  exact id, checks the generated cells before any decision, checks the
  decision rules (including the reviewer note for override-flagged
  messages), and raises `ReviewFileError` listing the problems (at most
  50 shown). It only reads files; nothing is written or sent.
- `tests/test_finalize.py` (new, 224 tests counting parametrized
  cases), using synthetic messages only.
- `docs/intent.md`: Stage 4a behavior, known limitations and the
  planned Stage 4b output.

#### Problems found and fixed during the stage
- Some of my first tests built CSV rows by splitting text on line
  breaks, which broke draft cells containing newlines; they now use the
  CSV writer. One swapped-id test expected the two ids the wrong way
  round; the module was right.
- While fixing a review finding I briefly moved the check that skips
  the decision when the content does not match; I noticed it before
  running anything and restored it. A test now fails if that happens.
- My file-writing tools twice put invisible Unicode characters
  literally into the files (once in the tests, once in `finalize.py`);
  both files are now plain ASCII with `\u` escapes.

#### Formal reviews (security and code quality, five rounds)
- No round found a Critical or High issue.
- Round 1: one Medium finding (a missing header row made error messages
  show message text), plus Low findings (a review file accepted as
  input, confusing empty column names, misleading hints, invisible
  Unicode in tests, column drift test missing). All fixed.
- Rounds 2–5: Low findings only (short values shown in errors,
  case-changed review columns, duplicate id hints, invisible-only notes
  and edits, blank first line, digits written with separators, real
  input ids hidden in duplicate messages). Fixed as approved; the rest
  are documented as limitations.
- One reviewer once ran the full test suite including the evaluation
  test files. That run probably read the frozen evaluation data
  through those tests; the data was not modified and its fingerprints
  stayed unchanged. From then on the suite is run without
  `test_eval_dataset.py` and `test_evaluate.py`.

#### Tests and checks run
- `.venv/bin/python -m pytest -q -rs tests/test_finalize.py` → 224
  passed, 0 skipped.
- Suite without the evaluation test files
  (`--ignore=tests/test_eval_dataset.py --ignore=tests/test_evaluate.py`)
  → 444 passed, 0 skipped.
- Deliberate breakages in temporary copies (removing the content check,
  the override-note rule, exact-id matching, the header guard, the
  digit rule and others) each made specific tests fail.
- Existing source, test and data files unchanged against `d9b0bf2`;
  the only changes are the two new files (`finalize.py`,
  `test_finalize.py`) and the two documentation files; frozen CSV fingerprints
  a19d0d36… and b74fe9fb… unchanged (checked by hash only).

#### Limitations
- Short values pasted from a message into an id or decision cell can
  still appear in an error message.
- Some rare blank-looking characters (e.g. U+1D159) count as text.
- Review-only columns renamed with look-alike or invisible characters,
  or deleted, are not detected; binding the review file to its input
  (SHA-256) is deferred to Stage 4b.
- Hints for unknown or swapped ids can be slow on large files where
  every id was changed.
- A decision containing a zero-width character gets an unhelpful
  "(N characters, not shown)" message.
- An input file with an ordinary `status`, `draft` or `decision` column
  is refused.
- The protective `'` round trip has not been checked in a real
  spreadsheet program.
- A reviewer note made only of punctuation (e.g. `.`) counts as
  meaningful for an override-flagged message.
- Edited replies that start like a formula are kept as written;
  Stage 4b must protect every output CSV cell with `protect_cell` and
  show such text safely in Markdown (future requirement).
- No command and no output files yet (Stage 4b and the command).
- At the time this entry was written, the changes were staged but not
  committed; the commit status is recorded in Git history.
