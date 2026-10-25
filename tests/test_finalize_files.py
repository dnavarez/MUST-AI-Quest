"""Tests for writing approved_unsent.md and approved_unsent.csv (Stage 4b-3).

All messages are synthetic. Review folders are written by the real draft
pipeline (generate_review) and then edited the way a reviewer might. SECRET
is planted in the sender, subject, body, edited reply and note, and must
never appear in an error or the summary.

Fakes for os functions fail only for named paths, so cleanup of other files
is never disturbed by accident. os is one module, so patching os.replace
here also patches finalize_files.os.replace.
"""

import csv
import os
import stat
import sys
import tempfile

import pytest

from inbox_helper import finalize
from inbox_helper.final_output import Provenance, render_final_csv, render_final_markdown
from inbox_helper.finalize import InputBindingError, ReviewFileError, validate_bound_review
from inbox_helper import finalize_files
from inbox_helper.final_output import APPROVED_UNSENT
from inbox_helper.finalize_files import (
    FINAL_CSV,
    FINAL_MD,
    FINAL_STEM,
    FinalOutputConflictError,
    FinalOutputExistsError,
    FinalPartialOutputError,
    finalize_review,
)
from inbox_helper.loader import MessageFileError
from inbox_helper.manifest import MANIFEST_NAME
from inbox_helper.review import CSV_COLUMNS, REVIEW_CSV, REVIEW_MD, generate_review

SECRET = "Zq7Hidden"
MESSAGES = [
    ("A1", f"Sam {SECRET} <sam@example.com>", f"Password {SECRET}",
     f"How do I reset my password? {SECRET}"),
    ("B2", "Kim <kim@example.com>", "Meeting", "Can we schedule a meeting next week?"),
    ("C3", "Lee <lee@example.com>", "Login", "I can't log into my account."),
    ("D4", "Max <max@example.com>", "Question", "How do I change my email address?"),
    ("E5", "Ola <ola@example.com>", "", ""),
]
DECISIONS = {"A1": "approve", "B2": "edit", "C3": "reject"}  # D4 and E5 stay pending
EDITS = {"B2": f"Hello,\n\nYes, we can meet [DATE]. {SECRET}\n\nBest regards"}
NOTES = {"A1": f"checked {SECRET}"}
WINDOWS = sys.platform == "win32"


def write_input(path, rows=MESSAGES):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "sender", "subject", "body"])
        writer.writerows(rows)
    return path


def decide(review_csv):
    with review_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["decision"] = DECISIONS.get(row["id"], "")
        row["edited_draft"] = EDITS.get(row["id"], "")
        row["reviewer_note"] = NOTES.get(row["id"], "")
    with review_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def make_review(tmp_path, input_name="input.csv", review_dir="review"):
    source = write_input(tmp_path / input_name)
    generate_review(source, tmp_path / review_dir)
    review_csv = tmp_path / review_dir / REVIEW_CSV
    decide(review_csv)
    return source, review_csv


@pytest.fixture
def folder(tmp_path):
    """(input, review.csv, out_dir); out_dir does not exist yet."""
    source, review_csv = make_review(tmp_path)
    return source, review_csv, tmp_path / "final"


def expected_bytes(source, review_csv, allow_unbound=False):
    bound = validate_bound_review(source, review_csv, allow_unbound=allow_unbound)
    provenance = Provenance(source.name, bound.input_sha256, review_csv.name, bound.review_sha256)
    return (
        render_final_markdown(bound.reviewed, provenance).encode("utf-8"),
        render_final_csv(bound.reviewed).encode("utf-8-sig"),
    )


def snapshot(path):
    """{name: bytes or link target} of a folder, or None if it does not exist."""
    if not os.path.lexists(path):
        return None
    result = {}
    for name in sorted(os.listdir(path)):
        full = path / name
        if full.is_symlink():
            result[name] = ("link", os.readlink(full))
        elif full.is_dir():
            result[name] = ("dir", snapshot(full))
        elif not full.is_file():  # a FIFO: never read it, it would block
            result[name] = ("special",)
        else:
            result[name] = full.read_bytes()
    return result


def temps_in(path):
    return [n for n in os.listdir(path) if n.startswith(".approved_unsent")]


def old_outputs(out_dir, names=(FINAL_MD, FINAL_CSV)):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (out_dir / name).write_bytes(f"old {name}".encode())


def assert_private(exc):
    texts = [str(exc), repr(exc), "\n".join(getattr(exc, "__notes__", ()))]
    for text in texts:
        assert SECRET not in text


def _symlink(target, link, target_is_directory=False):
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create symbolic links here: {exc}")


def fail_for(real, names, error=None):
    """A fake of os.replace/os.remove that fails when the target's name is in `names`."""
    error = error or OSError("disk full")

    def fake(*args):
        target = os.fspath(args[-1])
        if os.path.basename(target) in names:
            raise error
        return real(*args)

    return fake


