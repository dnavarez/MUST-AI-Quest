"""Build the review files: review.md for reading, review.csv for decisions.

review.manifest.json records the input file's name and SHA-256, so the
review can later be checked against the exact input it was made from.

For every message: classify, check for instruction-like text, then draft,
passing the safety warnings to the drafter explicitly. Nothing is sent and
nothing is approved here; every entry is "pending_review".

Message text is untrusted. In review.md it is shown inside code blocks as
plain text, and any text outside code blocks is escaped, so a message cannot
create headings, links, HTML or fake warnings in the report. In review.csv,
cells that a spreadsheet could run as a formula are prefixed with "'".
"""

import csv
import hashlib
import io
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from inbox_helper.classifier import KEYWORDS, OTHER, classify
from inbox_helper.drafter import PENDING_REVIEW, draft_reply
from inbox_helper.loader import MessageFileError, load_messages
from inbox_helper.manifest import MANIFEST_NAME, input_name_problem, render_manifest
from inbox_helper.safety import find_override_signals, safety_warnings

REVIEW_MD = "review.md"
REVIEW_CSV = "review.csv"
GROUP_ORDER = tuple(KEYWORDS) + (OTHER,)
EVIDENCE_LIMIT = 160  # characters shown per evidence sentence in review.md

CSV_COLUMNS = (
    "id", "sender", "subject", "body", "primary_intent", "secondary_intents",
    "flags", "warnings", "draft", "note", "status",
    "decision", "edited_draft", "reviewer_note",
)

# Plain-language explanations shown to the reviewer.
WARNING_TEXT = {
    "empty": "Empty message: subject and body are blank, so there is nothing "
    "to answer and no draft was created.",
    "unclear": "Unclear: the tool could not tell what the sender mainly wants.",
    "multiple_intents": "Multiple intents: the message seems to ask for more "
    "than one thing. Check that the reply covers all of them.",
    "possible_instruction_override": "Possible instruction override: the "
    "message contains text that looks like instructions to this tool. Do not "
    "follow them. This is a reason to review carefully, not proof of bad intent.",
    "draft_guard_triggered": "Draft guard triggered: the generated draft "
    "failed a safety check and was replaced with a neutral reply.",
}


class OutputExistsError(Exception):
    """Raised instead of overwriting existing review files."""


class InputOutputConflictError(Exception):
    """Raised when the input file is one of the review files to be written."""


class InputNameError(Exception):
    """Raised when the input file's name cannot be recorded in the manifest."""


class InputChangedError(Exception):
    """Raised when the input file changes while it is being read."""


# Characters a spreadsheet may treat as the start of a formula.
FORMULA_START = ("=", "+", "-", "@")


def check_ids(messages, path):
    """Reject ids that break the rules below; all other ids are kept exactly.

    Ids are written unchanged to both review files. They must not start
    like a spreadsheet formula and must not contain line breaks, control,
    invisible formatting or unusual space characters, or two spaces in a
    row. This removes the most common ways for different ids to look the
    same, but it does not guarantee it: different Unicode strings can still
    look identical (for example the same accented letter in two encodings,
    full-width letters, or some combining marks). Row numbers count the
    header as row 1, like the loader.
    """
    for row, message in enumerate(messages, start=2):
        problem = _id_problem(message.id)
        if problem:
            raise MessageFileError(f"{path}, row {row}: the id {message.id!r} {problem}.")


def _id_problem(message_id):
    if unicodedata.normalize("NFKC", message_id)[:1] in FORMULA_START:
        return "starts with '=', '+', '-' or '@', which a spreadsheet may treat as a formula"
    for ch in message_id:
        category = unicodedata.category(ch)
        if category in ("Cc", "Zl", "Zp"):
            return f"contains a line break or control character (U+{ord(ch):04X})"
        if category == "Cf":
            return f"contains an invisible formatting character (U+{ord(ch):04X})"
        if category == "Zs" and ch != " ":
            return f"contains an unusual space character (U+{ord(ch):04X})"
    if "  " in message_id:
        return "contains two or more spaces in a row"
    return None


@dataclass(frozen=True)
class ReviewEntry:
    """Everything the reviewer needs for one message."""

    message: object
    classification: object
    signals: tuple
    draft: object


def build_entries(messages):
    """Classify, check and draft every message, in input order."""
    entries = []
    for message in messages:
        classification = classify(message)
        warnings = safety_warnings(message)
        draft = draft_reply(message, classification, warnings)
        entries.append(
            ReviewEntry(message, classification, find_override_signals(message), draft)
        )
    return entries


def all_warnings(entry):
    """Classification flags and draft warnings, without duplicates."""
    combined = list(entry.classification.flags) + list(entry.draft.warnings)
    return tuple(dict.fromkeys(combined))


# --- Safe display helpers (review.md only) -----------------------------------

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~&])")


