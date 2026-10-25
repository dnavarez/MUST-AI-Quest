"""The review manifest: links a review folder to its input file (Stage 4b-2).

The draft command writes review.manifest.json next to review.md and
review.csv. It records the input file's name and SHA-256 fingerprint, so a
review can later be checked against the exact input it was made from.

The manifest protects against mistakes (the wrong input file, or an input
changed after drafting), not against deliberate tampering: it is not signed,
and anyone can edit it. The name is informational; the fingerprint decides.

Reading is strict. The file must be a regular file (not a symbolic link,
where the system can tell), at most MAX_MANIFEST_BYTES long, UTF-8 JSON with
exactly the expected keys and value types, with no duplicate keys and no
NaN or Infinity. Error messages never repeat values from the manifest.

This module imports nothing else from the project, so any module can use it.
"""

import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass

MANIFEST_NAME = "review.manifest.json"
MANIFEST_FORMAT = "inbox_helper review manifest"
MANIFEST_VERSION = 1
MANIFEST_KEYS = ("format", "version", "input_name", "input_sha256")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_NAME_LENGTH = 255  # characters in input_name

_SHA256 = re.compile(r"[0-9a-f]{64}")
# Control, format (for example bidirectional overrides) and surrogate
# characters. A surrogate means a file name that is not valid Unicode.
_REFUSED_CATEGORIES = ("Cc", "Cf", "Cs")


class ManifestError(ValueError):
    """Raised when a review manifest exists but cannot be used."""

    def __init__(self, path, problem):
        self.path = path
        self.problem = problem
        super().__init__(f"the review manifest {path} cannot be used: {problem}")


@dataclass(frozen=True)
class Manifest:
    input_name: str
    input_sha256: str


def input_name_problem(name):
    """Why `name` cannot be stored as input_name, or None if it can."""
    if not isinstance(name, str) or not name:
        return "the input file name must be a non-empty text"
    if len(name) > MAX_NAME_LENGTH:
        return f"the input file name is longer than {MAX_NAME_LENGTH} characters"
    if "/" in name or "\\" in name or name in (".", ".."):
        return "the input file name must be a file name, not a path"
    if any(unicodedata.category(ch) in _REFUSED_CATEGORIES for ch in name):
        return "the input file name contains control, invisible or invalid characters"
    return None


def render_manifest(input_name, input_sha256):
    """The manifest file's bytes: the same values always give the same bytes."""
    problem = input_name_problem(input_name)
    if problem:
        raise ValueError(problem)
    if not isinstance(input_sha256, str) or not _SHA256.fullmatch(input_sha256):
        raise ValueError("input_sha256 must be 64 lower-case hexadecimal characters")
    data = {
        "format": MANIFEST_FORMAT,
        "version": MANIFEST_VERSION,
        "input_name": input_name,
        "input_sha256": input_sha256,
    }
    return (json.dumps(data, ensure_ascii=True, indent=2) + "\n").encode("ascii")


class _DuplicateKey(Exception):
    pass


def _no_duplicates(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen.add(key)
    return dict(pairs)


def _refuse_constant(name):
    raise ValueError(f"{name} is not allowed")


def _read_bytes(path):
    """The manifest's bytes, or None if there is no file at `path`."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode):
        raise ManifestError(path, "it is a symbolic link, not a regular file")
    if not stat.S_ISREG(before.st_mode):
        raise ManifestError(path, "it is not a regular file")
    # O_NOFOLLOW refuses a symbolic link put in place after the check above;
    # O_NONBLOCK keeps a special file put there from blocking the open.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ManifestError(path, f"it could not be opened ({exc.strerror})") from None
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev, before.st_ino
        ):
            raise ManifestError(path, "it changed while it was being opened")
        data = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError(path, f"it is larger than {MAX_MANIFEST_BYTES} bytes")
    return data


def read_manifest(path):
    """The Manifest at `path`, or None if there is no file there.

    Raises ManifestError for anything else that is not a valid manifest,
    including a broken symbolic link.
    """
    data = _read_bytes(path)
    if data is None:
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ManifestError(path, "it is not UTF-8 text") from None
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_refuse_constant)
    except _DuplicateKey as exc:
        key = exc.args[0]
        shown = f'"{key}"' if key in MANIFEST_KEYS else "a key"
        raise ManifestError(path, f"{shown} appears more than once") from None
    except RecursionError:
        raise ManifestError(path, "it is nested too deeply to be a manifest") from None
    except json.JSONDecodeError as exc:
        raise ManifestError(
            path, f"it is not valid JSON (line {exc.lineno}, column {exc.colno})"
        ) from None
    except ValueError:  # NaN, Infinity, or a number with too many digits
        raise ManifestError(
            path, "it contains a value that cannot be read (NaN, Infinity or a very long number)"
        ) from None
    return _checked(path, value)


def _checked(path, value):
    if not isinstance(value, dict):
        raise ManifestError(path, "it must hold a JSON object")
    missing = [key for key in MANIFEST_KEYS if key not in value]
    if missing:
        raise ManifestError(path, f"missing key(s): {', '.join(missing)}")
    unknown = len(value) - len(MANIFEST_KEYS)
    if unknown:
        raise ManifestError(path, f"it has {unknown} unknown key(s)")
    if value["format"] != MANIFEST_FORMAT:
        raise ManifestError(path, f'"format" must be "{MANIFEST_FORMAT}"')
    # type() rather than isinstance(): true would otherwise count as 1.
    if type(value["version"]) is not int or value["version"] != MANIFEST_VERSION:
        raise ManifestError(path, f'"version" must be the number {MANIFEST_VERSION}')
    sha256 = value["input_sha256"]
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ManifestError(path, '"input_sha256" must be 64 lower-case hexadecimal characters')
    problem = input_name_problem(value["input_name"])
    if problem:
        raise ManifestError(path, f'"input_name" is not valid: {problem}')
    return Manifest(value["input_name"], sha256)