# --- Success -----------------------------------------------------------------


def test_bound_review_writes_both_files_and_a_private_summary(folder):
    source, review_csv, out_dir = folder
    md_bytes, csv_bytes = expected_bytes(source, review_csv)

    summary = finalize_review(source, review_csv, out_dir)

    assert (out_dir / FINAL_MD).read_bytes() == md_bytes
    assert (out_dir / FINAL_CSV).read_bytes() == csv_bytes
    rows = list(csv.DictReader((out_dir / FINAL_CSV).read_text(encoding="utf-8-sig").splitlines()))
    assert [r["id"] for r in rows] == ["A1", "B2"]
    assert b"NOT SENT" in md_bytes
    assert summary == {
        "messages": 5,
        "approved": 1,
        "edited": 1,
        "rejected": 1,
        "pending": 2,
        "finalized": 2,
        "bound": True,
        "input_sha256": validate_bound_review(source, review_csv).input_sha256,
        "manifest_input_name": "input.csv",
        "approved_unsent_csv": str(out_dir / FINAL_CSV),
        "approved_unsent_md": str(out_dir / FINAL_MD),
    }
    assert SECRET not in repr(summary)
    assert sorted(os.listdir(out_dir)) == [FINAL_CSV, FINAL_MD]


def test_unbound_review_is_written_only_when_allowed(folder):
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()

    with pytest.raises(InputBindingError):
        finalize_review(source, review_csv, out_dir)
    assert not out_dir.exists()

    summary = finalize_review(source, review_csv, out_dir, allow_unbound=True)

    assert "Input binding was not checked" in (out_dir / FINAL_MD).read_text(encoding="utf-8")
    assert (out_dir / FINAL_MD).read_bytes() == expected_bytes(source, review_csv, True)[0]
    assert summary["bound"] is False
    assert summary["input_sha256"] is None and summary["manifest_input_name"] is None


def test_output_is_byte_identical_across_runs(folder, tmp_path):
    source, review_csv, out_dir = folder
    finalize_review(source, review_csv, out_dir)
    finalize_review(source, review_csv, tmp_path / "again")
    assert snapshot(out_dir) == snapshot(tmp_path / "again")


@pytest.mark.skipif(WINDOWS, reason="POSIX file modes")
def test_files_are_readable_only_by_their_owner(folder, tmp_path):
    source, review_csv, out_dir = folder
    out_dir.mkdir()
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("keep me", encoding="utf-8")
    _symlink(elsewhere, out_dir / FINAL_MD)

    finalize_review(source, review_csv, out_dir, overwrite=True)

    for name in (FINAL_MD, FINAL_CSV):
        assert stat.S_IMODE(os.lstat(out_dir / name).st_mode) == 0o600
    assert elsewhere.read_text(encoding="utf-8") == "keep me"


def test_files_can_be_written_into_the_review_folder(folder):
    source, review_csv, _ = folder
    review_dir = review_csv.parent
    before = snapshot(review_dir)

    finalize_review(source, review_csv, review_dir)

    after = snapshot(review_dir)
    for name in (REVIEW_CSV, REVIEW_MD, MANIFEST_NAME):
        assert after[name] == before[name]
    assert sorted(after) == sorted([*before, FINAL_CSV, FINAL_MD])


def test_missing_nested_folder_is_created(folder):
    source, review_csv, out_dir = folder
    finalize_review(source, review_csv, out_dir / "a" / "b")
    assert (out_dir / "a" / "b" / FINAL_CSV).exists()


# --- Refusals ----------------------------------------------------------------


@pytest.mark.parametrize("overwrite", [False, True])
def test_malformed_review_is_refused_and_nothing_changes(folder, overwrite):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    before = snapshot(out_dir)
    review_csv.write_text("not,a,review\n", encoding="utf-8")

    with pytest.raises(ReviewFileError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=overwrite)

    assert type(caught.value) is ReviewFileError
    assert snapshot(out_dir) == before


def test_validation_comes_before_output_checks(folder):
    source, review_csv, out_dir = folder
    old_outputs(out_dir, [FINAL_MD])
    (out_dir / FINAL_CSV).mkdir()
    before = snapshot(out_dir)
    review_csv.write_text("not,a,review\n", encoding="utf-8")

    with pytest.raises(ReviewFileError) as caught:
        finalize_review(source, review_csv, out_dir)

    assert type(caught.value) is ReviewFileError
    assert snapshot(out_dir) == before


