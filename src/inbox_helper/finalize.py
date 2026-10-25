"""Check a completed review.csv against the original messages (Stage 4a).

The original input file is the source of truth. Its messages are loaded and
drafted again with the same deterministic pipeline as the draft command, and
every review row must match that rebuilt entry before its decision is used:

- rows are matched by exact id, never by position (sorting is fine);
- the cells the tool generated (sender to status) must still match the
  rebuilt values; the review file's draft is never trusted as the AI draft;
- ids are never repaired. An unknown id is only compared with the unmatched
  messages to explain what probably happened, and the run is refused.

Nothing is written and nothing is sent here. Problems with the review file
(or with how it relates to the input) raise ReviewFileError listing the
problems found (up to MAX_ERRORS shown), so a person can fix most of them at
once. If the review file's structure is broken, the row checks do not run,
and an unsupported decision stops further checks of that row. Problems
reading the input file itself come from the existing loader instead
(MessageFileError, or file and decoding errors). Error messages name rows,
ids and columns, never message text.

Planned for Stage 4b (not implemented here): unresolved placeholders in a
final reply will be reported as a warning, never a refusal. A placeholder is
any placeholder used in the drafter's templates, or square brackets holding
an upper-case word of three or more letters, optionally followed by more
upper-case words and then a comma or colon with a description, e.g. [DATE],
[DETAILS NEEDED], [ANSWER OR NEXT STEP]. [OK], [sic], [1] and [e.g.] are not
placeholders.
"""

import csv
import io
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from inbox_helper.drafter import PENDING_REVIEW
from inbox_helper.loader import load_messages
from inbox_helper.review import (
    CSV_COLUMNS,
    ReviewEntry,
    _same_file,
    build_entries,
    check_ids,
    protect_cell,
)
from inbox_helper.safety import OVERRIDE_WARNING

REVIEW_COLUMNS = CSV_COLUMNS
SOURCE_COLUMNS = ("sender", "subject", "body")
# Cells the tool generated; they must still match the rebuilt entry. The
# status column is checked separately and must be exactly pending_review.
COMPARED_COLUMNS = SOURCE_COLUMNS + (
    "primary_intent", "secondary_intents", "flags", "warnings", "draft", "note",
)
# Columns only a review file has. An input file with any of them is
# probably a review file given by mistake, and its edited text must not
# become the "original" the review is checked against.
REVIEW_ONLY_COLUMNS = (
    "primary_intent", "secondary_intents", "draft", "status",
    "decision", "edited_draft", "reviewer_note",
)
DECISIONS = ("approve", "edit", "reject")
MAX_ERRORS = 50  # problems shown in one error message
ID_DISPLAY_LIMIT = 40  # characters of an input id shown in error messages
MAX_POSITIONS_SHOWN = 5  # column positions listed in one header problem

# Ids and decisions read from the review file are untrusted: a cell may hold
# pasted message text, so only their length is shown unless they look safe.
# An id is shown if it is a short code (one word of letters, digits and a
# little punctuation, optionally with spaces around it) with at most
# MAX_ID_DIGITS_SHOWN digits in total. Long numbers such as card, account
# and most phone numbers are therefore hidden even when written with
# separators (4111-1111-1111-1111, acct:12345678); a value with fewer
# digits, such as a short local phone number, may still be shown. A
# decision is shown only if it is ASCII letters alone, at most 12 of them.
# A short code taken from a message can still be shown; that remaining risk
# is accepted.
_SAFE_ID = re.compile(r" *[A-Za-z0-9._:/#+?!-]{1,20} *")
MAX_ID_DIGITS_SHOWN = 7
_SAFE_DECISION = re.compile(r"[A-Za-z]{1,12}")

# Values a spreadsheet writes when a formula fails (Excel, Google Sheets,
# LibreOffice). Only a whole cell is matched, so "#1 priority" is fine.
SPREADSHEET_ERRORS = {
    "#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A",
    "#SPILL!", "#CALC!", "#ERROR!", "#GETTING_DATA",
}
_LIBREOFFICE_ERROR = re.compile(r"Err:\d{3}")


class ReviewFileError(ValueError):
    """Raised when the review file cannot be used.

    `problems` holds the problems found; the message shows at most
    MAX_ERRORS of them and says how many more there are.
    """

    def __init__(self, problems):
        self.problems = list(problems)
        lines = ["The review file cannot be used. Nothing was changed."]
        lines += [f"- {p}" for p in self.problems[:MAX_ERRORS]]
        hidden = len(self.problems) - MAX_ERRORS
        if hidden > 0:
            lines.append(f"... and {hidden} more problem(s).")
        super().__init__("\n".join(lines))


