"""Read messages from a CSV file and check that the file has the right shape."""

import csv
from pathlib import Path

from inbox_helper.models import Message

REQUIRED_COLUMNS = ("id", "sender", "subject", "body")


class MessageFileError(ValueError):
    """Raised when the CSV file cannot be used as a message file."""


def load_messages(path):
    """Return the messages in the CSV file at `path`, in file order.

    Raises MessageFileError if the file is empty, is missing a required
    column, or has a blank or duplicate id. Ids are trimmed of surrounding
    spaces. Extra columns are ignored. Other empty cells become empty
    strings. A file with a valid header but no messages returns [].
    """
    path = Path(path)

    # "utf-8-sig" also accepts files saved by Excel, which start with an
    # invisible marker that would otherwise become part of the "id" header.
    # newline="" is what the csv module documentation asks for.
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        # No header at all, or a first line made only of spaces, means the
        # file has no usable content.
        if reader.fieldnames is None or not any(
            name.strip() for name in reader.fieldnames
        ):
            raise MessageFileError(f"The CSV file is empty: {path}")

        columns = [name.strip() for name in reader.fieldnames]
        missing = [name for name in REQUIRED_COLUMNS if name not in columns]
        if missing:
            raise MessageFileError(
                f"The CSV file {path} is missing required column(s): "
                f"{', '.join(missing)}. "
                f"Required columns are: {', '.join(REQUIRED_COLUMNS)}."
            )
        reader.fieldnames = columns

        messages = []
        first_row_for_id = {}
        # Row numbers match a spreadsheet: the header is row 1, so the
        # first message is row 2.
        for row_number, row in enumerate(reader, start=2):
            message_id = (row["id"] or "").strip()
            if not message_id:
                raise MessageFileError(f"{path}, row {row_number}: the id is blank.")
            if message_id in first_row_for_id:
                raise MessageFileError(
                    f"{path}, row {row_number}: the id {message_id!r} is a "
                    f"duplicate of row {first_row_for_id[message_id]}."
                )
            first_row_for_id[message_id] = row_number

            messages.append(
                Message(
                    id=message_id,
                    sender=row["sender"] or "",
                    subject=row["subject"] or "",
                    body=row["body"] or "",
                )
            )
        return messages