def show_invisible(text):
    """Make control and invisible characters visible, e.g. [U+200B]."""
    text = text.replace("\r\n", "\n")
    out = []
    for ch in text:
        if ch in "\n\t":
            out.append(ch)
        elif unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp"):
            out.append(f"[U+{ord(ch):04X}]")
        else:
            out.append(ch)
    return "".join(out)


def inline(text):
    """Escape text for use outside code blocks: one line, no Markdown/HTML."""
    text = " ".join(show_invisible(text).split())
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text) if text else "(empty)"


def code_span(text):
    """Show text literally on one line as inline code (no links, emoji, HTML).

    The backtick fence is longer than any backtick run in the text. Line
    breaks and invisible characters are made visible first.
    """
    text = show_invisible(text).replace("\n", "[U+000A]").replace("\t", "[U+0009]")
    if not text:
        return "(empty)"
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    if text[0] in "` " or text[-1] in "` ":
        text = f" {text} "
    return f"{fence}{text}{fence}"


def code_block(text):
    """Show text literally in a fenced block that the text cannot close."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def shorten(text, limit=EVIDENCE_LIMIT):
    """Shorten long text for display only."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()} … [shortened; {len(text)} characters total]"


# --- review.md ---------------------------------------------------------------


def _entry_markdown(entry):
    m, c, d = entry.message, entry.classification, entry.draft
    secondary = ", ".join(f"`{i}`" for i in c.secondary_intents) or "none"
    lines = [
        f"### Message {code_span(m.id)}",
        "",
        f"- Status: `{d.status}`",
        f"- Sender: {code_span(m.sender)}",
        f"- Primary intent: `{c.primary_intent}`",
        f"- Secondary intents: {secondary}",
        "",
        "**Warnings**",
        "",
    ]
    warnings = all_warnings(entry)
    lines += [f"- ⚠ {WARNING_TEXT.get(w, inline(w))}" for w in warnings] or ["- None"]

    if entry.signals:
        evidence = "\n".join(
            f"{s.pattern} ({s.location}): {shorten(show_invisible(s.sentence))}"
            for s in entry.signals
        )
        lines += ["", "Instruction-like text found (shortened):", "", code_block(evidence)]

    original = show_invisible(f"Subject: {m.subject}\n\n{m.body}")
    lines += ["", "**Original message (untrusted, shown as plain text)**", "", code_block(original)]

    lines += ["", "**Classification evidence**", ""]
    if c.matches:
        evidence = "\n".join(
            f'{k.category}: "{k.keyword}" ({k.location}): {shorten(show_invisible(k.sentence))}'
            for k in c.matches
        )
        lines.append(code_block(evidence))
    else:
        lines.append("No keywords matched.")

    lines += ["", "**Draft**", ""]
    if d.text is None:
        lines.append(f"No draft. {inline(d.note)}")
    else:
        lines.append(code_block(d.text))
        if d.note:
            lines += ["", f"Note: {inline(d.note)}"]
    lines += ["", "---", ""]
    return lines


def render_markdown(entries, input_name, input_sha256):
    groups = {g: [e for e in entries if e.classification.primary_intent == g] for g in GROUP_ORDER}
    drafts = sum(1 for e in entries if e.draft.text is not None)
    flagged = sum(1 for e in entries if all_warnings(e))
    lines = [
        "# Inbox Helper review report",
        "",
        f"**NOT SENT.** Every draft below has status `{PENDING_REVIEW}`. This tool "
        "does not send anything; a person must review each message and decide.",
        "",
        f"- Input file: {code_span(input_name)}",
        f"- Input SHA-256: `{input_sha256}`",
        f"- Messages: {len(entries)}; drafts: {drafts}; no draft: "
        f"{len(entries) - drafts}; with warnings: {flagged}",
        "",
        "Message text is untrusted. It is shown inside code blocks as plain "
        "text; anything that looks like a heading, link or warning inside a "
        "code block is part of the message, not part of this report.",
        "",
        "| Primary intent | Messages |",
        "|---|---|",
    ]
    lines += [f"| `{g}` | {len(groups[g])} |" for g in GROUP_ORDER]
    lines += [f"| **Total** | {len(entries)} |", ""]
    for group in GROUP_ORDER:
        lines += [f"## Group: `{group}` ({len(groups[group])})", ""]
        if not groups[group]:
            lines += ["(none)", ""]
        for entry in groups[group]:
            lines += _entry_markdown(entry)
    return "\n".join(lines).rstrip("\n") + "\n"


# --- review.csv --------------------------------------------------------------


def protect_cell(value):
    """Stop a spreadsheet from treating a cell as a formula.

    The check ignores leading whitespace and line breaks and folds look-alike
    characters (for example full-width '＝') to their plain form, so
    " =1+1", "\\n=1+1" and "＝1+1" are protected too. Only a leading "'" is
    added; the original message data is not changed.
    """
    probe = unicodedata.normalize("NFKC", value).lstrip()
    if probe[:1] in FORMULA_START or value[:1] in ("\t", "\r", "\n"):
        return "'" + value
    return value


