"""Keep the worked example in examples/ honest.

The example files must be exactly what the current code produces from
data/messages.csv (synthetic demo messages). If rendering changes on
purpose, regenerate them with the commands in examples/README.md.
"""

import csv
import hashlib
import json
from pathlib import Path

from inbox_helper.__main__ import main
from inbox_helper.finalize_files import FINAL_CSV, FINAL_MD
from inbox_helper.manifest import MANIFEST_NAME
from inbox_helper.review import CSV_COLUMNS, REVIEW_CSV, REVIEW_MD

ROOT = Path(__file__).resolve().parent.parent
MESSAGES = ROOT / "data" / "messages.csv"
EXAMPLES = ROOT / "examples"
DRAFT_DIR, REVIEWED_DIR, FINAL_DIR = (EXAMPLES / n for n in ("1_draft", "2_reviewed", "3_final"))
DECISION_COLUMNS = ("decision", "edited_draft", "reviewer_note")


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# macOS Finder metadata (also in .gitignore). Only this name is skipped, so
# any other unexpected file, hidden or not, still fails the listing test.
IGNORED_NAMES = {".DS_Store"}


def example_files():
    """Files under examples/, except macOS .DS_Store metadata."""
    return [p for p in EXAMPLES.rglob("*") if p.is_file() and p.name not in IGNORED_NAMES]


def test_example_folders_hold_exactly_the_expected_files():
    listing = {p.relative_to(EXAMPLES).as_posix() for p in example_files()}
    assert listing == {
        "README.md",
        f"1_draft/{REVIEW_MD}", f"1_draft/{REVIEW_CSV}", f"1_draft/{MANIFEST_NAME}",
        f"2_reviewed/{REVIEW_CSV}", f"2_reviewed/{MANIFEST_NAME}",
        f"3_final/{FINAL_MD}", f"3_final/{FINAL_CSV}",
    }


def test_draft_example_is_what_draft_writes(tmp_path, capsys):
    out_dir = tmp_path / "1_draft"
    assert main(["draft", str(MESSAGES), "--out", str(out_dir)]) == 0
    capsys.readouterr()

    for name in (REVIEW_MD, REVIEW_CSV, MANIFEST_NAME):
        assert (out_dir / name).read_bytes() == (DRAFT_DIR / name).read_bytes(), name


def test_final_example_is_what_finalize_writes(tmp_path, capsys):
    out_dir = tmp_path / "3_final"
    code = main([
        "finalize", str(MESSAGES), "--review", str(REVIEWED_DIR / REVIEW_CSV),
        "--out", str(out_dir),
    ])
    out = capsys.readouterr().out
    assert code == 0 and "Input binding: verified by SHA-256" in out

    for name in (FINAL_MD, FINAL_CSV):
        assert (out_dir / name).read_bytes() == (FINAL_DIR / name).read_bytes(), name


def test_review_only_changes_the_decision_columns():
    drafted, reviewed = read_rows(DRAFT_DIR / REVIEW_CSV), read_rows(REVIEWED_DIR / REVIEW_CSV)
    assert list(reviewed[0]) == list(CSV_COLUMNS)  # same columns, same order
    assert [r["id"] for r in reviewed] == [r["id"] for r in drafted]
    for before, after in zip(drafted, reviewed):
        for column in CSV_COLUMNS:
            if column not in DECISION_COLUMNS:
                assert after[column] == before[column], (after["id"], column)


def test_reviewed_folder_is_bound_to_the_demo_input():
    assert (REVIEWED_DIR / MANIFEST_NAME).read_bytes() == (DRAFT_DIR / MANIFEST_NAME).read_bytes()
    manifest = json.loads((REVIEWED_DIR / MANIFEST_NAME).read_text(encoding="ascii"))
    assert manifest["input_name"] == "messages.csv"
    assert manifest["input_sha256"] == hashlib.sha256(MESSAGES.read_bytes()).hexdigest()


def test_worked_example_decisions_match_the_plan():
    decisions = {r["id"]: r["decision"] for r in read_rows(REVIEWED_DIR / REVIEW_CSV)}
    counts = {d: list(decisions.values()).count(d) for d in ("approve", "edit", "reject", "")}
    assert counts == {"approve": 3, "edit": 2, "reject": 2, "": 5}

    final_ids = [r["id"] for r in read_rows(FINAL_DIR / FINAL_CSV)]
    assert final_ids == [i for i, d in decisions.items() if d in ("approve", "edit")]
    # The rule-override message is rejected, not sent on.
    assert decisions["demo-09"] == "reject"


def test_demo_data_is_synthetic_and_covers_every_intent():
    rows = read_rows(MESSAGES)
    assert len(rows) == 12
    assert all(r["sender"].rstrip(">").endswith("@example.com") for r in rows)
    intents = {r["primary_intent"] for r in read_rows(DRAFT_DIR / REVIEW_CSV)}
    assert intents == {
        "meeting_request", "support_question", "job_application", "complaint",
        "status_update", "thank_you", "other_or_unclear",
    }


def test_demo_12_is_still_the_documented_classifier_mistake():
    # examples/README.md describes demo-12 (a complaint without complaint
    # keywords) as a genuine mistake. If the classifier ever gets it right,
    # that paragraph must be rewritten; this test makes sure it is noticed.
    by_id = {r["id"]: r for r in read_rows(DRAFT_DIR / REVIEW_CSV)}
    assert by_id["demo-12"]["primary_intent"] == "other_or_unclear"


def test_example_files_have_no_machine_paths():
    for path in [MESSAGES, *example_files()]:
        text = path.read_bytes().decode("utf-8-sig")
        assert str(ROOT) not in text and str(Path.home()) not in text, path