@dataclass(frozen=True)
class ReviewRow:
    """One row of the review file; row_number counts the header as row 1."""

    row_number: int
    cells: dict  # every column in REVIEW_COLUMNS -> cell text


@dataclass(frozen=True)
class ReviewedEntry:
    """A rebuilt entry with the reviewer's checked decision."""

    entry: ReviewEntry
    decision: str | None  # "approve", "edit", "reject", or None for pending
    edited_draft: str
    reviewer_note: str
    final_reply: str | None  # rebuilt AI draft (approve), edited text (edit), else None


def show_id(value):
    """An input id for error messages: escaped, quoted and shortened.

    Only for ids from the input file. Text from the review file goes
    through show_untrusted.
    """
    if len(value) > ID_DISPLAY_LIMIT:
        return ascii(value[:ID_DISPLAY_LIMIT]) + "..."
    return ascii(value)


def _not_shown(value):
    return f"({len(value)} characters, not shown)"


def show_untrusted(value):
    """A review-file id for error messages, if safe to show.

    Shown only if it is a short code with at most MAX_ID_DIGITS_SHOWN
    digits. An id with 8 or more digits in total is hidden, counting digits
    separated by punctuation too (555-123-4567); only its length is shown.
    """
    digits = sum(ch in "0123456789" for ch in value)
    if _SAFE_ID.fullmatch(value) and digits <= MAX_ID_DIGITS_SHOWN:
        return ascii(value)
    return _not_shown(value)


def show_decision(value):
    """A review-file decision for error messages, if safe to show."""
    if _SAFE_DECISION.fullmatch(value.strip()):
        return ascii(value.strip())
    return _not_shown(value)


# Letters and symbols that are displayed as blank space: Hangul fillers and
# the blank braille pattern.
_BLANK_LOOKING = {"\u115f", "\u1160", "\u3164", "\uffa0", "\u2800"}


def has_content(text):
    """True if `text` has a visible letter, digit, punctuation mark or symbol.

    Spaces and line separators (Unicode Z*), control and invisible formatting
    characters (C*: e.g. line breaks, zero-width space, soft hyphen, private
    use), combining marks and variation selectors on their own (M*), and the
    blank-looking characters above do not count. Used only to decide whether
    a cell is blank; the text itself is kept as written.
    """
    return any(
        unicodedata.category(ch)[0] in "LNPS" and ch not in _BLANK_LOOKING
        for ch in text
    )


def _lf(text):
    return text.replace("\r\n", "\n")


def normalize(text):
    """For comparing message content only: CRLF -> LF, then Unicode NFC."""
    return unicodedata.normalize("NFC", _lf(text))


def cell_matches(cell, raw):
    """True if a review cell still holds `raw`.

    Accepted: `raw` itself, or `raw` with the protective "'" that
    protect_cell adds (a spreadsheet may keep or drop it), after normalize().
    Nothing else: no trimming, no case-folding, no other apostrophes removed.
    """
    value = normalize(cell)
    return value == normalize(raw) or value == normalize(protect_cell(raw))


def is_spreadsheet_error(value):
    value = value.strip()
    return value in SPREADSHEET_ERRORS or bool(_LIBREOFFICE_ERROR.fullmatch(value))


def expected_raw(entry):
    """The values the draft command wrote, before formula protection.

    Same order and joining as review.render_csv; a test checks the two agree.
    """
    m, c, d = entry.message, entry.classification, entry.draft
    return {
        "sender": m.sender,
        "subject": m.subject,
        "body": m.body,
        "primary_intent": c.primary_intent,
        "secondary_intents": ";".join(c.secondary_intents),
        "flags": ";".join(c.flags),
        "warnings": ";".join(d.warnings),
        "draft": d.text or "",
        "note": d.note,
    }


# --- Reading the review file -------------------------------------------------


