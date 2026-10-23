"""Checks that the evaluation arithmetic is right, using hand-made results.

These tests never run the real classifier on the evaluation data, so they
do not depend on (or assert anything about) how accurate it is.
"""

from inbox_helper.evaluate import (
    ABSTAINED,
    ACCEPTABLE,
    CONFIDENT_WRONG,
    CORRECT,
    DEFINITE,
    EXACT,
    INCORRECT,
    SENT_TO_REVIEW,
    LabelledCase,
    format_report,
    outcome,
    pct,
    summarize,
    unexpected_secondary,
)
from inbox_helper.models import Classification, Message


def case(expected, acceptable=(), secondary=(), tags=()):
    return LabelledCase(
        message=Message("x", "s", "", "body"),
        expected_primary=expected,
        expected_secondary=tuple(secondary),
        acceptable_primary=tuple(acceptable),
        tags=tuple(tags),
        label_status="ai_proposed",
        rationale="r",
    )


def result(primary, secondary=(), flags=()):
    return Classification("x", primary, tuple(secondary), tuple(flags), ())


def test_outcome_buckets():
    assert outcome(case("complaint"), result("complaint")) == CORRECT
    assert outcome(case("complaint", acceptable=["support_question"]),
                   result("support_question")) == ACCEPTABLE
    assert outcome(case("complaint"), result("other_or_unclear")) == SENT_TO_REVIEW
    assert outcome(case("complaint"), result("thank_you")) == CONFIDENT_WRONG
    # Expecting other_or_unclear but getting a real category is confidently wrong.
    assert outcome(case("other_or_unclear"), result("complaint")) == CONFIDENT_WRONG


def test_unexpected_secondary_ignores_expected_ones():
    c = case("meeting_request", secondary=["support_question"])
    r = result("meeting_request", secondary=["support_question", "thank_you"])

    assert unexpected_secondary(c, r) == ("thank_you",)


def test_summarize_counts():
    cases = [
        case("complaint"),                                   # correct
        case("complaint", acceptable=["support_question"]),  # acceptable
        case("meeting_request", secondary=["thank_you"]),    # sent to review
        case("other_or_unclear", tags=["empty"]),            # correct abstention
        case("thank_you"),                                   # confidently wrong
    ]
    results = [
        result("complaint"),
        result("support_question"),
        result("other_or_unclear", secondary=["thank_you"], flags=["unclear"]),
        result("other_or_unclear", flags=["empty"]),
        result("support_question"),
    ]

    s = summarize(cases, results)

    assert s["counts"] == {CORRECT: 2, ACCEPTABLE: 1, SENT_TO_REVIEW: 1, CONFIDENT_WRONG: 1}
    assert s["majority_label"] == "complaint"
    assert s["majority_hits"] == 2
    assert s["table"] == {
        (EXACT, DEFINITE): 1, (EXACT, ABSTAINED): 1,
        (ACCEPTABLE, DEFINITE): 1,
        (INCORRECT, DEFINITE): 1, (INCORRECT, ABSTAINED): 1,
    }
    assert (s["definite_n"], s["abstained_n"]) == (3, 2)
    assert (s["secondary_total"], s["secondary_found"]) == (1, 1)
    assert (s["empty_n"], s["empty_flagged"]) == (1, 1)
    assert s["per_category"]["support_question"] == (0, 2, 0)
    assert s["per_category"]["complaint"] == (2, 1, 1)


def test_pct_formats_counts_and_handles_zero():
    assert pct(1, 3) == "1/3 (33.3%)"
    assert pct(0, 0) == "0/0 (n/a)"


# --- Regression: abstentions that match an acceptable alternative ---------
# The first baseline report listed 8 abstentions on the test set but only
# explained 7 of them (3 expected + 4 "sent to review"). The missing one
# (test-18) was an abstention that matched an acceptable alternative.


def acceptable_abstention_example():
    cases = [
        case("status_update", acceptable=["other_or_unclear"]),  # like test-18
        case("other_or_unclear"),                               # correct abstention
        case("meeting_request"),                                # sent to review
        case("complaint"),                                      # exact definite
        case("thank_you"),                                      # confidently wrong
    ]
    results = [
        result("other_or_unclear", flags=["unclear"]),
        result("other_or_unclear", flags=["unclear"]),
        result("other_or_unclear", flags=["unclear"]),
        result("complaint"),
        result("support_question"),
    ]
    return cases, results


def test_acceptable_abstention_is_counted_as_an_abstention():
    s = summarize(*acceptable_abstention_example())

    assert s["table"][ACCEPTABLE, ABSTAINED] == 1
    assert s["abstained_n"] == 3
    # Every abstention is explained by exactly one row.
    assert s["abstained_n"] == (
        s["table"][EXACT, ABSTAINED]
        + s["table"][ACCEPTABLE, ABSTAINED]
        + s["table"][INCORRECT, ABSTAINED]
    )


def test_reconciliation_table_adds_up_to_message_count():
    cases, results = acceptable_abstention_example()
    s = summarize(cases, results)

    assert sum(s["table"].values()) == len(cases)
    assert s["definite_n"] + s["abstained_n"] == len(cases)


def test_report_shows_reconciled_counts_and_both_strict_definitions():
    report = format_report("example.csv", *acceptable_abstention_example())

    assert "| Exact match | 1 | 1 | 2 |" in report
    assert "| Acceptable alternative | 0 | 1 | 1 |" in report
    assert "| Incorrect | 1 | 1 | 2 |" in report
    assert "| **Total** | 2 | 3 | 5 |" in report
    # Strict counts the expected abstention; the stricter version does not.
    assert "only when `other_or_unclear` was expected) | 2/5 (40.0%) |" in report
    assert "| Strict accuracy, every abstention incorrect | exact definite / all messages | 1/5 (20.0%) |" in report
    assert "| Accuracy among definite (exact) | exact definite / definite | 1/2 (50.0%) |" in report
