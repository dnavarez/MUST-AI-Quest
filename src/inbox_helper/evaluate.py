"""Compare the classifier with expected labels and print a Markdown report.

Usage:
    PYTHONPATH=src python -m inbox_helper.evaluate data/eval_dev.csv

This is a measurement tool, not a test: it reports how often the
classifier agrees with the labels and never fails because a score is low.
"""

import csv
import sys
from collections import Counter
from dataclasses import dataclass

from inbox_helper.classifier import KEYWORDS, OTHER, classify
from inbox_helper.loader import load_messages

CATEGORIES = tuple(KEYWORDS) + (OTHER,)
LABEL_COLUMNS = (
    "expected_primary", "expected_secondary", "acceptable_primary",
    "case_tags", "label_status", "rationale",
)

# The four possible outcomes for one message, from best to worst.
CORRECT = "correct"
ACCEPTABLE = "acceptable"  # matches an alternative label for a debatable case
SENT_TO_REVIEW = "sent_to_review"  # said other_or_unclear; not expected, not acceptable
CONFIDENT_WRONG = "confident_wrong"  # chose a real category that is wrong

# Labels for the reconciliation table in summarize().
EXACT, INCORRECT = "exact", "incorrect"
DEFINITE, ABSTAINED = "definite", "abstained"


@dataclass(frozen=True)
class LabelledCase:
    """One message plus the labels a reviewer expects for it."""

    message: object
    expected_primary: str
    expected_secondary: tuple[str, ...]
    acceptable_primary: tuple[str, ...]
    tags: tuple[str, ...]
    label_status: str
    rationale: str


def _split(cell):
    return tuple(part.strip() for part in (cell or "").split(";") if part.strip())


