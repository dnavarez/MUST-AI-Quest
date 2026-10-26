# Final directive — Inbox Helper

> **What this file is.** The quest page lists `Final directive.md` as a
> deliverable but does not say what it must contain (see
> `docs/quest_requirements.md`). This file is my interpretation: the
> final, consolidated directive for Inbox Helper as it was built —
> what it is for, how it must behave, and where its limits are —
> written so that a person or an AI assistant continuing the work
> would follow it. I have confirmed that this interpretation is the
> one I am submitting.
>
> The full design is in `docs/intent.md`; how to run it is in
> `README.md`. If this file and `docs/intent.md` disagree,
> `docs/intent.md` is the detailed source and this file should be
> corrected.

## Purpose

Help a person work through a pile of incoming messages: group them by
what each sender wants, and draft a short reply for each one, so that
a human can review every draft before anything is sent. This is
Format A (Inbox helper) of the MUST AI Quest. The tool **never sends
anything**; the human sends approved replies from their own email
tool.

## Intended user

A person who needs to process many incoming messages efficiently while
keeping full control over every reply.

## What it is

- A **local, deterministic, rule-based Python command-line program**
  (standard library only). It has **no graphical interface**.
- It reads a CSV file of messages (`id, sender, subject, body`). It
  does **not** connect to a real inbox, does not use an LLM or an API
  key, and needs no network access.
- The same input always gives the same output.

## Core workflow

1. **Draft.** `draft INPUT.csv --out DIR` classifies each message with
   keyword rules into one of seven intents (`meeting_request`,
   `support_question`, `job_application`, `complaint`,
   `status_update`, `thank_you`, `other_or_unclear`), drafts a reply
   from a fixed template with `[PLACEHOLDERS]`, and writes
   `review.md` (to read), `review.csv` (for decisions) and
   `review.manifest.json` (the input's fingerprint). Every draft is
   `pending_review`.
2. **Review.** A human fills in `decision` (`approve`, `edit`,
   `reject`, or blank for pending), `edited_draft` and
   `reviewer_note` in `review.csv`.
3. **Finalize.** `finalize INPUT.csv --review review.csv --out DIR`
   checks that the review belongs to this exact input and writes the
   approved and edited replies to `approved_unsent.md` and
   `approved_unsent.csv`, marked **NOT SENT**.
4. **Send manually.** The human copies each reply into their own email
   tool, fills in any remaining placeholders, and sends it themselves.

## Human review requirements

- No reply is final until a human has decided on it; blank means
  pending, and pending or rejected messages are never written as
  replies.
- `edit` requires the human's own text in `edited_draft`.
- An empty message gets no draft and can only be rejected or left
  pending.
- A message with the `possible_instruction_override` warning gets only
  a neutral fallback draft, and approving or editing it requires a
  `reviewer_note`.
- `finalize` checks every row of the review against the input, and the
  input's SHA-256 against the manifest written by `draft`. A review
  without a manifest is refused unless `--allow-unbound` is given; the
  output then says that the input binding was not checked.
  `--allow-unbound` never overrides a fingerprint mismatch, a damaged
  manifest or the row checks.
- Reply warnings (unfilled placeholders, commitment or approval wording)
  are shown but do not block; the human decides.

## Safety boundaries

- **No sending capability:** no send function, no email, SMTP or network
  code. This was checked by my human code and dependency review (with
  AI assistance) on
  2026-10-25 (the entry "D7 — Human code and dependency review" in
  `docs/daily_log.md`) and by a tripwire test
  (`tests/test_no_network.py`), which is not proof on its own.
- **Message text is untrusted:** it can never change the tool's rules
  or templates. It is shown as plain text in the reports, and
  spreadsheet-formula-like cells are protected with a leading `'`.
- **The override detector is a heuristic** that can miss attacks and
  flag harmless text. Safety relies on human review and on the absence
  of any sending capability, not on detection.
- **No invented facts:** drafts copy no text from the message and
  contain no dates, amounts, tracking numbers or promises; missing
  details are `[PLACEHOLDERS]` for the human to fill in.
- **Outputs stay local:** files, including short-lived temporary files,
  are written only inside the chosen output folder, which is created if
  needed (if `--out` or a folder in its path is a symbolic link, files
  go where it points).
  Existing review or final files are replaced only with `--overwrite`.

## Acceptance criteria (v1)

The five criteria in `docs/intent.md` (*Acceptance criteria (v1)*):
empty message, multiple intents, rule-override attempt, batch
traceability, and no invented facts. They are covered by named
automated tests, together with the no-network tripwire test and the
recorded human code and dependency review. By that definition, v1 is
complete for the current challenge prototype. It is **not**
production-ready.

## Limitations

- **Classification is unreliable.** On the frozen 24-message test set,
  in its one checkpoint after tuning (2026-10-23), strict accuracy was
  14/24 (58.3%), against 13/24 before tuning (both with the reviewed
  labels), and about 1 in 6
  messages got a confidently wrong label. The sets are
  small and were produced with AI assistance. The demo data includes one
  known miss (`demo-12`).
- Keyword rules miss paraphrases, negation and sarcasm; English only;
  synthetic data only; template replies can sound generic.
- The manifest is not signed: it prevents mix-ups, not deliberate
  tampering.
- Accepted limitations from the D7 review (for example a race between
  the existence check and the write, some misleading error messages,
  Windows not tested), and four Stage 4b follow-ups that are still open
  (see `docs/intent.md` and `docs/daily_log.md`).

## Rules for any further change

- Keep the no-sending, no-network boundary and mandatory human review.
- Work in small stages, with a plan approved before coding and explicit
  approval before each commit; every commit passes the security and
  code-quality review gate.
- Never edit, re-tune against, or open the frozen evaluation files
  (`data/eval_dev.csv`, `data/eval_test.csv`); the test set has been
  used for its one post-tuning checkpoint and is spent.
- Record what was actually done, tested and decided in
  `docs/daily_log.md`, keeping AI-generated work separate from my own
  decisions.
