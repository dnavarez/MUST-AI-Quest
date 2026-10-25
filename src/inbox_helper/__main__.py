"""Command-line entry point: python -m inbox_helper draft INPUT --out DIR

Nothing is ever sent. The command only writes review files for a person to
read and decide on.
"""

import argparse
import csv
import sys

from inbox_helper.loader import MessageFileError
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
    args = parser.parse_args(argv)

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


def _error(text):
    print(f"Error: {text}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
