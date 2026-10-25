"""Tests for binding a review to its input file (Stage 4b-2).

All messages are synthetic. Review folders are written by the real draft
pipeline (generate_review) and then edited the way a reviewer might.
"""

import csv
import hashlib
import os
import shutil

import pytest

from inbox_helper import finalize
from inbox_helper.final_output import Provenance, render_final_csv, render_final_markdown
from inbox_helper.finalize import (
    InputBindingError,
    ReviewFileError,
    validate_bound_review,
    validate_review,
)
from inbox_helper.manifest import MANIFEST_NAME
from inbox_helper.review import CSV_COLUMNS, REVIEW_CSV, generate_review

MESSAGES = [
    ("A1", "Sam <sam@example.com>", "Password question", "How do I reset my password?"),
    ("B2", "Kim <kim@example.com>", "Meeting", "Can we schedule a meeting next week?"),
    ("C3", "Lee <lee@example.com>", "Login", "I can't log into my account."),
    ("E4", "Ola <ola@example.com>", "", ""),
]
DECISIONS = {"A1": "approve", "B2": "reject"}  # C3 and E4 stay pending


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_input(path, rows=MESSAGES):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "sender", "subject", "body"])
        writer.writerows(rows)
    return path


def decide(review_csv, decisions=DECISIONS):
    with review_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["decision"] = decisions.get(row["id"], "")
    with review_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def folder(tmp_path):
    """(input path, review.csv path) for a drafted and decided review."""
    source = write_input(tmp_path / "input.csv")
    generate_review(source, tmp_path / "review")
    review_csv = tmp_path / "review" / REVIEW_CSV
    decide(review_csv)
    return source, review_csv


def refused(reason, *args, **kwargs):
    with pytest.raises(InputBindingError) as caught:
        validate_bound_review(*args, **kwargs)
    assert caught.value.reason == reason
    return str(caught.value)


@pytest.fixture
def no_stage_4a(monkeypatch):
    """Fail the test if Stage 4a validation runs."""

    def must_not_run(*args):
        raise AssertionError("validate_review must not run")

    monkeypatch.setattr(finalize, "validate_review", must_not_run)