@pytest.mark.parametrize("reason", ["missing", "malformed", "mismatch", "changed"])
def test_binding_refusals_leave_old_outputs_even_with_overwrite(folder, monkeypatch, reason):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    before = snapshot(out_dir)
    manifest = review_csv.parent / MANIFEST_NAME
    if reason == "missing":
        manifest.unlink()
    elif reason == "malformed":
        manifest.write_text("{}", encoding="utf-8")
    elif reason == "mismatch":
        source.write_bytes(source.read_bytes().replace(b"password?", b"password!"))
    else:
        real_validate = finalize.validate_review

        def validate_then_change(*args):
            result = real_validate(*args)
            with source.open("ab") as handle:
                handle.write(b"\r\n")
            return result

        monkeypatch.setattr(finalize, "validate_review", validate_then_change)

    with pytest.raises(InputBindingError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert caught.value.reason == reason
    assert snapshot(out_dir) == before


def test_input_file_errors_propagate_and_nothing_is_created(folder):
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()
    source.write_text("id,sender,subject,body\n,a,b,c\n", encoding="utf-8")

    with pytest.raises(MessageFileError):
        finalize_review(source, review_csv, out_dir, allow_unbound=True)
    assert not out_dir.exists()


@pytest.mark.parametrize("existing", [[FINAL_MD], [FINAL_CSV], [FINAL_MD, FINAL_CSV]])
def test_existing_outputs_are_not_replaced_without_overwrite(folder, existing):
    source, review_csv, out_dir = folder
    old_outputs(out_dir, existing)
    before = snapshot(out_dir)

    with pytest.raises(FinalOutputExistsError) as caught:
        finalize_review(source, review_csv, out_dir)

    # The exact public message; `existing` is listed in target order (MD, CSV).
    assert str(caught.value) == (
        f"Finalized file(s) already exist: {', '.join(str(out_dir / n) for n in existing)}. "
        "Use --overwrite to replace them, or choose another folder. Nothing was changed."
    )
    assert snapshot(out_dir) == before
    assert_private(caught.value)


@pytest.mark.parametrize("name", [FINAL_MD, FINAL_CSV])
def test_broken_link_at_a_target_counts_as_existing(folder, tmp_path, name):
    source, review_csv, out_dir = folder
    out_dir.mkdir()
    _symlink(tmp_path / "nowhere", out_dir / name)
    before = snapshot(out_dir)

    with pytest.raises(FinalOutputExistsError):
        finalize_review(source, review_csv, out_dir)
    assert snapshot(out_dir) == before


def _make_fifo(path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("no named pipes on this platform")
    os.mkfifo(path)


@pytest.mark.parametrize("kind", ["folder", "fifo"])
@pytest.mark.parametrize("name", [FINAL_MD, FINAL_CSV])
def test_non_file_target_is_refused_even_with_overwrite(folder, kind, name):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    (out_dir / name).unlink()
    if kind == "folder":
        (out_dir / name).mkdir()
    else:
        _make_fifo(out_dir / name)
    before = snapshot(out_dir)

    with pytest.raises(FinalOutputConflictError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert str(caught.value).endswith("Nothing was changed.")
    assert snapshot(out_dir) == before
    assert_private(caught.value)


def test_non_file_target_takes_precedence_over_existing_output(folder):
    source, review_csv, out_dir = folder
    old_outputs(out_dir, [FINAL_CSV])
    (out_dir / FINAL_MD).mkdir()

    with pytest.raises(FinalOutputConflictError) as caught:
        finalize_review(source, review_csv, out_dir)
    assert_private(caught.value)


def test_out_dir_that_is_a_file_is_refused(folder):
    source, review_csv, out_dir = folder
    out_dir.write_text("a file", encoding="utf-8")

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir)

    # Raised by os.lstat in the initial target checks, not by the writer.
    assert type(caught.value) is NotADirectoryError
    assert out_dir.read_text(encoding="utf-8") == "a file"


def test_out_dir_that_is_a_dangling_link_is_refused(folder, tmp_path):
    source, review_csv, out_dir = folder
    _symlink(tmp_path / "nowhere", out_dir, target_is_directory=True)

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir)

    # Raised by out_dir.mkdir, before the writer changes anything.
    assert type(caught.value) is FileExistsError
    assert os.path.islink(out_dir) and not (tmp_path / "nowhere").exists()


# --- Output-path conflicts (all also with overwrite) ----------------------------


def _review_named_as_output(tmp_path):
    source, review_csv = make_review(tmp_path)
    renamed = review_csv.with_name(FINAL_CSV)
    review_csv.rename(renamed)
    return source, renamed, renamed.parent


def _review_named_as_output_in_other_case(tmp_path):
    source, review_csv = make_review(tmp_path)
    renamed = review_csv.with_name(FINAL_CSV.upper())
    review_csv.rename(renamed)
    if not (renamed.parent / FINAL_CSV).exists():
        pytest.skip("this file system is case-sensitive")
    return source, renamed, renamed.parent


def _input_named_as_output(tmp_path):
    out_dir = tmp_path / "final"
    out_dir.mkdir()
    source, review_csv = make_review(tmp_path, input_name=f"final/{FINAL_MD}")
    return source, review_csv, out_dir


def _csv_linked_to_review(tmp_path):
    source, review_csv = make_review(tmp_path)
    out_dir = tmp_path / "final"
    out_dir.mkdir()
    _symlink(review_csv, out_dir / FINAL_CSV)
    return source, review_csv, out_dir


def _md_linked_to_input(tmp_path):
    source, review_csv = make_review(tmp_path)
    out_dir = tmp_path / "final"
    out_dir.mkdir()
    _symlink(source, out_dir / FINAL_MD)
    return source, review_csv, out_dir


def _md_symlinked_to_manifest(tmp_path):
    source, review_csv = make_review(tmp_path)
    out_dir = tmp_path / "final"
    out_dir.mkdir()
    _symlink(review_csv.parent / MANIFEST_NAME, out_dir / FINAL_MD)
    return source, review_csv, out_dir


def _md_hard_linked_to_manifest(tmp_path):
    source, review_csv = make_review(tmp_path)
    out_dir = tmp_path / "final"
    out_dir.mkdir()
    try:
        os.link(review_csv.parent / MANIFEST_NAME, out_dir / FINAL_MD)
    except OSError as exc:
        pytest.skip(f"this file system cannot create hard links here: {exc}")
    return source, review_csv, out_dir


def _out_dir_linked_to_review_folder(tmp_path):
    source, review_csv, review_dir = _review_named_as_output(tmp_path)
    link = tmp_path / "linked"
    _symlink(review_dir, link, target_is_directory=True)
    return source, review_csv, link


@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize(
    "setup",
    [
        _review_named_as_output,
        _review_named_as_output_in_other_case,
        _input_named_as_output,
        _csv_linked_to_review,
        _md_linked_to_input,
        _md_symlinked_to_manifest,
        _md_hard_linked_to_manifest,
        _out_dir_linked_to_review_folder,
    ],
)
def test_output_that_is_the_input_review_or_manifest_is_refused(tmp_path, setup, overwrite):
    source, review_csv, out_dir = setup(tmp_path)
    watched = [source.parent, review_csv.parent, out_dir]
    before = [snapshot(p) for p in watched]

    with pytest.raises(FinalOutputConflictError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=overwrite)

    assert str(caught.value).endswith("Nothing was changed.")
    assert [snapshot(p) for p in watched] == before
    assert_private(caught.value)


def test_conflicts_are_checked_before_validation(tmp_path):
    source, review_csv, out_dir = _input_named_as_output(tmp_path)
    review_csv.write_text("not,a,review\n", encoding="utf-8")

    with pytest.raises(FinalOutputConflictError):
        finalize_review(source, review_csv, out_dir)


# --- Overwrite ---------------------------------------------------------------


def test_without_overwrite_nothing_is_ever_removed(folder, monkeypatch):
    source, review_csv, out_dir = folder
    removed = []
    real_remove = os.remove

    def recording_remove(path, *args, **kwargs):
        removed.append(os.path.basename(path))
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "remove", recording_remove)

    finalize_review(source, review_csv, out_dir)

    assert FINAL_MD not in removed and FINAL_CSV not in removed


