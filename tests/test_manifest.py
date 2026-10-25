"""Tests for the review manifest (Stage 4b-2): writing and strict reading."""

import json
import os

import pytest

from inbox_helper.manifest import (
    MANIFEST_FORMAT,
    MAX_MANIFEST_BYTES,
    Manifest,
    ManifestError,
    input_name_problem,
    read_manifest,
    render_manifest,
)

SHA = "0123456789abcdef" * 4
SECRET = "Sekr3tValue"  # planted in bad manifests; must never be shown


def good(**changes):
    data = {"format": MANIFEST_FORMAT, "version": 1, "input_name": "messages.csv", "input_sha256": SHA}
    data.update(changes)
    return data


def write(tmp_path, content, name="review.manifest.json"):
    path = tmp_path / name
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def refused(path):
    with pytest.raises(ManifestError) as caught:
        read_manifest(path)
    assert SECRET not in str(caught.value)
    return str(caught.value)


# --- Writing -----------------------------------------------------------------


def test_round_trip(tmp_path):
    path = write(tmp_path, render_manifest("messages.csv", SHA))
    assert read_manifest(path) == Manifest("messages.csv", SHA)


def test_rendering_is_deterministic_and_ascii():
    first = render_manifest("caf\u00e9 \u4f60\u597d.csv", SHA)
    assert first == render_manifest("caf\u00e9 \u4f60\u597d.csv", SHA)
    assert first.isascii() and first.endswith(b"}\n")
    assert list(json.loads(first)) == ["format", "version", "input_name", "input_sha256"]


def test_non_ascii_name_reads_back(tmp_path):
    path = write(tmp_path, render_manifest("caf\u00e9.csv", SHA))
    assert read_manifest(path).input_name == "caf\u00e9.csv"


@pytest.mark.parametrize("sha", [SHA.upper(), SHA[:-1], "g" * 64, None])
def test_rendering_refuses_a_bad_fingerprint(sha):
    with pytest.raises(ValueError):
        render_manifest("messages.csv", sha)


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "a/b.csv", "a\\b.csv", "x" * 256, "a\nb.csv", "a\u0000b", "a\u202eb.csv",
     "a\u200bb.csv", "a\udcffb.csv"],
)
def test_names_that_cannot_be_recorded(name):
    assert input_name_problem(name) is not None
    with pytest.raises(ValueError):
        render_manifest(name, SHA)


@pytest.mark.parametrize("name", ["messages.csv", "x" * 255, "my inbox (1).csv", "caf\u00e9.csv"])
def test_names_that_can_be_recorded(name):
    assert input_name_problem(name) is None


# --- Reading: missing and file types -----------------------------------------


def test_missing_manifest_is_none(tmp_path):
    assert read_manifest(tmp_path / "review.manifest.json") is None


def test_folder_is_refused(tmp_path):
    (tmp_path / "review.manifest.json").mkdir()
    assert "not a regular file" in refused(tmp_path / "review.manifest.json")


def _symlink(target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform cannot create symbolic links here: {exc}")


def test_symbolic_link_is_refused_even_to_a_valid_manifest(tmp_path):
    real = write(tmp_path, render_manifest("messages.csv", SHA), name="real.json")
    _symlink(real, tmp_path / "review.manifest.json")
    assert "symbolic link" in refused(tmp_path / "review.manifest.json")


def test_broken_symbolic_link_is_refused_not_missing(tmp_path):
    _symlink(tmp_path / "nowhere.json", tmp_path / "review.manifest.json")
    assert "symbolic link" in refused(tmp_path / "review.manifest.json")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes on this platform")
def test_named_pipe_is_refused_without_blocking(tmp_path):
    os.mkfifo(tmp_path / "review.manifest.json")
    assert "not a regular file" in refused(tmp_path / "review.manifest.json")


def test_too_large_is_refused(tmp_path):
    padding = " " * MAX_MANIFEST_BYTES
    path = write(tmp_path, json.dumps(good()) + padding)
    assert "larger than" in refused(path)


def test_largest_allowed_size_is_read(tmp_path):
    text = json.dumps(good())
    path = write(tmp_path, text + " " * (MAX_MANIFEST_BYTES - len(text)))
    assert read_manifest(path) == Manifest("messages.csv", SHA)


# --- Reading: content --------------------------------------------------------


def test_byte_order_mark_is_accepted(tmp_path):
    path = write(tmp_path, b"\xef\xbb\xbf" + render_manifest("messages.csv", SHA))
    assert read_manifest(path) == Manifest("messages.csv", SHA)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\xff\xfe{}", "not UTF-8"),
        ("", "not valid JSON"),
        (f"{SECRET}", "not valid JSON"),
        (f'{{"format": "{SECRET}"', "not valid JSON"),
        (f'["{SECRET}"]', "JSON object"),
        ('"text"', "JSON object"),
        ("null", "JSON object"),
        ("[" * 30000 + "]" * 30000, "JSON object"),
        ('{"a": ' * 9000 + "1" + "}" * 9000, "missing key(s)"),
        ('{"format": NaN}', "NaN"),
        ('{"version": Infinity}', "NaN"),
        ('{"version": -Infinity}', "NaN"),
        ('{"version": ' + "9" * 5000 + "}", "very long number"),
    ],
)
def test_unreadable_content_is_refused(tmp_path, content, expected):
    assert expected in refused(write(tmp_path, content))