def _symlink(target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create symbolic links here: {exc}")


# --- Bound reviews -----------------------------------------------------------


def test_bound_review_returns_the_stage_4a_result_and_fingerprints(folder):
    source, review_csv = folder

    result = validate_bound_review(source, review_csv)

    assert result.reviewed == validate_review(source, review_csv)
    assert result.input_sha256 == sha256_of(source)
    assert result.review_sha256 == sha256_of(review_csv)
    assert result.manifest_input_name == "input.csv"
    assert [r.decision for r in result.reviewed] == ["approve", "reject", None, None]


def test_renamed_input_is_accepted_because_the_fingerprint_decides(folder, tmp_path):
    source, review_csv = folder
    renamed = tmp_path / "renamed.csv"
    shutil.copyfile(source, renamed)

    result = validate_bound_review(renamed, review_csv)

    assert result.input_sha256 == sha256_of(renamed)
    assert result.manifest_input_name == "input.csv"


def test_bound_review_still_runs_stage_4a(folder):
    source, review_csv = folder
    decide(review_csv, {"A1": "maybe"})

    with pytest.raises(ReviewFileError) as caught:
        validate_bound_review(source, review_csv)
    assert type(caught.value) is ReviewFileError


# --- Mismatch ----------------------------------------------------------------


@pytest.mark.parametrize("allow_unbound", [False, True])
def test_changed_input_is_refused_before_stage_4a(folder, no_stage_4a, allow_unbound):
    source, review_csv = folder
    source.write_bytes(source.read_bytes().replace(b"password?", b"password!"))

    message = refused("mismatch", source, review_csv, allow_unbound=allow_unbound)

    assert sha256_of(source) in message
    assert "not the file this review was made from" in message


def test_review_from_another_input_is_refused(tmp_path):
    first = write_input(tmp_path / "first.csv")
    second = write_input(tmp_path / "second.csv", MESSAGES[:2])
    generate_review(first, tmp_path / "a")
    generate_review(second, tmp_path / "b")
    # A mixed folder: the second review.csv next to the first manifest.
    shutil.copyfile(tmp_path / "b" / REVIEW_CSV, tmp_path / "a" / REVIEW_CSV)

    refused("mismatch", second, tmp_path / "a" / REVIEW_CSV)


# --- Missing manifest --------------------------------------------------------


def test_missing_manifest_is_refused_before_stage_4a(folder, no_stage_4a):
    source, review_csv = folder
    (review_csv.parent / MANIFEST_NAME).unlink()

    message = refused("missing", source, review_csv)

    assert MANIFEST_NAME in message and "unbound" in message


def test_missing_manifest_allowed_runs_stage_4a_and_is_marked_unbound(folder):
    source, review_csv = folder
    (review_csv.parent / MANIFEST_NAME).unlink()

    result = validate_bound_review(source, review_csv, allow_unbound=True)

    assert result.input_sha256 is None and result.manifest_input_name is None
    assert result.review_sha256 == sha256_of(review_csv)
    assert result.reviewed == validate_review(source, review_csv)


def test_allowing_unbound_never_skips_stage_4a(folder):
    source, review_csv = folder
    (review_csv.parent / MANIFEST_NAME).unlink()
    decide(review_csv, {"A1": "maybe"})

    with pytest.raises(ReviewFileError) as caught:
        validate_bound_review(source, review_csv, allow_unbound=True)
    assert type(caught.value) is ReviewFileError


def test_allowing_unbound_still_refuses_a_review_of_other_messages(tmp_path):
    first = write_input(tmp_path / "first.csv")
    second = write_input(tmp_path / "second.csv", MESSAGES[:2])
    generate_review(first, tmp_path / "a")
    (tmp_path / "a" / MANIFEST_NAME).unlink()

    with pytest.raises(ReviewFileError):
        validate_bound_review(second, tmp_path / "a" / REVIEW_CSV, allow_unbound=True)


def test_missing_review_file_is_reported_before_the_manifest(tmp_path, no_stage_4a):
    source = write_input(tmp_path / "input.csv")

    with pytest.raises(ReviewFileError, match="review file not found"):
        validate_bound_review(source, tmp_path / "nowhere" / REVIEW_CSV)


# --- Malformed manifest ------------------------------------------------------


@pytest.mark.parametrize("allow_unbound", [False, True])
@pytest.mark.parametrize("content", [b"", b"{}", b"not json", b'{"format": 1}'])
def test_malformed_manifest_is_always_refused(folder, no_stage_4a, allow_unbound, content):
    source, review_csv = folder
    (review_csv.parent / MANIFEST_NAME).write_bytes(content)

    message = refused("malformed", source, review_csv, allow_unbound=allow_unbound)

    assert "Run the draft command again" in message


@pytest.mark.parametrize("allow_unbound", [False, True])
def test_symbolic_link_manifest_is_refused(folder, tmp_path, no_stage_4a, allow_unbound):
    source, review_csv = folder
    manifest = review_csv.parent / MANIFEST_NAME
    real = tmp_path / "real.json"
    manifest.rename(real)
    _symlink(real, manifest)

    message = refused("malformed", source, review_csv, allow_unbound=allow_unbound)

    assert "symbolic link" in message


# --- Changes during the check ------------------------------------------------


@pytest.mark.parametrize("which", ["input", "review"])
def test_file_changed_during_the_check_is_refused(folder, monkeypatch, which):
    source, review_csv = folder
    target = source if which == "input" else review_csv
    real_validate = finalize.validate_review

    def validate_then_change(*args):
        result = real_validate(*args)
        with target.open("ab") as handle:
            handle.write(b"\r\n")
        return result

    monkeypatch.setattr(finalize, "validate_review", validate_then_change)

    message = refused("changed", source, review_csv)

    assert f"the {which} file" in message and "changed while it was being checked" in message


# --- Same-file conflicts and paths -------------------------------------------


def test_input_that_is_the_review_file_is_refused(folder):
    _, review_csv = folder
    with pytest.raises(ReviewFileError, match="are the same file"):
        validate_bound_review(review_csv, review_csv)


def test_review_file_that_is_the_manifest_is_refused(folder):
    source, review_csv = folder
    refused("conflict", source, review_csv.parent / MANIFEST_NAME)


def test_input_that_is_the_manifest_is_refused(folder):
    _, review_csv = folder
    refused("conflict", review_csv.parent / MANIFEST_NAME, review_csv)


def test_input_linked_to_the_manifest_is_refused(folder, tmp_path):
    _, review_csv = folder
    link = tmp_path / "looks_like_messages.csv"
    _symlink(review_csv.parent / MANIFEST_NAME, link)
    refused("conflict", link, review_csv, allow_unbound=True)


def test_input_reached_through_dot_dot_as_the_manifest_is_refused(folder):
    _, review_csv = folder
    roundabout = review_csv.parent / ".." / review_csv.parent.name / MANIFEST_NAME
    refused("conflict", roundabout, review_csv)


def test_linked_review_file_uses_the_manifest_next_to_the_real_file(folder, tmp_path):
    source, review_csv = folder
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # A manifest beside the link must not be used.
    (elsewhere / MANIFEST_NAME).write_text("not a manifest", encoding="utf-8")
    _symlink(review_csv, elsewhere / "my_review.csv")

    result = validate_bound_review(source, elsewhere / "my_review.csv")

    assert result.input_sha256 == sha256_of(source)


def test_review_file_renamed_in_the_same_folder_stays_bound(folder):
    source, review_csv = folder
    renamed = review_csv.with_name("review-done.csv")
    review_csv.rename(renamed)

    assert validate_bound_review(source, renamed).input_sha256 == sha256_of(source)


# --- End to end with the Stage 4b-1 renderers --------------------------------


def _provenance(source, review_csv, result):
    return Provenance(source.name, result.input_sha256, review_csv.name, result.review_sha256)


def test_bound_review_renders_only_approved_replies(folder):
    source, review_csv = folder

    result = validate_bound_review(source, review_csv)
    rows = list(csv.DictReader(render_final_csv(result.reviewed).splitlines()))
    report = render_final_markdown(result.reviewed, _provenance(source, review_csv, result))

    assert [row["id"] for row in rows] == ["A1"]
    assert f"Input SHA-256: `{sha256_of(source)}`" in report
    assert "binding was not checked" not in report


def test_unbound_review_says_binding_was_not_checked(folder):
    source, review_csv = folder
    (review_csv.parent / MANIFEST_NAME).unlink()

    result = validate_bound_review(source, review_csv, allow_unbound=True)
    rows = list(csv.DictReader(render_final_csv(result.reviewed).splitlines()))
    report = render_final_markdown(result.reviewed, _provenance(source, review_csv, result))

    assert [row["id"] for row in rows] == ["A1"]
    assert "Input binding was not checked" in report
