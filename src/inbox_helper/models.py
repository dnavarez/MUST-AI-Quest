"""Simple data containers used across the program."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    """One incoming message, exactly as read from the CSV file."""

    id: str
    sender: str
    subject: str
    body: str


@dataclass(frozen=True)
class KeywordMatch:
    """One keyword found in one sentence: the evidence for a category."""

    category: str
    keyword: str
    location: str  # "subject" or "body"
    sentence: str


@dataclass(frozen=True)
class OverrideSignal:
    """Text in a message that looks like an instruction aimed at the tool."""

    pattern: str  # short description of the pattern that matched
    location: str  # "subject" or "body"
    sentence: str


@dataclass(frozen=True)
class Draft:
    """A suggested reply for one message. It is never sent by this tool."""

    message_id: str
    text: str | None  # None when there is nothing that can be drafted
    status: str  # always "pending_review" when created
    warnings: tuple[str, ...]  # the caller's warnings plus any added here
    note: str  # explanation for the reviewer, e.g. why there is no draft


@dataclass(frozen=True)
class Classification:
    """The intent result for one message, with the evidence behind it."""

    message_id: str
    primary_intent: str
    secondary_intents: tuple[str, ...]
    flags: tuple[str, ...]
    matches: tuple[KeywordMatch, ...]