def read_review_rows(path):
    """Return the rows of the review file at `path`, in file order.

    Strict: UTF-8 (with or without a byte-order mark), valid CSV, header
    names trimmed of surrounding spaces and then exactly the review columns,
    with no duplicates and no unknown columns, in any order. Missing cells
    at the end of a row count as blank; extra cells are an error. Fully blank
    rows at the end are ignored; a blank row between rows is an error.
    """
    path = Path(path)
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        raise ReviewFileError([f"review file not found: {path}"]) from None
    except IsADirectoryError:
        raise ReviewFileError([f"the review file is a folder: {path}"]) from None
    except UnicodeDecodeError:
        raise ReviewFileError([
            f"the review file is not UTF-8 text: {path}. In a spreadsheet "
            "program, save it as 'CSV UTF-8'."
        ]) from None
    except OSError as exc:
        raise ReviewFileError([f"could not read the review file {path}: {exc}"]) from None

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        records = list(reader)
    except csv.Error as exc:
        raise ReviewFileError([
            f"the review file {path} is not a valid CSV file (line {reader.line_num}): {exc}"
        ]) from None

    if not records or all(_is_blank(record) for record in records):
        raise ReviewFileError([f"the review file is empty: {path}"])
    if _is_blank(records[0]):
        raise ReviewFileError([
            f"the first row of the review file {path} is blank; the header "
            "must be on row 1. Delete the blank row(s) at the top."
        ])
    header = [name.strip() for name in records[0]]
    _check_header(header, path)

    data = records[1:]
    while data and _is_blank(data[-1]):
        data.pop()
    rows, problems = [], []
    for row_number, record in enumerate(data, start=2):
        if _is_blank(record):
            problems.append(f"row {row_number}: the row is blank; remove it.")
            continue
        if len(record) > len(header):
            problems.append(
                f"row {row_number}: the row has {len(record)} cells but the "
                f"header has {len(header)}."
            )
            continue
        cells = dict(zip(header, record + [""] * (len(header) - len(record))))
        rows.append(ReviewRow(row_number, cells))
    if problems:
        raise ReviewFileError(problems)
    return rows


def _is_blank(record):
    return not any(cell.strip() for cell in record)


def _list_positions(positions):
    """Column positions (1 = first column) for error messages, at most a few."""
    shown = ", ".join(map(str, positions[:MAX_POSITIONS_SHOWN]))
    hidden = len(positions) - MAX_POSITIONS_SHOWN
    return f"{shown} and {hidden} more" if hidden > 0 else shown


def _check_header(header, path):
    """Raise ReviewFileError unless `header` names exactly the review columns.

    A header cell can hold message text (the header row may have been
    deleted, or text pasted into it), so header text is never shown, except
    for names from REVIEW_COLUMNS. Unknown names are reported by column
    position. If fewer than half of the review columns are named, the row is
    reported as not being the header at all.
    """
    if len(header) == 1 and ";" in header[0]:
        raise ReviewFileError([
            f"the review file {path} seems to use ';' instead of ',' between "
            "columns. Save it from the spreadsheet program as comma-separated "
            "'CSV UTF-8'."
        ])
    expected = f"The review file must have exactly these columns: {', '.join(REVIEW_COLUMNS)}."
    known = {name for name in header if name in REVIEW_COLUMNS}
    if len(known) * 2 < len(REVIEW_COLUMNS):
        raise ReviewFileError([
            f"the first row of the review file {path} is not the review header "
            "(it may have been deleted or replaced).",
            expected,
        ])
    problems = []
    named = [name for name in header if name]
    if len(named) < len(header):
        problems.append(
            f"{len(header) - len(named)} column(s) have no name, often empty "
            "columns at the end of the sheet; delete them."
        )
    duplicates = [
        name for name, count in Counter(named).items()
        if count > 1 and name in REVIEW_COLUMNS
    ]
    if duplicates:
        problems.append(f"duplicate column name(s): {', '.join(duplicates)}.")
    unknown = [
        position for position, name in enumerate(header, start=1)
        if name and name not in REVIEW_COLUMNS
    ]
    if unknown:
        problems.append(
            f"{len(unknown)} unknown column name(s), in column(s) "
            f"{_list_positions(unknown)} (names not shown)."
        )
    missing = [name for name in REVIEW_COLUMNS if name not in header]
    if missing:
        problems.append(f"missing column(s): {', '.join(missing)}.")
    if problems:
        problems.append(expected)
        raise ReviewFileError(problems)


# --- Matching and checking ---------------------------------------------------


def _source_matches(row, entry):
    raw = expected_raw(entry)
    return all(cell_matches(row.cells[c], raw[c]) for c in SOURCE_COLUMNS)