@pytest.mark.parametrize("claimed", ["old", "absent"])
def test_writer_called_directly_never_replaces_without_overwrite(tmp_path, monkeypatch, claimed):
    # The writer refuses on its own, even when called without _check_targets
    # and even if the caller wrongly says the existing files are absent.
    out_dir = tmp_path / "final"
    old_outputs(out_dir)
    before = snapshot(out_dir)
    targets = [out_dir / FINAL_MD, out_dir / FINAL_CSV]
    files = [(targets[0], b"new md"), (targets[1], b"new csv")]
    calls = []
    for name in ("remove", "replace"):
        real = getattr(os, name)
        monkeypatch.setattr(os, name, lambda *a, _real=real, _n=name: calls.append(_n) or _real(*a))

    with pytest.raises(FinalOutputExistsError) as caught:
        finalize_files._write_final_files(
            out_dir, files, {t: claimed for t in targets}, overwrite=False
        )

    assert str(caught.value).endswith("Nothing was changed.")
    assert calls == []
    assert snapshot(out_dir) == before  # both old files byte-identical, no temp files


def test_writer_refuses_when_a_target_cannot_be_checked(tmp_path, monkeypatch):
    # os.lstat fails for the CSV with an error other than "not found", so its
    # state is unknown: refuse, and do not claim that it exists.
    out_dir = tmp_path / "final"
    old_outputs(out_dir, [FINAL_MD])
    before = snapshot(out_dir)
    targets = [out_dir / FINAL_MD, out_dir / FINAL_CSV]
    files = [(targets[0], b"new md"), (targets[1], b"new csv")]
    real_lstat = os.lstat
    calls = []

    def deny_csv(path, *args, **kwargs):
        if os.path.basename(path) == FINAL_CSV:
            raise PermissionError("denied")
        return real_lstat(path, *args, **kwargs)

    def recording(name):
        real = getattr(os, name)

        def record(*args, **kwargs):
            calls.append(name)
            return real(*args, **kwargs)

        return record

    monkeypatch.setattr(os, "remove", recording("remove"))
    monkeypatch.setattr(os, "replace", recording("replace"))
    monkeypatch.setattr(os, "lstat", deny_csv)

    with pytest.raises(FinalOutputExistsError) as caught:
        finalize_files._write_final_files(
            out_dir, files, {targets[0]: "old", targets[1]: "absent"}, overwrite=False
        )

    monkeypatch.setattr(os, "lstat", real_lstat)
    assert str(caught.value) == (
        f"Finalized file(s) already exist: {targets[0]}. "
        f"The state of finalized file(s) could not be checked: {targets[1]}. "
        "Check that these paths can be read, or choose another folder. Nothing was changed."
    )
    assert "--overwrite" not in str(caught.value)  # it cannot help with an unknown state
    assert calls == []
    assert snapshot(out_dir) == before  # old Markdown byte-identical, no temp files


