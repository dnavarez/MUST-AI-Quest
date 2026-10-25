"""Write the finalized files: approved_unsent.md and approved_unsent.csv (Stage 4b-3).

finalize_review checks the review with finalize.validate_bound_review (the
manifest binding, then every Stage 4a check), renders both files with the
Stage 4b-1 renderers, and writes them. Nothing is sent: every reply has
status approved_unsent and must be sent by hand.

Output files are never the input, the review file or its manifest (also
through links, ".." or hard links), and existing output files are never
replaced unless `overwrite` is True. Everything is built before anything is
written.

Writing two files is not atomic. With `overwrite`, the old CSV and then the
old Markdown are removed first; the new Markdown is then moved into place,
and the new CSV last. So an old file never sits next to a new one, the new
CSV (the file replies are copied from) only appears after its NOT SENT
report, and an old CSV is never left without its old Markdown unless it was
already alone before the run. If writing fails part-way,
FinalPartialOutputError describes the state of each file as checked on disk.

Error messages and the returned summary hold only paths, file names, counts,
hashes and reasons; never message, reply or note text.
"""

import os
import stat
import tempfile
from collections import Counter
from pathlib import Path

from inbox_helper.final_output import Provenance, render_final_csv, render_final_markdown
from inbox_helper.finalize import validate_bound_review
from inbox_helper.manifest import MANIFEST_NAME
from inbox_helper.review import _same_file

# The output file names. Kept separate from the status value approved_unsent
# (final_output.APPROVED_UNSENT), so renaming one never renames the other.
FINAL_STEM = "approved_unsent"
FINAL_MD = f"{FINAL_STEM}.md"
FINAL_CSV = f"{FINAL_STEM}.csv"


class FinalOutputExistsError(Exception):
    """Raised instead of replacing existing finalized files."""


class FinalOutputConflictError(Exception):
    """Raised when an output path is the input, review or manifest file, or not a file."""


class FinalPartialOutputError(OSError):
    """Raised when writing failed after some finalized files were changed."""


def finalize_review(input_path, review_path, out_dir, overwrite=False, allow_unbound=False):
    """Check the review and write approved_unsent.md and approved_unsent.csv.

    Raises whatever validate_bound_review raises (nothing is written), and
    FinalOutputConflictError, FinalOutputExistsError, FinalPartialOutputError
    or OSError for problems with the output files. Returns a summary
    dictionary.
    """
    input_path, review_path, out_dir = Path(input_path), Path(review_path), Path(out_dir)
    md_path, csv_path = out_dir / FINAL_MD, out_dir / FINAL_CSV
    targets = (md_path, csv_path)
    # The same rule as finalize.validate_bound_review uses to find the manifest.
    manifest_path = review_path.resolve().parent / MANIFEST_NAME
    for target in targets:
        for other, label in ((input_path, "input"), (review_path, "review"),
                             (manifest_path, "review manifest")):
            if _same_file(target, other):
                raise FinalOutputConflictError(
                    f"The output file {target} is the {label} file {other}. "
                    "Choose another folder. Nothing was changed."
                )

    bound = validate_bound_review(input_path, review_path, allow_unbound=allow_unbound)
    provenance = Provenance(
        input_path.name, bound.input_sha256, review_path.name, bound.review_sha256
    )
    md_bytes = render_final_markdown(bound.reviewed, provenance).encode("utf-8")
    csv_bytes = render_final_csv(bound.reviewed).encode("utf-8-sig")

    previous = _check_targets(targets, overwrite)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_final_files(
        out_dir, [(md_path, md_bytes), (csv_path, csv_bytes)], previous, overwrite
    )

    counts = Counter(r.decision for r in bound.reviewed)
    return {
        "messages": len(bound.reviewed),
        "approved": counts["approve"],
        "edited": counts["edit"],
        "rejected": counts["reject"],
        "pending": counts[None],
        "finalized": counts["approve"] + counts["edit"],
        "bound": bound.input_sha256 is not None,
        "input_sha256": bound.input_sha256,
        "manifest_input_name": bound.manifest_input_name,
        "approved_unsent_csv": str(csv_path),
        "approved_unsent_md": str(md_path),
    }


def _check_targets(targets, overwrite):
    """{target: "old" or "absent"}; refuses before anything is changed.

    Every target is checked first. Something that is neither a regular file
    nor a symbolic link (a folder, for example) is refused even with
    `overwrite`, and that refusal comes before "already exists". Any other
    error from os.lstat (for example when out_dir is a file) is raised as
    it is.
    """
    previous, others = {}, []
    for target in targets:
        try:
            mode = os.lstat(target).st_mode
        except FileNotFoundError:
            previous[target] = "absent"
            continue
        previous[target] = "old"
        if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            others.append(target)
    if others:
        raise FinalOutputConflictError(
            f"The output path(s) {', '.join(map(str, others))} exist but are not files "
            "(for example a folder). Remove them or choose another folder. "
            "Nothing was changed."
        )
    existing = [t for t in targets if previous[t] == "old"]
    if existing and not overwrite:
        raise _exists_error(existing)
    return previous