def match_rows(entries, rows):
    """Match review rows to entries by exact id.

    Returns ({id: row}, problems), where problems are (row_number, text)
    pairs; problems about messages without a row have row_number None.
    """
    by_id = {e.message.id: e for e in entries}
    first_row = {}
    matched, unknown, problems = {}, [], []
    for row in rows:
        rid = row.cells["id"]
        where = f"row {row.row_number}"
        if not rid.strip():
            problems.append((row.row_number, f"{where}: the id is blank."))
        elif rid in first_row:
            # A real input id is trusted for display; any other id is not.
            shown = show_id(rid) if rid in by_id else show_untrusted(rid)
            problems.append((
                row.row_number,
                f"{where}: the id {shown} is a duplicate of row {first_row[rid]}.",
            ))
        else:
            first_row[rid] = row.row_number
            if rid in by_id:
                matched[rid] = row
            else:
                unknown.append(row)

    unmatched = [e for e in entries if e.message.id not in matched]
    suggested = {}  # id already suggested in a hint -> row it was suggested for
    for row in unknown:
        problems.append((
            row.row_number, _unknown_id_problem(row, by_id, first_row, unmatched, suggested)
        ))
    for entry in unmatched:
        problems.append((
            None,
            f"message {show_id(entry.message.id)} from the input file has no "
            "row with that id in the review file.",
        ))
    return matched, problems


def _unknown_id_problem(row, by_id, first_row, unmatched, suggested):
    """Explain an unknown id without repairing it.

    A hint never suggests an id that another row already has or that was
    already suggested for another row, since following it would create a
    duplicate. The suggested id comes from the input file; the unknown id
    is shown only if show_untrusted considers it safe.
    """
    rid = row.cells["id"]
    text = f"row {row.row_number}: the id {show_untrusted(rid)} is not in the input file."
    trimmed = rid.strip()
    if trimmed in by_id:
        if trimmed in first_row:
            return (
                f"{text} Without the extra spaces around it, it is the id of "
                f"row {first_row[trimmed]}, so this row is probably a duplicate."
            )
        if trimmed in suggested:
            return (
                f"{text} Without the extra spaces around it, it is "
                f"{show_id(trimmed)}, which row {suggested[trimmed]} also seems "
                "to be, so one of these rows is probably a duplicate."
            )
        suggested[trimmed] = row.row_number
        return (
            f"{text} It has extra spaces around it; restore it to "
            f"{show_id(trimmed)}. Ids are never repaired automatically."
        )
    candidates = [e for e in unmatched if _source_matches(row, e)]
    if len(candidates) == 1:
        original_id = candidates[0].message.id
        original = show_id(original_id)
        if original_id in suggested:
            return (
                f"{text} Its sender, subject and body match message {original}, "
                f"which row {suggested[original_id]} also seems to be, so one of "
                "these rows is probably a duplicate."
            )
        suggested[original_id] = row.row_number
        return (
            f"{text} Its sender, subject and body match message {original}, so "
            "a spreadsheet program has probably changed the id. Restore it to "
            f"{original}, or import the id column as Text. Ids are never "
            "repaired automatically."
        )
    if len(candidates) > 1:
        return (
            f"{text} Its sender, subject and body match {len(candidates)} "
            "messages in the input file, so it cannot be told which one it "
            "belongs to."
        )
    return text


def check_content(entry, row):
    """Problems where the row no longer matches its rebuilt entry."""
    where = f"row {row.row_number} (id {show_id(entry.message.id)})"
    raw = expected_raw(entry)
    problems = []
    for column in COMPARED_COLUMNS:
        if cell_matches(row.cells[column], raw[column]):
            continue
        if column in SOURCE_COLUMNS:
            problems.append(f"{where}: the {column} cell does not match the input file.")
        elif column == "draft":
            problems.append(
                f"{where}: the draft cell does not match the draft rebuilt from "
                "the input file. Write changes in edited_draft. If the input "
                "file or the program changed, run the draft command again."
            )
        else:
            problems.append(
                f"{where}: the {column} cell does not match the value rebuilt "
                "from the input file. If the input file or the program changed, "
                "run the draft command again."
            )
    if row.cells["status"] != PENDING_REVIEW:
        problems.append(
            f"{where}: the status cell must stay {PENDING_REVIEW!r}; record the "
            "choice in the decision column."
        )
    return problems


