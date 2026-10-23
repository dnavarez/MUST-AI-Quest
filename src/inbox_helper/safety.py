"""Warnings about message text that looks like instructions to the tool.

Message text is untrusted data. Nothing here changes how a message is
classified or drafted; it only raises a warning for the human reviewer.

These are simple text patterns. They can miss attacks (other wording, other
languages, deliberate misspellings) and can flag harmless text. A warning
is a reason to look carefully, not proof of bad intent. The real protection
is that the tool cannot send anything and every draft needs a human decision.
"""

import re

from inbox_helper.classifier import split_sentences
from inbox_helper.models import OverrideSignal

OVERRIDE_WARNING = "possible_instruction_override"

# (description shown to the reviewer, pattern). Patterns are matched against
# lower-cased text, so they only need lower-case words.
_OVERRIDE_PATTERNS = [
    (
        "asks to ignore instructions or rules",
        r"\b(?:ignore|disregard|forget|override)\s+(?:(?:all|any|the|your|these|those)\s+)*"
        r"(?:(?:previous|prior|above|earlier|system)\s+)?"
        r"(?:instructions?|rules?|guidelines?|prompts?|policies)\b",
    ),
    (
        "claims to be a system message",
        r"\bsystem\s+(?:note|prompt|instructions?)\b|\byou are now\b|\bnew instructions\b",
    ),
    (
        "asks to bypass human review",
        r"\b(?:bypass|skip|circumvent)\s+(?:(?:the|any)\s+)?(?:(?:human|manual)\s+)?"
        r"(?:review|approval|checks?)\b"
        r"|\b(?:do not|don't|no need to)\s+wait\s+for\s+(?:a\s+)?human\b",
    ),
    (
        "asks to mark a draft as approved",
        r"\bmark\b(?:\s+\w+){0,3}?\s+(?:as\s+)?approved\b"
        r"|\b(?:this|the)\s+(?:message|reply|request|email)\s+(?:is|has been)\s+(?:pre-?)?approved\b",
    ),
    (
        "asks for automatic sending",
        r"\b(?:send|reply|respond)\b(?:\s+\w+){0,4}?\s+automatically\b|\bauto-?send\b",
    ),
    (
        "claims authority over the tool",
        r"\bas (?:the|an|your) (?:administrator|admin|developer|system owner)\b"
        r"|\bi (?:hereby )?authori[sz]e you\b",
    ),
]
_COMPILED = [(label, re.compile(pattern)) for label, pattern in _OVERRIDE_PATTERNS]


def find_override_signals(message):
    """Return an OverrideSignal for each pattern found, sentence by sentence."""
    signals = []
    for location, text in (("subject", message.subject), ("body", message.body)):
        for sentence in split_sentences(text):
            lowered = " ".join(sentence.lower().split())
            for label, pattern in _COMPILED:
                if pattern.search(lowered):
                    signals.append(OverrideSignal(label, location, sentence))
    return tuple(signals)


def safety_warnings(message):
    """Return the warning codes for a message (currently at most one)."""
    return (OVERRIDE_WARNING,) if find_override_signals(message) else ()