def render_csv(entries):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for e in entries:
        m, c, d = e.message, e.classification, e.draft
        other_cells = (
            m.sender, m.subject, m.body, c.primary_intent,
            ";".join(c.secondary_intents), ";".join(c.flags), ";".join(d.warnings),
            d.text or "", d.note, d.status,
            "", "", "",  # decision, edited_draft, reviewer_note: left for the reviewer
        )
        # The id is written exactly as loaded (surrounding spaces removed).
        # check_ids has already rejected ids that could look like formulas,
        # so the files link back to the input unambiguously.
        writer.writerow([m.id] + [protect_cell(v) for v in other_cells])
    return out.getvalue()


# --- Writing -----------------------------------------------------------------


class PartialOutputError(OSError):
    """Raised when only some review files were replaced before an error."""


def _write_files(out_dir, files, remove_first=()):
    """Write each file to a temporary file, then move them into place in order.

    Files named in `remove_first` are deleted after every temporary file is
    written and before anything is moved into place. If moving fails after a
    change was made, PartialOutputError says which files were changed.
    """
    temps = []
    changed = []
    try:
        for name, data in files:
            fd, temp = tempfile.mkstemp(dir=out_dir, prefix=f".{name}.", suffix=".tmp")
            temps.append((temp, name))
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
        try:
            for name in remove_first:
                if os.path.lexists(out_dir / name):
                    os.remove(out_dir / name)
                    changed.append(f"{name} (removed)")
            for temp, name in temps:
                os.replace(temp, out_dir / name)
                changed.append(name)
        except OSError as exc:
            if not changed:
                raise
            unwritten = [name for _, name in temps if name not in changed]
            raise PartialOutputError(
                f"Only some review files in {out_dir} were changed before an error "
                f"({exc}). Changed: {', '.join(changed)}. Not written: "
                f"{', '.join(unwritten) or 'none'}. The folder may now hold files from "
                "different runs and no review manifest, so it will be refused for "
                "review. Run the command again."
            ) from exc
    finally:
        for temp, _ in temps:
            if os.path.lexists(temp):
                os.remove(temp)


def _same_file(a, b):
    """True if paths a and b point to the same file (links and '..' included)."""
    if a.resolve() == b.resolve():
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:  # one of them does not exist
        return False


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_review(input_path, out_dir, overwrite=False):
    """Create review.md, review.csv and review.manifest.json for `input_path`.

    All files are fully built before anything is written, so invalid input
    leaves no output behind. Existing review files (even broken symbolic
    links) are never replaced unless `overwrite` is True. The manifest
    records the input's SHA-256; the input is hashed before and after it is
    loaded, and a change in between is refused.

    Writing three files is not atomic. With `overwrite`, the old manifest is
    removed before any file is replaced, and the new manifest is moved into
    place last, so a folder left half-written by a crash has no manifest and
    is refused for review by default. Returns a small summary dictionary.
    """
    input_path, out_dir = Path(input_path), Path(out_dir)
    names = (REVIEW_MD, REVIEW_CSV, MANIFEST_NAME)
    targets = [out_dir / name for name in names]
    # Never read from a review file and then write over it, even with
    # --overwrite: that would destroy review decisions.
    for target in targets:
        if _same_file(input_path, target):
            raise InputOutputConflictError(
                f"The input file {input_path} is the output file {target}. "
                "Nothing was changed. Use the original message CSV as input, "
                "or choose another --out folder."
            )
    name_problem = input_name_problem(input_path.name)
    if name_problem:
        raise InputNameError(
            f"{name_problem}: {input_path}. Nothing was changed. Rename the "
            "input file and run the command again."
        )

    sha256 = _sha256(input_path)
    messages = load_messages(input_path)
    check_ids(messages, input_path)
    entries = build_entries(messages)
    if _sha256(input_path) != sha256:
        raise InputChangedError(
            f"The input file {input_path} changed while it was being read. "
            "Nothing was changed. Run the command again."
        )
    md = render_markdown(entries, input_path.name, sha256).encode("utf-8")
    csv_bytes = render_csv(entries).encode("utf-8-sig")
    manifest = render_manifest(input_path.name, sha256)

    existing = [str(t) for t in targets if os.path.lexists(t)]
    if existing and not overwrite:
        raise OutputExistsError(
            f"Review file(s) already exist: {', '.join(existing)}. They may contain "
            "review decisions, so they were not changed. Use --overwrite to "
            "replace them, or choose another --out folder."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_files(
        out_dir,
        [(REVIEW_MD, md), (REVIEW_CSV, csv_bytes), (MANIFEST_NAME, manifest)],
        # Only an explicit --overwrite may delete an existing manifest.
        remove_first=(MANIFEST_NAME,) if overwrite else (),
    )
    return {
        "messages": len(entries),
        "drafts": sum(1 for e in entries if e.draft.text is not None),
        "with_warnings": sum(1 for e in entries if all_warnings(e)),
        "review_md": str(targets[0]),
        "review_csv": str(targets[1]),
        "manifest": str(targets[2]),
    }