def test_writer_refuses_when_files_said_to_exist_are_absent(tmp_path):
    # A defensive branch: the caller says both outputs exist, but the writer
    # sees them absent. It refuses rather than trusting either view.
    out_dir = tmp_path / "final"
    out_dir.mkdir()
    targets = [out_dir / FINAL_MD, out_dir / FINAL_CSV]
    files = [(targets[0], b"new md"), (targets[1], b"new csv")]

    with pytest.raises(FinalOutputExistsError) as caught:
        finalize_files._write_final_files(
            out_dir, files, {t: "old" for t in targets}, overwrite=False
        )

    assert str(caught.value) == (
        f"Finalized file(s) expected to exist were found absent: {targets[0]}, {targets[1]}. "
        "Run again, or choose another folder. Nothing was changed."
    )
    assert os.listdir(out_dir) == []  # no output and no temporary file


def test_output_appearing_after_the_first_check_is_not_replaced(folder, monkeypatch):
    # Deterministic stand-in for another program: the CSV appears right after
    # _check_targets found both outputs absent. Without --overwrite, any old
    # output would already have been refused there, so the Markdown is absent.
    source, review_csv, out_dir = folder
    real_check = finalize_files._check_targets

    def check_then_plant(targets, overwrite):
        previous = real_check(targets, overwrite)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / FINAL_CSV).write_bytes(b"someone else's file")
        return previous

    monkeypatch.setattr(finalize_files, "_check_targets", check_then_plant)

    with pytest.raises(FinalOutputExistsError) as caught:
        finalize_review(source, review_csv, out_dir)

    assert str(caught.value) == (
        f"Finalized file(s) already exist: {out_dir / FINAL_CSV}. "
        "Use --overwrite to replace them, or choose another folder. Nothing was changed."
    )
    assert snapshot(out_dir) == {FINAL_CSV: b"someone else's file"}  # no MD, no temps
    assert_private(caught.value)


def test_writer_removes_old_files_csv_first_with_overwrite(tmp_path, monkeypatch):
    out_dir = tmp_path / "final"
    old_outputs(out_dir)
    targets = [out_dir / FINAL_MD, out_dir / FINAL_CSV]
    removed = []
    real_remove = os.remove

    def recording_remove(path, *args, **kwargs):
        removed.append(os.path.basename(path))
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "remove", recording_remove)
    files = [(targets[0], b"new md"), (targets[1], b"new csv")]

    finalize_files._write_final_files(out_dir, files, {t: "old" for t in targets}, overwrite=True)

    assert removed == [FINAL_CSV, FINAL_MD]  # D3: the CSV first
    assert (out_dir / FINAL_MD).read_bytes() == b"new md"
    assert (out_dir / FINAL_CSV).read_bytes() == b"new csv"


@pytest.mark.parametrize("existing", [[FINAL_MD, FINAL_CSV], [FINAL_CSV], [FINAL_MD]])
def test_overwrite_replaces_old_outputs(folder, existing):
    source, review_csv, out_dir = folder
    old_outputs(out_dir, existing)
    md_bytes, csv_bytes = expected_bytes(source, review_csv)

    finalize_review(source, review_csv, out_dir, overwrite=True)

    assert (out_dir / FINAL_MD).read_bytes() == md_bytes
    assert (out_dir / FINAL_CSV).read_bytes() == csv_bytes
    assert temps_in(out_dir) == []


def test_overwrite_replaces_a_linked_target_not_the_file_it_points_to(folder, tmp_path):
    source, review_csv, out_dir = folder
    out_dir.mkdir()
    elsewhere = tmp_path / "elsewhere.csv"
    elsewhere.write_text("keep me", encoding="utf-8")
    _symlink(elsewhere, out_dir / FINAL_CSV)

    finalize_review(source, review_csv, out_dir, overwrite=True)

    assert not (out_dir / FINAL_CSV).is_symlink()
    assert elsewhere.read_text(encoding="utf-8") == "keep me"