def _exists_error(existing, unchecked=(), missing=()):
    """The refusal, saying truthfully why each file was refused.

    `existing`: seen on disk. `unchecked`: their state could not be checked.
    `missing`: said to exist by the caller but seen absent. --overwrite is
    suggested only when existing files are the whole reason, because it
    cannot help with a file whose state is unknown.
    """
    def paths(targets):
        return ", ".join(map(str, targets))

    sentences = []
    if existing:
        sentences.append(f"Finalized file(s) already exist: {paths(existing)}.")
    if unchecked:
        sentences.append(
            f"The state of finalized file(s) could not be checked: {paths(unchecked)}."
        )
    if missing:
        sentences.append(
            f"Finalized file(s) expected to exist were found absent: {paths(missing)}."
        )
    if unchecked:
        sentences.append("Check that these paths can be read, or choose another folder.")
    elif existing:
        sentences.append("Use --overwrite to replace them, or choose another folder.")
    else:
        sentences.append("Run again, or choose another folder.")
    sentences.append("Nothing was changed.")
    return FinalOutputExistsError(" ".join(sentences))


# --- Writing -----------------------------------------------------------------
# A separate writer from review._write_files (the draft command's), on
# purpose: it removes both old files first and checks every file on disk
# when it fails. A fix to one writer may be needed in the other.

# The expected result of os.lstat for each tracked state.
_EXPECTED = {"old": "present", "new": "present", "removed": "absent", "absent": "absent"}


def _write_final_files(out_dir, files, previous, overwrite):
    """Write `files` ([(target, bytes)], Markdown first) to out_dir.

    `previous` maps each target to "old" or "absent". Old files are removed
    first only if `overwrite` is True.
    Without `overwrite`, it refuses (FinalOutputExistsError, before anything
    is written) if a target is "old" or is not confirmed absent on disk, so
    it never replaces a file even when called without _check_targets.
    If nothing was changed when an error happens, the original OSError is
    raised again; otherwise FinalPartialOutputError, raised from it.
    """
    targets = [target for target, _ in files]
    if not overwrite:
        existing, unchecked, missing = [], [], []
        for t in targets:
            seen = _observe(t)
            if seen == "present":
                existing.append(t)
            elif seen is None:
                unchecked.append(t)
            elif previous[t] == "old":  # absent now, but the caller saw it
                missing.append(t)
        if existing or unchecked or missing:
            raise _exists_error(existing, unchecked, missing)
    state = dict(previous)
    temps = []  # temporary files not yet moved into place
    try:
        for target, data in files:
            fd, temp = tempfile.mkstemp(dir=out_dir, prefix=f".{target.name}.", suffix=".tmp")
            temps.append(temp)
            try:
                handle = os.fdopen(fd, "wb")
            except BaseException:
                _close_quietly(fd)
                raise
            with handle:
                handle.write(data)
        placements = list(zip(list(temps), [target for target, _ in files]))
        for target in reversed(targets):  # CSV, then Markdown
            if overwrite and state[target] == "old":
                os.remove(target)
                state[target] = "removed"
        for temp, target in placements:  # Markdown, then CSV
            os.replace(temp, target)
            state[target] = "new"
            temps.remove(temp)
    except OSError as exc:
        leftovers = _remove_temps(temps)
        unsure = [t for t in targets if _observe(t) != _EXPECTED[state[t]]]
        changed = any(state[t] in ("new", "removed") for t in targets)
        if not changed and not unsure:
            if leftovers:
                exc.add_note(f"Temporary files could not be removed: {', '.join(leftovers)}")
            raise
        raise FinalPartialOutputError(
            _partial_message(out_dir, exc, targets, state, unsure, leftovers)
        ) from exc
    except BaseException as exc:  # interrupts and bugs: clean up, never replace the error
        leftovers = _remove_temps(temps)
        if leftovers:
            exc.add_note(f"Temporary files could not be removed: {', '.join(leftovers)}")
        raise


def _close_quietly(fd):
    try:
        os.close(fd)
    except OSError:
        pass


def _remove_temps(temps):
    """Remove each temporary file; return the ones that could not be removed."""
    left = []
    for temp in temps:
        try:
            os.remove(temp)
        except FileNotFoundError:
            pass
        except OSError:
            left.append(temp)
    return left


def _observe(path):
    """Return "present", "absent", or None if the state cannot be checked. Never raises."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return "absent"
    except OSError:
        return None
    return "present"


def _partial_message(out_dir, exc, targets, state, unsure, leftovers):
    """The partial-write report: sentences joined by one space, names by ", "."""
    def names(wanted):
        return [t.name for t in targets if t not in unsure and state[t] == wanted]

    sentences = [f"The finalized files in {out_dir} were left incomplete after an error ({exc})."]
    for label, found in (
        ("New version written", names("new")),
        ("Removed from a previous run, no new version", names("removed")),
        ("Still from a previous run", names("old")),
        ("Not written", names("absent")),
        ("State could not be confirmed", [t.name for t in unsure]),
        ("Temporary files could not be removed", leftovers),
    ):
        if found:
            sentences.append(f"{label}: {', '.join(found)}.")
    sentences.append(
        "Do not use these files. Run again with --overwrite, or choose another folder."
    )
    return " ".join(sentences)
