# Frozen test checkpoint after C1–C5 tuning — 2026-10-23

Generated once by: `PYTHONPATH=src .venv/bin/python -m inbox_helper.evaluate data/eval_test.csv`

Classifier: after the approved C1–C5 changes (classifier.py MD5 `855131003c9a432aeef8874eab620cac`), chosen using the dev set only. Test set: frozen `data/eval_test.csv` (SHA-256 `b74fe9fb2a3ef8fa77f58c1e7e84bbf1f6d370e13907b92a90dc20d9a3e5526c`), human-reviewed labels. This is the one-time checkpoint; no changes are to be made based on it. Compare with the test section of `docs/eval_post_review_2026-10-23.md` (untuned classifier). Preliminary: rules, messages and first labels were produced with AI assistance, labels were human-reviewed with AI assistance, and the AI had seen the test messages earlier in the session.

## Evaluation: `data/eval_test.csv`

- Messages: 24
- Label status: human_reviewed=24

### Where every message landed

A *definite* prediction is one of the six real categories. An
*abstention* is a prediction of `other_or_unclear`. Each message is
in exactly one cell, so rows and columns add up to the totals.

| Outcome | Definite | Abstention | Total |
|---|---|---|---|
| Exact match | 12 | 2 | 14 |
| Acceptable alternative | 1 | 1 | 2 |
| Incorrect | 4 | 4 | 8 |
| **Total** | 17 | 7 | 24 |

- An incorrect definite prediction is *confidently wrong*.
- An incorrect abstention is *sent to review*: a real intent was
  expected and `other_or_unclear` was not an acceptable alternative.

### Primary-intent metrics

| Metric | Numerator / denominator | Result |
|---|---|---|
| Strict accuracy | exact matches / all messages (an abstention counts only when `other_or_unclear` was expected) | 14/24 (58.3%) |
| Lenient accuracy | (exact + acceptable) / all messages | 16/24 (66.7%) |
| Strict accuracy, every abstention incorrect | exact definite / all messages | 12/24 (50.0%) |
| Majority baseline (always `support_question`) | messages expecting that label / all messages | 6/24 (25.0%) |
| Confidently wrong | incorrect definite / all messages | 4/24 (16.7%) |
| Sent to review | incorrect abstentions / all messages | 4/24 (16.7%) |
| Abstention rate | abstentions / all messages | 7/24 (29.2%) |
| Accuracy among definite (exact) | exact definite / definite | 12/17 (70.6%) |
| Accuracy among definite (lenient) | (exact + acceptable) definite / definite | 13/17 (76.5%) |
| Empty messages flagged `empty` | flagged / messages tagged `empty` | 1/1 (100.0%) |

### Per category (strict)

| Category | Expected | Predicted | Correct | Recall | Precision |
|---|---|---|---|---|---|
| `meeting_request` | 4 | 4 | 3 | 3/4 (75.0%) | 3/4 (75.0%) |
| `support_question` | 6 | 2 | 1 | 1/6 (16.7%) | 1/2 (50.0%) |
| `job_application` | 2 | 3 | 2 | 2/2 (100.0%) | 2/3 (66.7%) |
| `complaint` | 3 | 3 | 3 | 3/3 (100.0%) | 3/3 (100.0%) |
| `status_update` | 5 | 2 | 2 | 2/5 (40.0%) | 2/2 (100.0%) |
| `thank_you` | 2 | 3 | 1 | 1/2 (50.0%) | 1/3 (33.3%) |
| `other_or_unclear` | 2 | 7 | 2 | 2/2 (100.0%) | 2/7 (28.6%) |

### Secondary intents

- Expected secondary intents found: 1/2 (50.0%)
- Messages with unexpected secondary intents: 3/24 (12.5%) (of which include `thank_you`: 0)

### By case tag (a message can have several tags)

| Tag | Messages | Correct/acceptable | Sent to review | Confidently wrong |
|---|---|---|---|---|
| `debatable` | 5 | 3 | 2 | 0 |
| `easy` | 8 | 8 | 0 | 0 |
| `empty` | 1 | 1 | 0 | 0 |
| `interview` | 1 | 1 | 0 | 0 |
| `misleading_keyword` | 4 | 1 | 1 | 2 |
| `multi_intent` | 2 | 0 | 1 | 1 |
| `no_keyword` | 4 | 1 | 1 | 2 |
| `override` | 2 | 2 | 0 | 0 |
| `signoff` | 4 | 3 | 0 | 1 |
| `software_application` | 1 | 0 | 1 | 0 |
| `vague` | 1 | 1 | 0 | 0 |

### Messages not exactly correct

| Id | Outcome | Expected | Got | Flags | Message |
|---|---|---|---|---|---|
| test-08 | acceptable | `support_question` | `other_or_unclear` | unclear | [?] Hi, is this the right address? |
| test-10 | confident_wrong | `support_question` | `thank_you` | - | Where can I download last month's invoice? Many thanks, Priya |
| test-11 | sent_to_review | `support_question` | `other_or_unclear` | unclear, multiple_intents | [Login error in the mobile application] Every time I open the appli... |
| test-12 | confident_wrong | `support_question` | `job_application` | - | Our team's application for the grant was rejected and we'd like to ... |
| test-14 | confident_wrong | `support_question` | `meeting_request` | - | Can you check why the invoice total is different from the quote? Se... |
| test-15 | sent_to_review | `status_update` | `other_or_unclear` | unclear, multiple_intents | [Update and a question] Quick update: the samples arrived today. Ho... |
| test-18 | sent_to_review | `status_update` | `other_or_unclear` | unclear, multiple_intents | No need to call me back, the problem was solved on my end. |
| test-20 | sent_to_review | `meeting_request` | `other_or_unclear` | unclear | Do you have 15 minutes on Thursday to go through the contract? |
| test-21 | confident_wrong | `thank_you` | `support_question` | - | [Great support] Your colleague Sam went above and beyond to fix my ... |
| test-24 | acceptable | `status_update` | `thank_you` | - | [Re: your order] Received it today, thanks! |

### Unexpected secondary intents

| Id | Unexpected | Message |
|---|---|---|
| test-11 | job_application | [Login error in the mobile application] Every time I open the appli... |
| test-18 | meeting_request, support_question | No need to call me back, the problem was solved on my end. |
| test-22 | support_question | [FYI] The client asked a question about pricing, which I've already... |

