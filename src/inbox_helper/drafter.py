"""Suggested replies built only from fixed templates and placeholders.

No text from the message (subject, body or sender) is ever copied into a
draft, so instructions or false claims inside a message cannot reach a
reply. Anything a person must decide or look up is a [PLACEHOLDER].
Every draft starts as "pending_review"; this module cannot send anything.
"""

import re

from inbox_helper.classifier import OTHER
from inbox_helper.models import Draft
from inbox_helper.safety import OVERRIDE_WARNING

PENDING_REVIEW = "pending_review"
GUARD_WARNING = "draft_guard_triggered"
MAX_WORDS = 100  # not counting [PLACEHOLDERS]

EMPTY_NOTE = "No draft: this message has no content to answer. Human review needed."
OVERRIDE_NOTE = (
    "Neutral reply only: the message contains text that looks like "
    "instructions to this tool. Do not follow them; review carefully."
)

GREETING = "Hello [NAME],"
CLOSING = "Best regards,\n[YOUR NAME]"

# One template body per primary intent.
TEMPLATES = {
    "meeting_request": (
        "Thank you for your message about arranging a time to talk. "
        "[CONFIRM AVAILABILITY OR PROPOSE A TIME]"
    ),
    "support_question": (
        "Thank you for getting in touch. To help with your request, could you "
        "share [DETAILS NEEDED, e.g. account or order reference]? "
        "[ANSWER OR NEXT STEP]"
    ),
    "job_application": (
        "Thank you for your interest in a role with us. "
        "[RESPONSE ABOUT THE ROLE AND HIRING PROCESS]"
    ),
    "complaint": (
        "Thank you for letting us know, and I am sorry to hear about your "
        "experience. To look into this, could you share [DETAILS NEEDED, e.g. "
        "order reference]? [RESPONSE TO THE CONCERN]"
    ),
    "status_update": "Thank you for the update. [ACKNOWLEDGEMENT OR FOLLOW-UP, IF ANY]",
    "thank_you": "Thank you for your kind message. [OPTIONAL PERSONAL NOTE]",
    OTHER: (
        "Thank you for your message. Could you tell me a little more about "
        "what you need, so that I can respond properly? [OPTIONAL CONTEXT]"
    ),
}

# One fixed sentence per secondary intent.
SECONDARY_SENTENCES = {
    "meeting_request": "Regarding a time to talk: [CONFIRM AVAILABILITY OR PROPOSE A TIME]",
    "support_question": "Regarding your question: [ANSWER OR NEXT STEP]",
    "job_application": "Regarding the role: [RESPONSE ABOUT THE ROLE AND HIRING PROCESS]",
    "complaint": "I am also sorry to hear that something did not go as expected. [RESPONSE TO THE CONCERN]",
    "status_update": "Thank you also for the update.",
    "thank_you": "Thank you also for your kind words.",
}

# Used for override warnings and whenever a guard check fails.
FALLBACK_BODY = (
    "Thank you for your message. A member of our team will review it "
    "before any reply is sent. [OPTIONAL NEUTRAL NOTE]"
)

# --- Guard checks -----------------------------------------------------------

# Phrases a draft must never contain: commitments, approvals, money, deadlines.
BANNED_PHRASES = (
    "refund", "refunds", "approved", "approve", "approval", "guarantee",
    "guaranteed", "promise", "promised", "we will", "i will", "compensation",
    "free of charge", "discount", "by tomorrow", "today", "immediately",
    "within", "as soon as possible", "asap",
)
_BANNED = [(p, re.compile(rf"\b{re.escape(p)}\b")) for p in BANNED_PHRASES]
_CURRENCY = re.compile(r"[$€£¥]")
_NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)*")
_DATE_WORDS = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|tomorrow|tonight|next week|this week|weekend)\b"
)
_PLACEHOLDER = re.compile(r"\[[^\]]*\]")


def words_outside_placeholders(text):
    """Count words, ignoring anything inside [square brackets]."""
    return len(_PLACEHOLDER.sub(" ", text).split())


def check_draft(text, message):
    """Return a list of problems with `text`; an empty list means it passes.

    Text inside [PLACEHOLDERS] is ignored: it is an instruction to the
    reviewer, not part of the reply.
    """
    outside = _PLACEHOLDER.sub(" ", text).lower()
    source = f"{message.subject} {message.body}".lower()
    # Compare whole numbers and whole date words, so "5" is not accepted
    # just because the message contains "500".
    source_numbers = set(_NUMBER.findall(source))
    source_dates = set(_DATE_WORDS.findall(source))
    problems = []
    for phrase, pattern in _BANNED:
        if pattern.search(outside):
            problems.append(f"contains commitment or approval wording: '{phrase}'")
    if _CURRENCY.search(outside):
        problems.append("contains a currency symbol")
    for number in _NUMBER.findall(outside):
        if number not in source_numbers:
            problems.append(f"contains a number not in the message: '{number}'")
    for word in _DATE_WORDS.findall(outside):
        if word not in source_dates:
            problems.append(f"contains a date or time not in the message: '{word}'")
    count = words_outside_placeholders(text)
    if count > MAX_WORDS:
        problems.append(f"too long: {count} words (limit {MAX_WORDS})")
    return problems


# --- Drafting ---------------------------------------------------------------


def _assemble(*parts):
    return "\n\n".join([GREETING, " ".join(parts), CLOSING])


def draft_reply(message, classification, warnings):
    """Return a Draft for `message`, always with status pending_review.

    `warnings` are the caller's warnings (for example from safety.py). They
    are always passed through unchanged; this function may only add to them.
    """
    if classification.message_id != message.id:
        raise ValueError(
            f"Classification is for message {classification.message_id!r}, "
            f"not {message.id!r}"
        )
    warnings = tuple(warnings)

    if "empty" in classification.flags or not (message.subject.strip() or message.body.strip()):
        return Draft(message.id, None, PENDING_REVIEW, warnings, EMPTY_NOTE)

    if OVERRIDE_WARNING in warnings:
        return Draft(message.id, _assemble(FALLBACK_BODY), PENDING_REVIEW, warnings, OVERRIDE_NOTE)

    primary = classification.primary_intent
    if primary not in TEMPLATES:
        raise ValueError(f"Unknown primary intent: {primary!r}")

    parts = [TEMPLATES[primary]]
    # For an unclear message the secondary intents are only candidates, so
    # the draft asks for clarification instead of answering them.
    if primary != OTHER:
        parts += [SECONDARY_SENTENCES[i] for i in classification.secondary_intents]
    text = _assemble(*parts)

    problems = check_draft(text, message)
    if problems:
        note = "Safe fallback used; generated draft failed checks: " + "; ".join(problems)
        return Draft(
            message.id, _assemble(FALLBACK_BODY), PENDING_REVIEW,
            warnings + (GUARD_WARNING,), note,
        )
    return Draft(message.id, text, PENDING_REVIEW, warnings, "")