def load_labelled(path):
    """Load messages (validated by the normal loader) and their labels."""
    messages = load_messages(path)
    with open(path, encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = [name for name in LABEL_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path} is missing label column(s): {', '.join(missing)}")
        rows = list(reader)

    return [
        LabelledCase(
            message=message,
            expected_primary=row["expected_primary"].strip(),
            expected_secondary=_split(row["expected_secondary"]),
            acceptable_primary=_split(row["acceptable_primary"]),
            tags=_split(row["case_tags"]),
            label_status=row["label_status"].strip(),
            rationale=row["rationale"].strip(),
        )
        for message, row in zip(messages, rows)
    ]


def outcome(case, result):
    """Put one classifier result into one of the four outcome buckets."""
    if result.primary_intent == case.expected_primary:
        return CORRECT
    if result.primary_intent in case.acceptable_primary:
        return ACCEPTABLE
    if result.primary_intent == OTHER:
        return SENT_TO_REVIEW
    return CONFIDENT_WRONG


def unexpected_secondary(case, result):
    """Secondary intents the classifier found that the labels do not expect."""
    expected = set(case.expected_secondary) | {case.expected_primary}
    return tuple(i for i in result.secondary_intents if i not in expected)


def summarize(cases, results):
    """Count everything the report needs. Returns a plain dictionary."""
    outcomes = [outcome(c, r) for c, r in zip(cases, results)]
    counts = Counter(outcomes)

    majority_label, _ = sorted(
        Counter(c.expected_primary for c in cases).items(),
        key=lambda item: (-item[1], item[0]),
    )[0] if cases else (None, 0)

    # Reconciliation table: every message lands in exactly one cell.
    # Rows: exact / acceptable / incorrect. Columns: definite / abstained.
    # (An abstention is a prediction of other_or_unclear.)
    table = Counter()
    for r, o in zip(results, outcomes):
        column = ABSTAINED if r.primary_intent == OTHER else DEFINITE
        row = {CORRECT: EXACT, ACCEPTABLE: ACCEPTABLE}.get(o, INCORRECT)
        table[row, column] += 1
    if sum(table.values()) != len(cases):
        raise AssertionError("Reconciliation table does not add up to the message count")

    expected_secondary_total = sum(len(c.expected_secondary) for c in cases)
    expected_secondary_found = sum(
        1 for c, r in zip(cases, results)
        for intent in c.expected_secondary if intent in r.secondary_intents
    )
    extra_secondary = [(c, r, unexpected_secondary(c, r)) for c, r in zip(cases, results)]

    empty_cases = [(c, r) for c, r in zip(cases, results) if "empty" in c.tags]

    per_category = {}
    for category in CATEGORIES:
        expected_n = sum(1 for c in cases if c.expected_primary == category)
        predicted_n = sum(1 for r in results if r.primary_intent == category)
        hits = sum(1 for c, r in zip(cases, results)
                   if c.expected_primary == category and r.primary_intent == category)
        per_category[category] = (expected_n, predicted_n, hits)

    per_tag = {}
    for tag in sorted({t for c in cases for t in c.tags}):
        tagged = [o for c, o in zip(cases, outcomes) if tag in c.tags]
        per_tag[tag] = Counter(tagged), len(tagged)

    return {
        "n": len(cases),
        "outcomes": outcomes,
        "counts": counts,
        "majority_label": majority_label,
        "majority_hits": sum(1 for c in cases if c.expected_primary == majority_label),
        "table": table,
        "definite_n": table[EXACT, DEFINITE] + table[ACCEPTABLE, DEFINITE] + table[INCORRECT, DEFINITE],
        "abstained_n": table[EXACT, ABSTAINED] + table[ACCEPTABLE, ABSTAINED] + table[INCORRECT, ABSTAINED],
        "secondary_total": expected_secondary_total,
        "secondary_found": expected_secondary_found,
        "extra_secondary": extra_secondary,
        "empty_n": len(empty_cases),
        "empty_flagged": sum(1 for _, r in empty_cases if "empty" in r.flags),
        "per_category": per_category,
        "per_tag": per_tag,
    }


def pct(part, whole):
    """Format 'part/whole (xx.x%)', or 'n/a' when whole is 0."""
    if whole == 0:
        return f"{part}/0 (n/a)"
    return f"{part}/{whole} ({100 * part / whole:.1f}%)"


def _short(message, limit=70):
    """One-line preview for a table cell: '[subject] body', shortened."""
    text = f"[{message.subject.strip()}] " if message.subject.strip() else ""
    text = " ".join((text + message.body).split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_report(path, cases, results):
    s = summarize(cases, results)
    n, t = s["n"], s["table"]
    definite_n, abstained_n = s["definite_n"], s["abstained_n"]
    exact = t[EXACT, DEFINITE] + t[EXACT, ABSTAINED]
    acceptable = t[ACCEPTABLE, DEFINITE] + t[ACCEPTABLE, ABSTAINED]
    statuses = Counter(c.label_status for c in cases)
    lines = [
        f"## Evaluation: `{path}`",
        "",
        f"- Messages: {n}",
        f"- Label status: {', '.join(f'{k}={v}' for k, v in sorted(statuses.items()))}",
        "",
        "### Where every message landed",
        "",
        "A *definite* prediction is one of the six real categories. An",
        "*abstention* is a prediction of `other_or_unclear`. Each message is",
        "in exactly one cell, so rows and columns add up to the totals.",
        "",
        "| Outcome | Definite | Abstention | Total |",
        "|---|---|---|---|",
    ]
    for row, label in ((EXACT, "Exact match"), (ACCEPTABLE, "Acceptable alternative"),
                       (INCORRECT, "Incorrect")):
        lines.append(
            f"| {label} | {t[row, DEFINITE]} | {t[row, ABSTAINED]} "
            f"| {t[row, DEFINITE] + t[row, ABSTAINED]} |"
        )
    lines += [
        f"| **Total** | {definite_n} | {abstained_n} | {n} |",
        "",
        "- An incorrect definite prediction is *confidently wrong*.",
        "- An incorrect abstention is *sent to review*: a real intent was",
        "  expected and `other_or_unclear` was not an acceptable alternative.",
        "",
        "### Primary-intent metrics",
        "",
        "| Metric | Numerator / denominator | Result |",
        "|---|---|---|",
        f"| Strict accuracy | exact matches / all messages (an abstention counts "
        f"only when `other_or_unclear` was expected) | {pct(exact, n)} |",
        f"| Lenient accuracy | (exact + acceptable) / all messages | {pct(exact + acceptable, n)} |",
        f"| Strict accuracy, every abstention incorrect | exact definite / all messages "
        f"| {pct(t[EXACT, DEFINITE], n)} |",
        f"| Majority baseline (always `{s['majority_label']}`) "
        f"| messages expecting that label / all messages | {pct(s['majority_hits'], n)} |",
        f"| Confidently wrong | incorrect definite / all messages | {pct(t[INCORRECT, DEFINITE], n)} |",
        f"| Sent to review | incorrect abstentions / all messages | {pct(t[INCORRECT, ABSTAINED], n)} |",
        f"| Abstention rate | abstentions / all messages | {pct(abstained_n, n)} |",
        f"| Accuracy among definite (exact) | exact definite / definite | "
        f"{pct(t[EXACT, DEFINITE], definite_n)} |",
        f"| Accuracy among definite (lenient) | (exact + acceptable) definite / definite | "
        f"{pct(t[EXACT, DEFINITE] + t[ACCEPTABLE, DEFINITE], definite_n)} |",
        f"| Empty messages flagged `empty` | flagged / messages tagged `empty` "
        f"| {pct(s['empty_flagged'], s['empty_n'])} |",
        "",
        "### Per category (strict)",
        "",
        "| Category | Expected | Predicted | Correct | Recall | Precision |",
        "|---|---|---|---|---|---|",
    ]
    for category, (expected_n, predicted_n, hits) in s["per_category"].items():
        lines.append(
            f"| `{category}` | {expected_n} | {predicted_n} | {hits} "
            f"| {pct(hits, expected_n)} | {pct(hits, predicted_n)} |"
        )

    extra = [(c, r, x) for c, r, x in s["extra_secondary"] if x]
    extra_thanks = sum(1 for _, _, x in extra if "thank_you" in x)
    lines += [
        "",
        "### Secondary intents",
        "",
        f"- Expected secondary intents found: {pct(s['secondary_found'], s['secondary_total'])}",
        f"- Messages with unexpected secondary intents: {pct(len(extra), n)}"
        f" (of which include `thank_you`: {extra_thanks})",
        "",
        "### By case tag (a message can have several tags)",
        "",
        "| Tag | Messages | Correct/acceptable | Sent to review | Confidently wrong |",
        "|---|---|---|---|---|",
    ]
    for tag, (tag_counts, total) in s["per_tag"].items():
        ok = tag_counts[CORRECT] + tag_counts[ACCEPTABLE]
        lines.append(
            f"| `{tag}` | {total} | {ok} | {tag_counts[SENT_TO_REVIEW]} "
            f"| {tag_counts[CONFIDENT_WRONG]} |"
        )

    lines += [
        "",
        "### Messages not exactly correct",
        "",
        "| Id | Outcome | Expected | Got | Flags | Message |",
        "|---|---|---|---|---|---|",
    ]
    for c, r, o in zip(cases, results, s["outcomes"]):
        if o != CORRECT:
            text = _short(c.message)
            lines.append(
                f"| {c.message.id} | {o} | `{c.expected_primary}` | `{r.primary_intent}` "
                f"| {', '.join(r.flags) or '-'} | {text} |"
            )

    lines += [
        "",
        "### Unexpected secondary intents",
        "",
        "| Id | Unexpected | Message |",
        "|---|---|---|",
    ]
    for c, r, x in extra:
        text = _short(c.message)
        lines.append(f"| {c.message.id} | {', '.join(x)} | {text} |")
    lines.append("")
    return "\n".join(lines)


def main(paths):
    if not paths:
        print("Usage: python -m inbox_helper.evaluate FILE.csv [FILE.csv ...]")
        return 2
    for path in paths:
        cases = load_labelled(path)
        results = [classify(case.message) for case in cases]
        print(format_report(path, cases, results))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
