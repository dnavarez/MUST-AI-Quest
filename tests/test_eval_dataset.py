"""Checks that the evaluation CSV files are well-formed.

These tests check the data, not the classifier: they never compare
predictions with labels.
"""

from pathlib import Path

import pytest

from inbox_helper.evaluate import CATEGORIES, load_labelled

DATA = Path(__file__).resolve().parent.parent / "data"
FILES = {"dev": DATA / "eval_dev.csv", "test": DATA / "eval_test.csv"}
KNOWN_TAGS = {
    "easy", "empty", "vague", "no_keyword", "signoff", "misleading_keyword",
    "software_application", "interview", "multi_intent", "override", "overlap",
    "debatable",
}


@pytest.mark.parametrize("split", ["dev", "test"])
def test_labels_are_valid(split):
    for c in load_labelled(FILES[split]):
        assert c.message.id.startswith(f"{split}-")
        assert c.expected_primary in CATEGORIES
        assert set(c.expected_secondary) <= set(CATEGORIES)
        assert set(c.acceptable_primary) <= set(CATEGORIES)
        assert c.expected_primary not in c.acceptable_primary
        assert set(c.tags) <= KNOWN_TAGS and c.tags
        assert c.label_status in {"ai_proposed", "human_reviewed"}
        assert c.rationale


@pytest.mark.parametrize("split", ["dev", "test"])
def test_every_category_appears_as_expected_primary(split):
    labels = {c.expected_primary for c in load_labelled(FILES[split])}

    assert labels == set(CATEGORIES)


@pytest.mark.parametrize("split", ["dev", "test"])
def test_required_case_types_are_covered(split):
    tags = {t for c in load_labelled(FILES[split]) for t in c.tags}

    assert {"empty", "multi_intent", "signoff", "override", "interview",
            "software_application", "misleading_keyword", "debatable"} <= tags


@pytest.mark.parametrize("split", ["dev", "test"])
def test_debatable_cases_list_an_alternative_label(split):
    for c in load_labelled(FILES[split]):
        if "debatable" in c.tags:
            assert c.acceptable_primary, c.message.id


def test_dev_and_test_share_no_messages():
    dev, test = (load_labelled(FILES[s]) for s in ("dev", "test"))

    assert not {c.message.id for c in dev} & {c.message.id for c in test}
    assert not {c.message.body for c in dev if c.message.body.strip()} & {
        c.message.body for c in test if c.message.body.strip()
    }
