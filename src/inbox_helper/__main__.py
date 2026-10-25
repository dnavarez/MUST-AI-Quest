"""Command-line entry point.

    python -m inbox_helper draft INPUT --out DIR
    python -m inbox_helper finalize INPUT --review REVIEW_CSV --out DIR

Nothing is ever sent. `draft` writes review files for a person to read and
decide on; `finalize` checks the completed review against the input and
writes the approved replies, marked not sent, for the person to send
themselves.
"""

import argparse
import csv
import sys
from pathlib import Path

from inbox_helper.finalize import ReviewFileError
from inbox_helper.finalize_files import (
    FinalOutputConflictError,
    FinalOutputExistsError,
    FinalPartialOutputError,
    finalize_review,
)
from inbox_helper.loader import MessageFileError
from inbox_helper.manifest import MANIFEST_NAME
from inbox_helper.review import (
    InputChangedError,
    InputNameError,
    InputOutputConflictError,
    OutputExistsError,
    PartialOutputError,
    generate_review,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m inbox_helper",
        description="Draft replies for human review. Nothing is ever sent.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    draft = commands.add_parser(
        "draft",
        help="classify messages and write review.md, review.csv and review.manifest.json",
    )
    draft.add_argument("input", help="CSV file with columns id, sender, subject, body")
    draft.add_argument("--out", required=True, help="folder for the review files")
    draft.add_argument(
        "--overwrite", action="store_true",
        help="replace existing review files (they may contain review decisions)",
    )
    finalize = commands.add_parser(
        "finalize",
        help="check a completed review.csv and write approved_unsent.md and .csv (not sent)",
    )
    finalize.add_argument("input", help="the original message CSV the review was made from")
    finalize.add_argument("--review", required=True, help="the completed review.csv")
    finalize.add_argument("--out", required=True, help="folder for the finalized files")
    finalize.add_argument(
        "--overwrite", action="store_true",
        help="replace existing approved_unsent.md and approved_unsent.csv",
    )
    finalize.add_argument(
        "--allow-unbound", action="store_true",
        help="accept a review folder without review.manifest.json; the review is then "
        "only checked against the input's messages, not its fingerprint",
    )
    args = parser.parse_args(argv)
    if args.command == "finalize":
        return _finalize(args)
    return _draft(args)


def _draft(args):
    try:
        summary = generate_review(args.input, args.out, overwrite=args.overwrite)
    except FileNotFoundError:
        return _error(f"input file not found: {args.input}")
    except IsADirectoryError:
        return _error(f"input is a folder, not a CSV file: {args.input}")
    except UnicodeDecodeError:
        return _error(f"input file is not valid UTF-8 text: {args.input}")
    except csv.Error as exc:
        return _error(f"input file is not a valid CSV file: {exc}")
    except (
        MessageFileError, OutputExistsError, InputOutputConflictError,
        InputNameError, InputChangedError, PartialOutputError,
    ) as exc:
        return _error(str(exc))
    except OSError as exc:
        return _error(f"could not write the review files: {exc}")

    print(
        f"Reviewed {summary['messages']} message(s): {summary['drafts']} draft(s), "
        f"{summary['messages'] - summary['drafts']} without a draft, "
        f"{summary['with_warnings']} with warnings."
    )
    print(f"Wrote {summary['review_md']}")
    print(f"Wrote {summary['review_csv']}")
    print(f"Wrote {summary['manifest']}")
    print("Nothing was sent. Every draft is pending_review.")
    return 0


def _finalize(args):
    try:
        summary = finalize_review(
            args.input, args.review, args.out,
            overwrite=args.overwrite, allow_unbound=args.allow_unbound,
        )
    except (
        ReviewFileError, MessageFileError, FinalOutputExistsError,
        FinalOutputConflictError, FinalPartialOutputError,
    ) as exc:
        return _error(str(exc), exc)
    # Review-file problems are already ReviewFileError, so these two can
    # only come from the input file.
    except UnicodeDecodeError as exc:
        return _error(f"input file is not valid UTF-8 text: {args.input}", exc)
    except csv.Error as exc:
        return _error(f"input file is not a valid CSV file: {exc}", exc)
    except OSError as exc:
        return _error(_finalize_os_error(exc, args), exc)

    print(
        f"Finalized {summary['messages']} message(s): {summary['approved']} approved, "
        f"{summary['edited']} edited, {summary['rejected']} rejected, "
        f"{summary['pending']} pending."
    )
    if summary["bound"]:
        print(f"Input binding: verified by SHA-256 {summary['input_sha256']}.")
    else:
        print(
            "Warning: input binding was NOT checked (--allow-unbound): there is no "
            "review manifest, so the review was only checked against the input's messages."
        )
    print(f"Wrote {summary['approved_unsent_md']}")
    print(f"Wrote {summary['approved_unsent_csv']}")
    print(
        "Nothing was sent. Every reply is approved_unsent; send it yourself from "
        "your own email tool."
    )
    return 0


def _finalize_os_error(exc, args):
    """Say which file an unwrapped OSError is about, using exc.filename.

    Problems with the review file are already ReviewFileError. An error
    names the input only if it is about the input path; anything else is
    never reported as an input problem.
    """
    if exc.filename is None:
        return f"could not finalize the review: {exc}"
    if _same_path(exc.filename, args.input):
        if isinstance(exc, FileNotFoundError):
            return f"input file not found: {args.input}"
        if isinstance(exc, IsADirectoryError):
            return f"input is a folder, not a CSV file: {args.input}"
        return f"could not read the input file: {exc}"
    if _same_path(exc.filename, Path(args.review), manifest=True):
        return f"could not check the review manifest: {exc}"
    return f"could not write the finalized files: {exc}"


def _same_path(a, b, manifest=False):
    """True if a and b resolve to the same path; with `manifest`, b is the
    review file and its manifest is compared (as finalize finds it)."""
    try:
        b = Path(b).resolve()
        if manifest:
            b = b.parent / MANIFEST_NAME
        return Path(a).resolve() == b
    except (OSError, RuntimeError, ValueError):
        return False


def _error(text, exc=None):
    print(f"Error: {text}", file=sys.stderr)
    for note in getattr(exc, "__notes__", ()):
        print(f"Note: {note}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
