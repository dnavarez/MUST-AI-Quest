"""End-to-end tests for: python -m inbox_helper finalize INPUT --review CSV --out DIR

All messages are synthetic. Review folders are written by the real draft
pipeline and then edited the way a reviewer might. SECRET is planted in the
sender, subject, body, edited reply and note; it must never be printed.
"""

import csv
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from inbox_helper import __main__ as cli
from inbox_helper.__main__ import main
from inbox_helper.finalize_files import FINAL_CSV, FINAL_MD
from inbox_helper.manifest import MANIFEST_NAME
from inbox_helper.review import CSV_COLUMNS, REVIEW_CSV, generate_review

SRC = Path(__file__).resolve().parent.parent / "src"
SECRET = "Zq7Hidden"
MESSAGES = [
    ("A1", f"Sam {SECRET} <sam@example.com>", f"Password {SECRET}",
     f"How do I reset my password? {SECRET}"),
    ("B2", "Kim <kim@example.com>", "Meeting", "Can we schedule a meeting next week?"),
    ("C3", "Lee <lee@example.com>", "Login", "I can't log into my account."),
    ("D4", "Ola <ola@example.com>", "", ""),
]
DECISIONS = {"A1": "approve", "B2": "edit", "C3": "reject"}  # D4 stays pending
EDITS = {"B2": f"Hello,\n\nYes, we can meet [DATE]. {SECRET}\n\nBest regards"}
NOTES = {"A1": f"checked {SECRET}"}


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
        row["edited_draft"] = EDITS.get(row["id"], "") if decisions.get(row["id"]) else ""
        row["reviewer_note"] = NOTES.get(row["id"], "")
    with review_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def folder(tmp_path):
    """(input, review.csv, out_dir); out_dir does not exist yet."""
    source = write_input(tmp_path / "input.csv")
    generate_review(source, tmp_path / "review")
    review_csv = tmp_path / "review" / REVIEW_CSV
    decide(review_csv)
    return source, review_csv, tmp_path / "final"