def test_link_to_a_folder_at_a_target(folder, tmp_path):
    source, review_csv, out_dir = folder
    out_dir.mkdir()
    a_folder = tmp_path / "a_folder"
    a_folder.mkdir()
    (a_folder / "keep.txt").write_text("keep me", encoding="utf-8")
    _symlink(a_folder, out_dir / FINAL_MD, target_is_directory=True)

    with pytest.raises(FinalOutputExistsError):
        finalize_review(source, review_csv, out_dir)

    finalize_review(source, review_csv, out_dir, overwrite=True)

    assert not (out_dir / FINAL_MD).is_symlink() and (out_dir / FINAL_MD).is_file()
    assert snapshot(a_folder) == {"keep.txt": b"keep me"}


# --- Write failures ----------------------------------------------------------


def _message(out_dir, *sentences):
    return " ".join([
        f"The finalized files in {out_dir} were left incomplete after an error (disk full).",
        *sentences,
        "Do not use these files. Run again with --overwrite, or choose another folder.",
    ])


def test_failure_creating_the_second_temp_file(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    before = snapshot(out_dir)
    error = OSError("disk full")
    real_mkstemp = tempfile.mkstemp

    def fake_mkstemp(*args, **kwargs):
        if kwargs.get("prefix", "").startswith(f".{FINAL_CSV}."):
            raise error
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", fake_mkstemp)

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert caught.value is error
    assert snapshot(out_dir) == before


def test_failure_writing_the_second_temp_file(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    before = snapshot(out_dir)
    error = OSError("disk full")
    real_fdopen = os.fdopen
    calls = []

    class FailingWrite:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            self.handle.close()

        def write(self, data):
            raise error

    def fake_fdopen(fd, mode="r", *args, **kwargs):
        handle = real_fdopen(fd, mode, *args, **kwargs)
        if mode != "wb":  # the manifest reader opens with "rb"
            return handle
        calls.append(fd)
        return FailingWrite(handle) if len(calls) == 2 else handle

    monkeypatch.setattr(os, "fdopen", fake_fdopen)

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert caught.value is error and len(calls) == 2
    assert snapshot(out_dir) == before


def test_fdopen_failure_closes_the_descriptor(folder, monkeypatch):
    source, review_csv, out_dir = folder
    error = OSError("disk full")
    closed = []
    real_close, real_fdopen = os.close, os.fdopen

    def fake_fdopen(fd, mode="r", *args, **kwargs):
        if mode == "wb":  # the manifest reader opens with "rb"
            raise error
        return real_fdopen(fd, mode, *args, **kwargs)

    def recording_close(fd):
        closed.append(fd)
        return real_close(fd)

    monkeypatch.setattr(os, "fdopen", fake_fdopen)
    monkeypatch.setattr(os, "close", recording_close)

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir)

    assert caught.value is error and len(closed) == 1
    assert temps_in(out_dir) == []


def test_failure_removing_the_old_csv(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    before = snapshot(out_dir)
    error = OSError("disk full")
    monkeypatch.setattr(os, "remove", fail_for(os.remove, {FINAL_CSV}, error))

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert caught.value is error
    assert snapshot(out_dir) == before


def test_failure_removing_the_only_old_file_the_markdown(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir, [FINAL_MD])
    before = snapshot(out_dir)
    error = OSError("disk full")
    monkeypatch.setattr(os, "remove", fail_for(os.remove, {FINAL_MD}, error))

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert caught.value is error
    assert snapshot(out_dir) == before


def test_removal_that_fails_after_removing_is_not_reported_as_unchanged(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    real_remove = os.remove
    error = OSError("disk full")

    def remove_then_fail(path, *args, **kwargs):
        real_remove(path, *args, **kwargs)
        if os.path.basename(path) == FINAL_CSV:
            raise error

    monkeypatch.setattr(os, "remove", remove_then_fail)

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert str(caught.value) == _message(
        out_dir,
        f"Still from a previous run: {FINAL_MD}.",
        f"State could not be confirmed: {FINAL_CSV}.",
    )
    assert caught.value.__cause__ is error
    assert_private(caught.value)


def test_failure_removing_the_old_markdown_after_the_csv(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    error = OSError("disk full")
    monkeypatch.setattr(os, "remove", fail_for(os.remove, {FINAL_MD}, error))

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert str(caught.value) == _message(
        out_dir,
        f"Removed from a previous run, no new version: {FINAL_CSV}.",
        f"Still from a previous run: {FINAL_MD}.",
    )
    assert caught.value.__cause__ is error
    assert sorted(os.listdir(out_dir)) == [FINAL_MD]
    assert (out_dir / FINAL_MD).read_bytes() == f"old {FINAL_MD}".encode()
    assert_private(caught.value)


def test_failure_placing_the_markdown_after_both_were_removed(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    error = OSError("disk full")
    monkeypatch.setattr(os, "replace", fail_for(os.replace, {FINAL_MD}, error))

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    message = str(caught.value)
    assert message.startswith(
        f"The finalized files in {out_dir} were left incomplete after an error ("
    )
    assert message == _message(
        out_dir, f"Removed from a previous run, no new version: {FINAL_MD}, {FINAL_CSV}."
    )
    assert caught.value.__cause__ is error
    assert os.listdir(out_dir) == []
    assert_private(caught.value)


def test_failure_placing_the_markdown_with_nothing_before(folder, monkeypatch):
    source, review_csv, out_dir = folder
    error = OSError("disk full")
    monkeypatch.setattr(os, "replace", fail_for(os.replace, {FINAL_MD}, error))

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir)

    assert caught.value is error
    assert os.listdir(out_dir) == []  # the folder may be created, but stays empty


@pytest.mark.parametrize("previous", [[FINAL_MD, FINAL_CSV], []])
def test_failure_placing_the_csv_after_the_markdown(folder, monkeypatch, previous):
    source, review_csv, out_dir = folder
    old_outputs(out_dir, previous)
    md_bytes, _ = expected_bytes(source, review_csv)
    error = OSError("disk full")
    monkeypatch.setattr(os, "replace", fail_for(os.replace, {FINAL_CSV}, error))

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=bool(previous))

    csv_sentence = (
        f"Removed from a previous run, no new version: {FINAL_CSV}." if previous
        else f"Not written: {FINAL_CSV}."
    )
    assert str(caught.value) == _message(
        out_dir, f"New version written: {FINAL_MD}.", csv_sentence
    )
    assert caught.value.__cause__ is error
    assert (out_dir / FINAL_MD).read_bytes() == md_bytes
    assert sorted(os.listdir(out_dir)) == [FINAL_MD]
    assert_private(caught.value)


def test_cleanup_failure_is_reported_in_the_partial_error(folder, monkeypatch):
    source, review_csv, out_dir = folder
    md_bytes, _ = expected_bytes(source, review_csv)
    error = OSError("disk full")
    monkeypatch.setattr(os, "replace", fail_for(os.replace, {FINAL_CSV}, error))
    real_remove = os.remove
    left = []

    def fail_for_csv_temp(path, *args, **kwargs):
        if os.path.basename(path).startswith(f".{FINAL_CSV}."):
            left.append(os.fspath(path))
            raise OSError("busy")
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "remove", fail_for_csv_temp)

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir)

    assert str(caught.value) == _message(
        out_dir,
        f"New version written: {FINAL_MD}.",
        f"Not written: {FINAL_CSV}.",
        f"Temporary files could not be removed: {left[0]}.",
    )
    assert caught.value.__cause__ is error
    assert (out_dir / FINAL_MD).read_bytes() == md_bytes
    assert_private(caught.value)


def test_cleanup_failure_before_any_change_keeps_the_original_error(folder, monkeypatch):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    error = OSError("disk full")
    real_mkstemp = tempfile.mkstemp

    def fake_mkstemp(*args, **kwargs):
        if kwargs.get("prefix", "").startswith(f".{FINAL_CSV}."):
            raise error
        return real_mkstemp(*args, **kwargs)

    real_remove = os.remove
    left = []

    def fail_for_md_temp(path, *args, **kwargs):
        if os.path.basename(path).startswith(f".{FINAL_MD}."):
            left.append(os.fspath(path))
            raise OSError("busy")
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", fake_mkstemp)
    monkeypatch.setattr(os, "remove", fail_for_md_temp)

    with pytest.raises(OSError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert caught.value is error
    assert caught.value.__notes__ == [f"Temporary files could not be removed: {left[0]}"]
    assert_private(caught.value)


def _lstat_after_failure(monkeypatch, failing_name, fake_result):
    """os.replace fails for `failing_name`; only then does os.lstat start lying.

    fake_result(path) returns None to use the real os.lstat, or raises or
    returns a fake result. Switching on late keeps step 2 (Path.resolve) and
    step 6 working normally.
    """
    real_replace, real_lstat = os.replace, os.lstat
    active = []
    error = OSError("disk full")

    def failing_replace(src, dst, *args, **kwargs):
        if os.path.basename(dst) == failing_name:
            active.append(True)
            raise error
        return real_replace(src, dst, *args, **kwargs)

    def lying_lstat(path, *args, **kwargs):
        if active:
            result = fake_result(os.fspath(path))
            if result is not None:
                return result
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", failing_replace)
    monkeypatch.setattr(os, "lstat", lying_lstat)
    return error


def test_target_whose_state_cannot_be_checked(folder, monkeypatch):
    source, review_csv, out_dir = folder

    def deny_csv(path):
        if os.path.basename(path) == FINAL_CSV:
            raise PermissionError("denied")
        return None

    error = _lstat_after_failure(monkeypatch, FINAL_CSV, deny_csv)

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir)

    assert str(caught.value) == _message(
        out_dir,
        f"New version written: {FINAL_MD}.",
        f"State could not be confirmed: {FINAL_CSV}.",
    )
    assert caught.value.__cause__ is error
    assert_private(caught.value)


def test_target_whose_state_contradicts_what_was_done(folder, monkeypatch, tmp_path):
    source, review_csv, out_dir = folder
    old_outputs(out_dir)
    some_file = tmp_path / "some_file"
    some_file.write_text("x", encoding="utf-8")
    real_lstat = os.lstat

    def md_looks_present(path):
        if os.path.basename(path) == FINAL_MD:
            return real_lstat(some_file)
        return None

    error = _lstat_after_failure(monkeypatch, FINAL_MD, md_looks_present)

    with pytest.raises(FinalPartialOutputError) as caught:
        finalize_review(source, review_csv, out_dir, overwrite=True)

    assert str(caught.value) == _message(
        out_dir,
        f"Removed from a previous run, no new version: {FINAL_CSV}.",
        f"State could not be confirmed: {FINAL_MD}.",
    )
    assert caught.value.__cause__ is error
    assert_private(caught.value)


@pytest.mark.parametrize("where", ["placing the csv", "writing a temp file"])
def test_interrupt_propagates_and_temp_files_are_removed(folder, monkeypatch, where):
    source, review_csv, out_dir = folder
    md_bytes, _ = expected_bytes(source, review_csv)
    interrupt = KeyboardInterrupt()
    if where == "placing the csv":
        monkeypatch.setattr(os, "replace", fail_for(os.replace, {FINAL_CSV}, interrupt))
    else:
        real_fdopen = os.fdopen
        calls = []

        def fake_fdopen(fd, mode="r", *args, **kwargs):
            if mode == "wb":  # the manifest reader opens with "rb"
                calls.append(fd)
                if len(calls) == 2:
                    raise interrupt
            return real_fdopen(fd, mode, *args, **kwargs)

        monkeypatch.setattr(os, "fdopen", fake_fdopen)

    with pytest.raises(KeyboardInterrupt) as caught:
        finalize_review(source, review_csv, out_dir)

    assert caught.value is interrupt
    assert temps_in(out_dir) == []
    if where == "writing a temp file":
        assert len(calls) == 2
    if where == "placing the csv":
        assert (out_dir / FINAL_MD).read_bytes() == md_bytes
        assert not (out_dir / FINAL_CSV).exists()
    else:
        assert os.listdir(out_dir) == []


def test_interrupt_reports_temp_files_that_could_not_be_removed(folder, monkeypatch):
    source, review_csv, out_dir = folder
    md_bytes, _ = expected_bytes(source, review_csv)
    interrupt = KeyboardInterrupt()
    monkeypatch.setattr(os, "replace", fail_for(os.replace, {FINAL_CSV}, interrupt))
    real_remove = os.remove
    left = []

    def fail_for_csv_temp(path, *args, **kwargs):
        if os.path.basename(path).startswith(f".{FINAL_CSV}."):
            left.append(os.fspath(path))
            raise OSError("busy")
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "remove", fail_for_csv_temp)

    with pytest.raises(KeyboardInterrupt) as caught:
        finalize_review(source, review_csv, out_dir)

    assert caught.value is interrupt
    assert caught.value.__notes__ == [f"Temporary files could not be removed: {left[0]}"]
    assert os.path.exists(left[0])  # still there, and reported as such
    assert (out_dir / FINAL_MD).read_bytes() == md_bytes
    assert_private(caught.value)