def test_recursion_error_is_refused(tmp_path, monkeypatch):
    from inbox_helper import manifest

    def too_deep(*args, **kwargs):
        raise RecursionError

    monkeypatch.setattr(manifest.json, "loads", too_deep)
    assert "nested too deeply" in refused(write(tmp_path, json.dumps(good())))


def test_duplicate_known_key_is_named(tmp_path):
    text = json.dumps(good())[:-1] + f', "input_sha256": "{SHA}"}}'
    assert '"input_sha256" appears more than once' in refused(write(tmp_path, text))


def test_duplicate_unknown_key_is_not_named(tmp_path):
    text = json.dumps(good())[:-1] + f', "{SECRET}": 1, "{SECRET}": 2}}'
    message = refused(write(tmp_path, text))
    assert "a key appears more than once" in message


def test_duplicate_key_in_a_nested_object_is_refused(tmp_path):
    text = json.dumps(good())[:-1] + ', "extra": {"a": 1, "a": 2}}'
    assert "more than once" in refused(write(tmp_path, text))


@pytest.mark.parametrize("missing", ["format", "version", "input_name", "input_sha256"])
def test_missing_key_is_refused(tmp_path, missing):
    data = good()
    del data[missing]
    assert f"missing key(s): {missing}" in refused(write(tmp_path, json.dumps(data)))


def test_unknown_key_is_counted_not_shown(tmp_path):
    message = refused(write(tmp_path, json.dumps(good(**{SECRET: SECRET}))))
    assert "1 unknown key(s)" in message


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"format": SECRET}, '"format" must be'),
        ({"format": ["inbox_helper review manifest"]}, '"format" must be'),
        ({"version": 2}, '"version" must be'),
        ({"version": "1"}, '"version" must be'),
        ({"version": 1.0}, '"version" must be'),
        ({"version": True}, '"version" must be'),
        ({"input_sha256": SHA.upper()}, '"input_sha256" must be'),
        ({"input_sha256": SHA[:-1]}, '"input_sha256" must be'),
        ({"input_sha256": SHA + "0"}, '"input_sha256" must be'),
        ({"input_sha256": SHA[:-1] + "\n"}, '"input_sha256" must be'),
        ({"input_sha256": (SECRET * 6)[:64]}, '"input_sha256" must be'),
        ({"input_sha256": 12345}, '"input_sha256" must be'),
        ({"input_name": ""}, '"input_name" is not valid'),
        ({"input_name": f"../{SECRET}.csv"}, '"input_name" is not valid'),
        ({"input_name": f"C:\\{SECRET}.csv"}, '"input_name" is not valid'),
        ({"input_name": ".."}, '"input_name" is not valid'),
        ({"input_name": f"{SECRET}\u0007.csv"}, '"input_name" is not valid'),
        ({"input_name": SECRET * 30}, '"input_name" is not valid'),
        ({"input_name": 7}, '"input_name" is not valid'),
        ({"input_name": None}, '"input_name" is not valid'),
    ],
)
def test_wrong_values_are_refused_without_being_shown(tmp_path, changes, expected):
    assert expected in refused(write(tmp_path, json.dumps(good(**changes))))
