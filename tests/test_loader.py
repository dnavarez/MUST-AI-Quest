import pytest

from inbox_helper.loader import MessageFileError, load_messages
from inbox_helper.models import Message

HEADER = "id,sender,subject,body\n"


def write_csv(tmp_path, text):
    """Write `text` to a temporary CSV file and return its path."""
    path = tmp_path / "messages.csv"
    path.write_text(text, encoding="utf-8")
    return path


def load_error(path):
    """Return the full text of the MessageFileError raised for `path`.

    Tests compare the whole message with ==, so they cannot pass just
    because a word also appears in pytest's temporary folder name.
    """
    with pytest.raises(MessageFileError) as error:
        load_messages(path)
    return str(error.value)


# --- Valid files ---------------------------------------------------------


def test_valid_file_returns_messages_in_order(tmp_path):
    path = write_csv(
        tmp_path,
        HEADER
        + "m1,ana@example.com,Meeting,Can we meet on Tuesday?\n"
        + 'm2,ben@example.com,Login,"I can\'t log in, please help."\n',
    )

    messages = load_messages(path)

    assert messages == [
        Message("m1", "ana@example.com", "Meeting", "Can we meet on Tuesday?"),
        Message("m2", "ben@example.com", "Login", "I can't log in, please help."),
    ]


def test_extra_columns_are_ignored_and_empty_cells_become_empty_strings(tmp_path):
    path = write_csv(
        tmp_path,
        "id,sender,subject,body,notes\n"
        "m1,ana@example.com,,,ignored note\n",
    )

    messages = load_messages(path)

    assert messages == [Message("m1", "ana@example.com", "", "")]


def test_excel_style_file_with_byte_order_mark_is_accepted(tmp_path):
    path = tmp_path / "messages.csv"
    path.write_text(HEADER + "m1,a,b,c\n", encoding="utf-8-sig")

    assert load_messages(path) == [Message("m1", "a", "b", "c")]


def test_header_only_file_returns_no_messages(tmp_path):
    path = write_csv(tmp_path, HEADER)

    assert load_messages(path) == []


# --- Empty file and missing columns --------------------------------------


@pytest.mark.parametrize("content", ["", "\n", "   \n\n"])
def test_empty_file_raises_clear_error(tmp_path, content):
    path = write_csv(tmp_path, content)

    assert load_error(path) == f"The CSV file is empty: {path}"


def test_missing_one_column_names_it_in_the_error(tmp_path):
    path = write_csv(tmp_path, "id,sender,subject\nm1,a,b\n")

    assert load_error(path) == (
        f"The CSV file {path} is missing required column(s): body. "
        "Required columns are: id, sender, subject, body."
    )


def test_missing_several_columns_names_all_of_them(tmp_path):
    path = write_csv(tmp_path, "id,body\nm1,hello\n")

    assert load_error(path) == (
        f"The CSV file {path} is missing required column(s): sender, subject. "
        "Required columns are: id, sender, subject, body."
    )


# --- Message ids ---------------------------------------------------------


def test_id_with_surrounding_spaces_is_trimmed(tmp_path):
    path = write_csv(tmp_path, HEADER + "  m1  ,a,b,c\n")

    assert load_messages(path) == [Message("m1", "a", "b", "c")]


def test_blank_id_is_rejected_with_its_row_number(tmp_path):
    path = write_csv(tmp_path, HEADER + "m1,a,b,c\n" + ",a,b,c\n")

    assert load_error(path) == f"{path}, row 3: the id is blank."


def test_whitespace_only_id_is_rejected_with_its_row_number(tmp_path):
    path = write_csv(tmp_path, HEADER + "   ,a,b,c\n")

    assert load_error(path) == f"{path}, row 2: the id is blank."


def test_duplicate_id_is_rejected_naming_both_rows(tmp_path):
    path = write_csv(tmp_path, HEADER + "m1,a,b,c\n" + "m2,a,b,c\n" + "m1,a,b,c\n")

    assert load_error(path) == f"{path}, row 4: the id 'm1' is a duplicate of row 2."


def test_ids_that_only_differ_by_spaces_count_as_duplicates(tmp_path):
    path = write_csv(tmp_path, HEADER + "m1,a,b,c\n" + " m1 ,a,b,c\n")

    assert load_error(path) == f"{path}, row 3: the id 'm1' is a duplicate of row 2."