# --- D7 and file names -------------------------------------------------------


def test_markdown_shows_the_current_file_names_after_renaming(folder, tmp_path):
    # D7: the report names the files as they are now. The manifest still
    # records input.csv; the fingerprint, not the name, binds the review.
    source, review_csv, out_dir = folder
    renamed_input = source.rename(tmp_path / "renamed.csv")
    renamed_review = review_csv.rename(review_csv.with_name("my_review.csv"))

    summary = finalize_review(renamed_input, renamed_review, out_dir)

    report = (out_dir / FINAL_MD).read_text(encoding="utf-8")
    assert "- Input file: `renamed.csv`" in report
    assert "- Review file: `my_review.csv`" in report
    assert "input.csv" not in report and "`review.csv`" not in report
    assert summary["manifest_input_name"] == "input.csv"
    assert summary["bound"] is True


def test_output_file_names_are_fixed():
    # Pins the file names. Their independence from the status value is kept by
    # the code: FINAL_STEM is its own constant, not derived from APPROVED_UNSENT.
    assert (FINAL_STEM, FINAL_MD, FINAL_CSV) == (
        "approved_unsent", "approved_unsent.md", "approved_unsent.csv"
    )
    assert APPROVED_UNSENT == "approved_unsent"  # the status value, defined separately