def check_decision(entry, row):
    """Return (ReviewedEntry or None, problems) for a row whose content matched."""
    where = f"row {row.row_number} (id {show_id(entry.message.id)})"
    raw_decision = row.cells["decision"]
    decision = raw_decision.strip().lower()
    edited = _lf(row.cells["edited_draft"])
    note = _lf(row.cells["reviewer_note"])
    has_edit = has_content(edited)
    problems = []

    if is_spreadsheet_error(note):
        problems.append(
            f"{where}: reviewer_note holds the spreadsheet error {note.strip()!r}; "
            "the note was probably turned into a formula. Type it again as text."
        )
    if decision and decision not in DECISIONS:
        problems.append(
            f"{where}: the decision {show_decision(raw_decision)} is not supported. "
            "Use approve, edit or reject, or leave it blank."
        )
        return None, problems

    if decision == "edit":
        if is_spreadsheet_error(edited):
            problems.append(
                f"{where}: edited_draft holds the spreadsheet error "
                f"{edited.strip()!r}; the reply was probably turned into a "
                "formula. Type it again as text."
            )
        elif not has_edit:
            problems.append(f"{where}: the decision is edit, but edited_draft is blank.")
    elif has_edit:
        name = decision or "blank (pending)"
        problems.append(
            f"{where}: the decision is {name}, but edited_draft is filled in. "
            "Use edit to record an edited reply, or clear edited_draft."
        )

    if decision in ("approve", "edit"):
        if entry.draft.text is None:
            problems.append(
                f"{where}: this message is empty and has no draft, so it cannot "
                f"be given {decision}; reject it or leave it pending."
            )
        if OVERRIDE_WARNING in entry.draft.warnings and not has_content(note):
            problems.append(
                f"{where}: this message has the {OVERRIDE_WARNING} warning, so "
                f"{decision} needs a reviewer_note explaining the decision."
            )

    if problems:
        return None, problems
    final = {"approve": entry.draft.text, "edit": edited}.get(decision)
    # Outside "edit", edited_draft is blank (perhaps only spaces): keep "".
    kept_edit = edited if decision == "edit" else ""
    return ReviewedEntry(entry, decision or None, kept_edit, note, final), []


def validate_rows(entries, rows):
    """Check rows against rebuilt entries; return ReviewedEntry list in input order.

    Content is checked before a decision is accepted. Raises ReviewFileError
    with all problems, rows in file order first, then missing messages.
    """
    matched, problems = match_rows(entries, rows)
    reviewed = []
    for entry in entries:
        row = matched.get(entry.message.id)
        if row is None:
            continue
        content = check_content(entry, row)
        if content:
            # Suggest a swap only if the row no longer holds its own message.
            if not _source_matches(row, entry):
                others = [e for e in entries if e is not entry and _source_matches(row, e)]
                if len(others) == 1:
                    content.append(
                        f"row {row.row_number} (id {show_id(entry.message.id)}): "
                        "its sender, subject and body match "
                        f"message {show_id(others[0].message.id)}; the id may have "
                        "been changed or swapped."
                    )
            problems += [(row.row_number, p) for p in content]
            continue
        result, decision_problems = check_decision(entry, row)
        problems += [(row.row_number, p) for p in decision_problems]
        if result is not None:
            reviewed.append(result)
    if problems:
        ordered = sorted(problems, key=lambda p: (p[0] is None, p[0] or 0))
        raise ReviewFileError([text for _, text in ordered])
    return reviewed


def _refuse_review_as_input(input_path):
    """Refuse an input file that looks like a review file (even a copy).

    The loader ignores extra columns, so a review file would load as
    messages, and any text edited in it would become the "original".
    Column names are compared ignoring case and surrounding spaces. Called
    after load_messages, which has already checked the file.

    Limitation: a review file with all of these columns deleted cannot be
    told apart from a message file. Only binding the review file to its
    input (for example by the input's SHA-256) would detect that.
    """
    with input_path.open(encoding="utf-8-sig", newline="") as file:
        header = {name.strip().casefold() for name in next(csv.reader(file), [])}
    found = [name for name in REVIEW_ONLY_COLUMNS if name in header]
    if found:
        raise ReviewFileError([
            f"the input file {input_path} has review column(s) "
            f"({', '.join(found)}), so it looks like a review file. Give the "
            "original message CSV as input. If these are ordinary columns of "
            "your message file, rename or remove them."
        ])


def validate_review(input_path, review_path):
    """Check the review file against the original input file.

    Returns a ReviewedEntry for every message, in input order. Raises
    ReviewFileError for problems with the review file (or if both paths are
    the same file, or the input looks like a review file), and the loader's
    usual errors for the input file.
    Nothing is written.
    """
    input_path, review_path = Path(input_path), Path(review_path)
    if _same_file(input_path, review_path):
        raise ReviewFileError([
            f"the input file {input_path} and the review file {review_path} are "
            "the same file. Give the original message CSV as input."
        ])
    messages = load_messages(input_path)
    _refuse_review_as_input(input_path)
    check_ids(messages, input_path)
    entries = build_entries(messages)
    rows = read_review_rows(review_path)
    return validate_rows(entries, rows)
