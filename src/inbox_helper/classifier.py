"""Rule-based intent classification, following docs/intent.md.

Each category has a fixed list of keywords and phrases. The message is read
sentence by sentence (subject first, then body). The first sentence that
points to exactly one category decides the primary intent.

Thanks is treated as courtesy, not an intent, when the message has any
other category (the approved courtesy-thanks rule).
"""

import re

from inbox_helper.models import Classification, KeywordMatch, Message

OTHER = "other_or_unclear"
THANKS = "thank_you"

# Keywords match whole words only and ignore upper/lower case.
# Plurals and other word forms must be listed separately.
KEYWORDS = {
    "meeting_request": (
        "meet", "meeting", "call", "schedule", "reschedule", "calendar",
        "appointment", "availability", "available", "catch up", "zoom",
        # Phrases, not the bare word "chat", so "live chat" is not a meeting.
        "a chat", "quick chat", "set up a time",
    ),
    "support_question": (
        "help", "how do i", "how can i", "question", "issue", "problem",
        "error", "not working", "doesn't work", "does not work", "can't log",
        "cannot log", "unable to", "password", "support",
    ),
    "job_application": (
        # No "interview": scheduling an interview is a meeting_request.
        "apply", "applying", "application", "resume", "cv", "job",
        "position", "role", "vacancy", "opening", "hiring",
    ),
    "complaint": (
        # No "refund": a refund demand alone is not evidence of a complaint.
        "complaint", "complain", "disappointed", "unacceptable", "frustrated",
        "angry", "terrible", "awful", "worst", "unhappy", "not happy", "rude",
        "still waiting", "hasn't arrived", "never arrived", "damaged",
    ),
    "status_update": (
        "update", "fyi", "for your information", "progress", "completed",
        "finished", "on track", "status", "heads up", "just letting you know",
    ),
    "thank_you": (
        "thank you", "thanks", "appreciate", "appreciated", "grateful",
    ),
}

# Compile each keyword once. \b means "word boundary", so "cv" does not
# match inside "cvs" and "call" does not match inside "recall".
_PATTERNS = {
    category: [(word, re.compile(rf"\b{re.escape(word)}\b")) for word in words]
    for category, words in KEYWORDS.items()
}

# Phrases that contain a keyword but are not evidence for its category.
# They are blanked out before that category's keywords are searched.
_NOT_EVIDENCE = {
    # "Thanks so much for your help": the help is being thanked for, not
    # asked for. "Thanks, but I still need help" is not matched.
    "support_question": re.compile(
        r"\b(?:thanks|thank you)(?:\W+\w+){0,4}?\W+for (?:all )?(?:your|the) help\b"
    ),
    # "Can you give me an update?": an update is requested, not shared.
    "status_update": re.compile(
        r"\b(?:give|send|get|provide) (?:me|us) (?:an |any )?update\b"
        r"|\bany update\b|\bupdate (?:me|us)\b"
    ),
}

# Split after . ? or ! followed by spaces, or at any line break.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text):
    """Split text into trimmed, non-empty sentences, in order."""
    text = text.replace("’", "'")  # curly apostrophe -> straight
    return [part.strip() for part in _SENTENCE_BREAK.split(text) if part.strip()]


def find_matches(sentence, location):
    """Return a KeywordMatch for every keyword found in `sentence`."""
    lowered = " ".join(sentence.lower().split())
    matches = []
    for category, patterns in _PATTERNS.items():
        text = lowered
        if category in _NOT_EVIDENCE:
            text = _NOT_EVIDENCE[category].sub(" ", text)
        for word, pattern in patterns:
            if pattern.search(text):
                matches.append(KeywordMatch(category, word, location, sentence))
    return matches


def classify(message):
    """Return the Classification for one Message."""
    if not message.subject.strip() and not message.body.strip():
        return Classification(message.id, OTHER, (), ("empty",), ())

    sentences = [
        find_matches(sentence, location)
        for location, text in (("subject", message.subject), ("body", message.body))
        for sentence in split_sentences(text)
    ]
    all_matches = [match for matches in sentences for match in matches]

    # Courtesy thanks: if anything other than thanks was found, thanks is
    # politeness, not an intent. It stays in `matches` as evidence but is
    # never chosen as primary or secondary.
    found = {match.category for match in all_matches}
    courtesy_thanks = THANKS in found and len(found) > 1

    def counted(matches):
        return [m for m in matches if not (courtesy_thanks and m.category == THANKS)]

    primary = None
    for matches in sentences:
        categories = {match.category for match in counted(matches)}
        if len(categories) == 1:
            primary = categories.pop()  # first clear request
            break
        if len(categories) > 1:
            break  # ambiguous sentence comes first

    flags = []
    if primary is None:
        primary = OTHER
        flags.append("unclear")

    # Every other category found, in the order it first appeared.
    secondary = []
    for match in counted(all_matches):
        if match.category != primary and match.category not in secondary:
            secondary.append(match.category)
    if secondary:
        flags.append("multiple_intents")

    return Classification(
        message.id, primary, tuple(secondary), tuple(flags), tuple(all_matches)
    )