def run(capsys, source, review_csv, out_dir, *flags):
    code = main(["finalize", str(source), "--review", str(review_csv), "--out", str(out_dir),
                 *flags])
    out, err = capsys.readouterr()
    assert SECRET not in out and SECRET not in err  # never print message or reply text
    return code, out, err


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _symlink(target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create symbolic links here: {exc}")


# --- Success -----------------------------------------------------------------


def test_finalize_writes_both_files_and_reports_counts_only(folder, capsys):
    source, review_csv, out_dir = folder

    code, out, err = run(capsys, source, review_csv, out_dir)

    assert code == 0 and err == ""
    assert out.splitlines() == [
        "Finalized 4 message(s): 1 approved, 1 edited, 1 rejected, 1 pending.",
        f"Input binding: verified by SHA-256 {sha256_of(source)}.",
        f"Wrote {out_dir / FINAL_MD}",
        f"Wrote {out_dir / FINAL_CSV}",
        "Nothing was sent. Every reply is approved_unsent; send it yourself from your "
        "own email tool.",
    ]
    with (out_dir / FINAL_CSV).open(encoding="utf-8-sig", newline="") as handle:
        assert [row["id"] for row in csv.DictReader(handle)] == ["A1", "B2"]
    assert "NOT SENT" in (out_dir / FINAL_MD).read_text(encoding="utf-8")


def test_python_dash_m_finalize_works(folder):
    source, review_csv, out_dir = folder
    env = dict(os.environ, PYTHONPATH=str(SRC))

    result = subprocess.run(
        [sys.executable, "-m", "inbox_helper", "finalize", str(source),
         "--review", str(review_csv), "--out", str(out_dir)],
        capture_output=True, text=True, env=env, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (out_dir / FINAL_MD).exists() and (out_dir / FINAL_CSV).exists()
    assert SECRET not in result.stdout + result.stderr


def test_help_mentions_allow_unbound(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["finalize", "--help"])
    assert caught.value.code == 0
    assert "--allow-unbound" in capsys.readouterr().out


def test_overwrite_replaces_existing_outputs(folder, capsys):
    source, review_csv, out_dir = folder
    out_dir.mkdir()
    (out_dir / FINAL_MD).write_text("old", encoding="utf-8")

    code, _, err = run(capsys, source, review_csv, out_dir)
    assert code == 2 and "already exist" in err and "--overwrite" in err
    assert (out_dir / FINAL_MD).read_text(encoding="utf-8") == "old"

    code, _, err = run(capsys, source, review_csv, out_dir, "--overwrite")
    assert code == 0 and err == ""
    assert (out_dir / FINAL_MD).read_text(encoding="utf-8").startswith("# Inbox Helper")


# --- Binding and --allow-unbound -------------------------------------------------


def test_missing_manifest_is_refused_and_names_the_flag(folder, capsys):
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()

    code, out, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and out == ""
    assert "there is no review manifest" in err and "--allow-unbound" in err
    assert not out_dir.exists()


def test_allow_unbound_accepts_a_missing_manifest_and_says_so(folder, capsys):
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()

    code, out, err = run(capsys, source, review_csv, out_dir, "--allow-unbound")

    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[1] == (
        "Warning: input binding was NOT checked (--allow-unbound): there is no review "
        "manifest, so the review was only checked against the input's messages."
    )
    assert "Input binding was not checked" in (out_dir / FINAL_MD).read_text(encoding="utf-8")


@pytest.mark.parametrize("problem", ["malformed", "mismatch"])
def test_allow_unbound_never_overrides_a_bad_manifest(folder, capsys, problem):
    source, review_csv, out_dir = folder
    if problem == "malformed":
        (review_csv.parent / MANIFEST_NAME).write_text("{}", encoding="utf-8")
        expected = "cannot be used"
    else:
        source.write_bytes(source.read_bytes().replace(b"password?", b"password!"))
        expected = "not the file this review was made from"

    code, out, err = run(capsys, source, review_csv, out_dir, "--allow-unbound")

    assert code == 2 and out == "" and expected in err
    assert not out_dir.exists()


def test_allow_unbound_still_runs_every_review_check(folder, capsys):
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()
    decide(review_csv, {"A1": "maybe"})

    code, _, err = run(capsys, source, review_csv, out_dir, "--allow-unbound")

    assert code == 2 and "The review file cannot be used" in err
    assert not out_dir.exists()


# --- Other refusals ----------------------------------------------------------


def test_output_that_is_the_review_file_is_refused(folder, capsys):
    source, review_csv, _ = folder
    renamed = review_csv.rename(review_csv.with_name(FINAL_CSV))

    code, _, err = run(capsys, source, renamed, renamed.parent, "--overwrite")

    assert code == 2 and "is the review file" in err
    assert renamed.exists()


def test_folder_at_an_output_path_is_refused(folder, capsys):
    source, review_csv, out_dir = folder
    (out_dir / FINAL_MD).mkdir(parents=True)

    code, _, err = run(capsys, source, review_csv, out_dir, "--overwrite")

    assert code == 2 and "are not files" in err and "Nothing was changed." in err


def test_missing_input_is_reported_as_an_input_problem(folder, capsys):
    source, review_csv, out_dir = folder
    source.unlink()

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and err.strip() == f"Error: input file not found: {source}"


def test_input_that_is_a_folder_is_reported_as_such(folder, capsys, tmp_path):
    _, review_csv, out_dir = folder
    a_folder = tmp_path / "a_folder"
    a_folder.mkdir()

    code, _, err = run(capsys, a_folder, review_csv, out_dir)

    assert code == 2 and err.strip() == f"Error: input is a folder, not a CSV file: {a_folder}"


def test_input_that_is_not_utf8_is_reported(folder, capsys):
    source, review_csv, out_dir = folder
    # Without the manifest (and with --allow-unbound) the edited input is not
    # refused first as a fingerprint mismatch, so the input loader runs.
    (review_csv.parent / MANIFEST_NAME).unlink()
    source.write_bytes("id,sender,subject,body\nA1,a,b,caf\xe9\n".encode("latin-1"))

    code, _, err = run(capsys, source, review_csv, out_dir, "--allow-unbound")

    assert code == 2 and err.strip() == f"Error: input file is not valid UTF-8 text: {source}"


def test_empty_input_is_reported(folder, capsys):
    # MessageFileError from the loader; the manifest is removed for the same
    # reason as in the UTF-8 test above.
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()
    source.write_text("", encoding="utf-8")

    code, out, err = run(capsys, source, review_csv, out_dir, "--allow-unbound")

    assert code == 2 and out == ""
    assert err.startswith("Error: The CSV file is empty")
    assert not out_dir.exists()


def test_input_that_is_not_valid_csv_is_reported(folder, capsys):
    # csv.Error from the loader: a field longer than the csv module allows.
    source, review_csv, out_dir = folder
    (review_csv.parent / MANIFEST_NAME).unlink()
    source.write_text(
        'id,sender,subject,body\nA1,a,b,"' + "x" * 200000 + '"\n', encoding="utf-8"
    )

    code, out, err = run(capsys, source, review_csv, out_dir, "--allow-unbound")

    assert code == 2 and out == ""
    assert err.startswith("Error: input file is not a valid CSV file: ")
    assert not out_dir.exists()


# --- Classifying unwrapped OS errors ----------------------------------------------


@pytest.mark.parametrize("error_type", [FileNotFoundError, IsADirectoryError, PermissionError])
def test_output_side_errors_are_not_reported_as_input_problems(
    folder, capsys, monkeypatch, error_type
):
    source, review_csv, out_dir = folder
    real_mkstemp = tempfile.mkstemp

    def fail_for_csv(*args, **kwargs):
        if kwargs.get("prefix", "").startswith(f".{FINAL_CSV}."):
            raise error_type(2, "simulated", str(out_dir / f".{FINAL_CSV}.x.tmp"))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", fail_for_csv)

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2
    assert err.startswith("Error: could not write the finalized files: ")
    assert "input file not found" not in err and "input is a folder" not in err


def test_os_error_without_a_file_name_is_reported_generically(folder, capsys, monkeypatch):
    source, review_csv, out_dir = folder

    def fail(*args, **kwargs):
        raise OSError("simulated")

    monkeypatch.setattr(cli, "finalize_review", fail)

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and err.strip() == "Error: could not finalize the review: simulated"


def test_manifest_that_cannot_be_checked_is_reported_as_such(folder, capsys, monkeypatch):
    source, review_csv, out_dir = folder
    manifest = review_csv.parent / MANIFEST_NAME

    def fail(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(manifest))

    monkeypatch.setattr(cli, "finalize_review", fail)

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and err.startswith("Error: could not check the review manifest: ")


def test_real_manifest_check_failure_is_reported_as_such(folder, capsys, monkeypatch):
    # The real path: os.lstat of the manifest fails with an unwrapped error.
    source, review_csv, out_dir = folder
    manifest = os.fspath(review_csv.parent / MANIFEST_NAME)
    real_lstat = os.lstat

    def deny_manifest(path, *args, **kwargs):
        if os.fspath(path) == manifest:
            raise PermissionError(13, "Permission denied", manifest)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", deny_manifest)

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and err.startswith("Error: could not check the review manifest: ")
    assert not out_dir.exists()


def test_relative_paths_are_resolved_before_comparing(folder, capsys, monkeypatch, tmp_path):
    # The manifest error names an absolute path, while --review is relative;
    # only resolving both paths classifies it as a manifest problem.
    _, review_csv, _ = folder
    monkeypatch.chdir(tmp_path)
    manifest = os.fspath(review_csv.parent / MANIFEST_NAME)
    real_lstat = os.lstat

    def deny_manifest(path, *args, **kwargs):
        if os.path.abspath(os.fspath(path)) == manifest:
            raise PermissionError(13, "Permission denied", manifest)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", deny_manifest)

    code, _, err = run(capsys, "input.csv", "review/../review/review.csv", "final")

    assert code == 2 and err.startswith("Error: could not check the review manifest: ")
    assert cli._same_path("review/../input.csv", tmp_path / "input.csv")
    assert not cli._same_path("input.csv", tmp_path / "review" / "input.csv")


def test_input_read_error_is_reported_as_an_input_problem(folder, capsys, monkeypatch):
    source, review_csv, out_dir = folder

    def fail(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(source))

    monkeypatch.setattr(cli, "finalize_review", fail)

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and err.startswith("Error: could not read the input file: ")


# --- Notes and partial output --------------------------------------------------


def test_notes_on_an_error_are_printed(folder, capsys, monkeypatch):
    # A temp file that could not be removed is reported as a note on the
    # original error; the CLI must show it, since str(exc) leaves notes out.
    source, review_csv, out_dir = folder
    real_mkstemp, real_remove = tempfile.mkstemp, os.remove
    left = []

    def fail_for_csv(*args, **kwargs):
        if kwargs.get("prefix", "").startswith(f".{FINAL_CSV}."):
            raise OSError(28, "No space left on device", str(out_dir / FINAL_CSV))
        return real_mkstemp(*args, **kwargs)

    def keep_md_temp(path, *args, **kwargs):
        if os.path.basename(path).startswith(f".{FINAL_MD}."):
            left.append(os.fspath(path))
            raise OSError("busy")
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", fail_for_csv)
    monkeypatch.setattr(os, "remove", keep_md_temp)

    code, _, err = run(capsys, source, review_csv, out_dir)

    assert code == 2
    assert err.splitlines() == [
        f"Error: could not write the finalized files: [Errno 28] No space left on device: "
        f"'{out_dir / FINAL_CSV}'",
        f"Note: Temporary files could not be removed: {left[0]}",
    ]


def test_partial_output_is_reported_with_leftover_temp_files(folder, capsys, monkeypatch):
    source, review_csv, out_dir = folder
    real_replace, real_remove = os.replace, os.remove
    left = []

    def fail_for_csv(src, dst, *args, **kwargs):
        if os.path.basename(dst) == FINAL_CSV:
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    def keep_csv_temp(path, *args, **kwargs):
        if os.path.basename(path).startswith(f".{FINAL_CSV}."):
            left.append(os.fspath(path))
            raise OSError("busy")
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_for_csv)
    monkeypatch.setattr(os, "remove", keep_csv_temp)

    code, out, err = run(capsys, source, review_csv, out_dir)

    assert code == 2 and out == ""
    assert err.startswith(
        f"Error: The finalized files in {out_dir} were left incomplete after an error"
    )
    assert f"New version written: {FINAL_MD}." in err
    assert f"Not written: {FINAL_CSV}." in err
    assert f"Temporary files could not be removed: {left[0]}." in err
