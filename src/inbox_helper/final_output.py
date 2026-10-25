"""Build the finalized outputs from a checked review (Stage 4b-1).

The functions here only turn the result of finalize.validate_review into
text: approved_unsent.csv and approved_unsent.md. They read and write no
files and send nothing. Only approved and edited replies become output
rows; rejected and pending messages appear only as counts and ids in the
Markdown report.

Message fields always come from the entries rebuilt from the input file,
never from review-file cells. Every CSV cell goes through protect_cell.
In the Markdown report, untrusted text is shown only through the safe
helpers of review.md (code blocks, inline code), so it cannot create
headings, links, HTML or fake warnings.

Not implemented here: binding the review file to its input, writing the
files, and the finalize command.
"""

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass

from inbox_helper.drafter import (
    CLOSING,
    FALLBACK_BODY,
    GREETING,
    SECONDARY_SENTENCES,
    TEMPLATES,
    check_draft,
)
from inbox_helper.finalize import DECISIONS, has_content
from inbox_helper.review import (
    WARNING_TEXT,
    all_warnings,
    code_block,
    code_span,
    protect_cell,
    show_invisible,
)

APPROVED_UNSENT = "approved_unsent"
FINAL_DECISIONS = ("approve", "edit")
FINAL_COLUMNS = (
    "id", "sender", "subject", "body", "primary_intent", "warnings",
    "decision", "ai_draft", "edited_draft", "final_reply", "reply_warnings",
    "reviewer_note", "status",
)

# A placeholder is any placeholder used in the drafter's templates, or square
# brackets holding a name, optionally followed by a comma or colon and a
# description. The name is one or more words separated by single spaces;
# each word is upper-case characters (str.isupper: accented and other
# scripts too), digits 0-9, "_", "-" or "/", and the name has at least
# three upper-case characters in a row. Whitespace may follow the name
# (before "]", "," or ":"), and the description may span lines. Words in
# the name are not checked by check_draft; only the description is.
# Placeholders: [DATE], [FOLLOW-UP], [DATE/TIME], [FIRST_NAME], [Q3 DATE],
# [DÉTAIL], [DATE ], [NOTE: call back]. Not placeholders: [OK], [sic], [1],
# [e.g.], [Date], [$500], or a "[" that is never closed.
_BRACKETED = re.compile(r"\[[^\[\]]*\]")
_SEPARATOR = re.compile(r"[,:]")
_NAME_WORD_EXTRAS = set("0123456789_-/")
TEMPLATE_PLACEHOLDERS = frozenset(
    found
    for text in (GREETING, CLOSING, FALLBACK_BODY, *TEMPLATES.values(), *SECONDARY_SENTENCES.values())
    for found in _BRACKETED.findall(text)
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Provenance:
    """Where the finalized replies came from, as given by the caller."""

    input_name: str
    input_sha256: str | None  # None: the review was not bound to its input
    review_name: str
    review_sha256: str

    def __post_init__(self):
        for name in ("input_sha256", "review_sha256"):
            value = getattr(self, name)
            if value is None and name == "input_sha256":
                continue
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise ValueError(f"{name} must be 64 lower-case hexadecimal characters")


def finalized(reviewed):
    """The approved and edited entries, in input order.

    Raises ValueError if an entry is not what validate_review returns: an
    unknown decision, a final reply that is not the rebuilt AI draft
    (approve) or the edited text (edit), a final decision for a message
    without an AI draft, a blank edit, or edited text outside an edit.
    """
    for r in reviewed:
        expected = {"approve": r.entry.draft.text, "edit": r.edited_draft}.get(r.decision)
        final = r.decision in FINAL_DECISIONS
        if (
            r.decision not in DECISIONS + (None,)
            or r.final_reply != expected
            or (final and (r.entry.draft.text is None or not has_content(r.final_reply)))
            or (r.decision != "edit" and r.edited_draft)
        ):
            raise ValueError(
                f"entry {r.entry.message.id!r} is not a checked review decision; "
                "use finalize.validate_review"
            )
    return [r for r in reviewed if r.decision in FINAL_DECISIONS]


def _split_placeholder(bracketed):
    """(name, description) of a bracketed text; description is "" if absent."""
    inner = bracketed[1:-1]
    separator = _SEPARATOR.search(inner)
    if separator is None:
        return inner, ""
    return inner[:separator.start()], inner[separator.end():]


def _is_placeholder_name(name):
    words = name.rstrip().split(" ")
    if not all(w and all(ch.isupper() or ch in _NAME_WORD_EXTRAS for ch in w) for w in words):
        return False
    run = longest = 0
    for ch in name:
        run = run + 1 if ch.isupper() else 0
        longest = max(longest, run)
    return longest >= 3


def is_placeholder(bracketed):
    """True if `bracketed` (text from "[" to "]") is a placeholder."""
    return bracketed in TEMPLATE_PLACEHOLDERS or _is_placeholder_name(
        _split_placeholder(bracketed)[0]
    )


def placeholders(text):
    """Unresolved placeholders in `text`, without duplicates, in text order."""
    found = [p for p in _BRACKETED.findall(text) if is_placeholder(p)]
    return tuple(dict.fromkeys(found))


def reply_warnings(reviewed):
    """Non-blocking warnings about a final reply; they never change the decision.

    Unresolved placeholders for every final reply, and the drafter's checks
    (commitment wording, currency, numbers or dates not in the message,
    length) for edited replies; approved AI drafts already passed them.
    """
    text = reviewed.final_reply
    warnings = [f"unresolved placeholder: {p}" for p in placeholders(text)]
    if reviewed.decision == "edit":
        warnings += check_draft(_without_placeholders(text), reviewed.entry.message)
    if protect_cell(text) != text:
        warnings.append(
            "the CSV cell starts with a protective ' (formula protection); "
            "it is not part of the reply"
        )
    return tuple(warnings)


def _without_placeholders(text):
    """`text` for check_draft: placeholder names blanked, all else kept as text.

    check_draft ignores everything in square brackets, which is right for
    template drafts. In an edited reply, bracketed words that are not
    placeholders will be sent, and a placeholder's description may hold a
    claim the reviewer meant to send, so both are checked. Only the name of
    a placeholder (for example DATE in [DATE] or NOTE in [NOTE: ...]) is
    left out.
    """
    for p in placeholders(text):
        text = text.replace(p, f" {_split_placeholder(p)[1]} ")
    return text.replace("[", " ").replace("]", " ")


# --- approved_unsent.csv -----------------------------------------------------


def render_final_csv(reviewed):
    """approved_unsent.csv as text: one row per approved or edited reply."""
    rows = [FINAL_COLUMNS]
    for r in finalized(reviewed):
        m, c, d = r.entry.message, r.entry.classification, r.entry.draft
        rows.append((
            m.id, m.sender, m.subject, m.body, c.primary_intent,
            ";".join(all_warnings(r.entry)), r.decision, d.text,
            r.edited_draft, r.final_reply, "; ".join(reply_warnings(r)),
            r.reviewer_note, APPROVED_UNSENT,
        ))
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    for row in rows:
        # Every cell, ids included. check_ids already rejects ids that would
        # need protection, so ids come out unchanged.
        writer.writerow([protect_cell(value) for value in row])
    return out.getvalue()


# --- approved_unsent.md ------------------------------------------------------


def _id_list(entries):
    return [f"- {code_span(r.entry.message.id)}" for r in entries] or ["(none)"]


def _text_block(text):
    """Untrusted multi-line text, literally, with invisible characters shown."""
    return code_block(show_invisible(text)) if has_content(text) else "(none)"


def _entry_markdown(r):
    m, c, d = r.entry.message, r.entry.classification, r.entry.draft
    lines = [
        f"### Message {code_span(m.id)}",
        "",
        f"- Decision: `{r.decision}`",
        f"- Sender: {code_span(m.sender)}",
        f"- Primary intent: `{c.primary_intent}`",
        "",
        "**Warnings**",
        "",
    ]
    lines += [f"- ⚠ {WARNING_TEXT.get(w, code_span(w))}" for w in all_warnings(r.entry)] or ["- None"]
    lines += ["", "**Reply warnings** (not blocking; check before sending)", ""]
    lines += [f"- {code_span(w)}" for w in reply_warnings(r)] or ["- None"]
    lines += ["", "**Reviewer note**", "", _text_block(r.reviewer_note)]
    lines += ["", "**Final reply (not sent)**", "", _text_block(r.final_reply)]
    if r.decision == "edit":
        lines += ["", "**AI draft before editing**", "", code_block(d.text)]
    lines += ["", "---", ""]
    return lines


def render_final_markdown(reviewed, provenance):
    """approved_unsent.md as text, for reading before sending by hand."""
    counts = Counter(r.decision for r in reviewed)
    final = finalized(reviewed)
    if provenance.input_sha256 is None:
        binding = (
            "- Input SHA-256: not available. **Input binding was not checked:** "
            "the review file was not linked to its input file by a fingerprint; "
            "only the message content was compared."
        )
    else:
        binding = f"- Input SHA-256: `{provenance.input_sha256}`"
    lines = [
        "# Inbox Helper approved replies",
        "",
        "**NOT SENT.** Nothing in this file has been sent, and this tool cannot "
        f"send messages. Every reply below has status `{APPROVED_UNSENT}`. To "
        "send one, copy it into your own email tool and send it yourself.",
        "",
        f"- Input file: {code_span(provenance.input_name)}",
        binding,
        f"- Review file: {code_span(provenance.review_name)}",
        f"- Review file SHA-256: `{provenance.review_sha256}`",
        f"- Messages: {len(reviewed)}; approved: {counts['approve']}; edited: "
        f"{counts['edit']}; rejected: {counts['reject']}; pending: {counts[None]}",
        "",
        "Message and reviewer text is untrusted. It is shown inside code blocks "
        "as plain text, with invisible characters shown as `[U+XXXX]`; copy "
        "replies from the CSV file, not from this report. A `'` at the start "
        "of a CSV cell was added to stop spreadsheets running it as a formula; "
        "it is not part of the reply, so remove it when copying.",
        "",
        f"## Pending, not finalized ({counts[None]})",
        "",
        *_id_list([r for r in reviewed if r.decision is None]),
        "",
        f"## Rejected ({counts['reject']})",
        "",
        *_id_list([r for r in reviewed if r.decision == "reject"]),
        "",
        f"## Replies to send manually ({len(final)})",
        "",
    ]
    if not final:
        lines += ["(none)", ""]
    for r in final:
        lines += _entry_markdown(r)
    return "\n".join(lines).rstrip("\n") + "\n"
