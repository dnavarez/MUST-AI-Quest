# Inbox Helper approved replies

**NOT SENT.** Nothing in this file has been sent, and this tool cannot send messages. Every reply below has status `approved_unsent`. To send one, copy it into your own email tool and send it yourself.

- Input file: `messages.csv`
- Input SHA-256: `2575b60e9b5a358a88e7d240b7221300e89b53525c2aecc3a3d827a2bc5a38ae`
- Review file: `review.csv`
- Review file SHA-256: `afdad854117b066bd8948863a20924c77e4cc5e32dcc4bec31d30587c78a8883`
- Messages: 12; approved: 3; edited: 2; rejected: 2; pending: 5

Message and reviewer text is untrusted. It is shown inside code blocks as plain text, with invisible characters shown as `[U+XXXX]`; copy replies from the CSV file, not from this report. A `'` at the start of a CSV cell was added to stop spreadsheets running it as a formula; it is not part of the reply, so remove it when copying.

## Pending, not finalized (5)

- `demo-04`
- `demo-05`
- `demo-07`
- `demo-10`
- `demo-12`

## Rejected (2)

- `demo-09`
- `demo-11`

## Replies to send manually (5)

### Message `demo-01`

- Decision: `approve`
- Sender: `Priya Shah <priya@example.com>`
- Primary intent: `meeting_request`

**Warnings**

- None

**Reply warnings** (not blocking; check before sending)

- `unresolved placeholder: [NAME]`
- `unresolved placeholder: [CONFIRM AVAILABILITY OR PROPOSE A TIME]`
- `unresolved placeholder: [YOUR NAME]`

**Reviewer note**

(none)

**Final reply (not sent)**

```text
Hello [NAME],

Thank you for your message about arranging a time to talk. [CONFIRM AVAILABILITY OR PROPOSE A TIME]

Best regards,
[YOUR NAME]
```

---

### Message `demo-02`

- Decision: `edit`
- Sender: `Tom Reyes <tom@example.com>`
- Primary intent: `support_question`

**Warnings**

- None

**Reply warnings** (not blocking; check before sending)

- `unresolved placeholder: [YOUR NAME]`

**Reviewer note**

```text
Filled in the name and the answer; sign with my own name before sending.
```

**Final reply (not sent)**

```text
Hello Tom,

Thank you for getting in touch. You can change the email address on your account from your account settings page. If that does not work, just reply to this message.

Best regards,
[YOUR NAME]
```

**AI draft before editing**

```text
Hello [NAME],

Thank you for getting in touch. To help with your request, could you share [DETAILS NEEDED, e.g. account or order reference]? [ANSWER OR NEXT STEP]

Best regards,
[YOUR NAME]
```

---

### Message `demo-03`

- Decision: `approve`
- Sender: `Lena Fischer <lena@example.com>`
- Primary intent: `job_application`

**Warnings**

- None

**Reply warnings** (not blocking; check before sending)

- `unresolved placeholder: [NAME]`
- `unresolved placeholder: [RESPONSE ABOUT THE ROLE AND HIRING PROCESS]`
- `unresolved placeholder: [YOUR NAME]`

**Reviewer note**

(none)

**Final reply (not sent)**

```text
Hello [NAME],

Thank you for your interest in a role with us. [RESPONSE ABOUT THE ROLE AND HIRING PROCESS]

Best regards,
[YOUR NAME]
```

---

### Message `demo-06`

- Decision: `approve`
- Sender: `Ben Okafor <ben@example.com>`
- Primary intent: `thank_you`

**Warnings**

- None

**Reply warnings** (not blocking; check before sending)

- `unresolved placeholder: [NAME]`
- `unresolved placeholder: [OPTIONAL PERSONAL NOTE]`
- `unresolved placeholder: [YOUR NAME]`

**Reviewer note**

(none)

**Final reply (not sent)**

```text
Hello [NAME],

Thank you for your kind message. [OPTIONAL PERSONAL NOTE]

Best regards,
[YOUR NAME]
```

---

### Message `demo-08`

- Decision: `edit`
- Sender: `Chen Wei <chen@example.com>`
- Primary intent: `meeting_request`

**Warnings**

- ⚠ Multiple intents: the message seems to ask for more than one thing. Check that the reply covers all of them.

**Reply warnings** (not blocking; check before sending)

- `unresolved placeholder: [YOUR NAME]`
- `contains commitment or approval wording: 'i will'`

**Reviewer note**

```text
Answered both parts of the message.
```

**Final reply (not sent)**

```text
Hello Chen,

Thank you for your message. Tuesday at 3pm works for me, and I will send a calendar invitation. Regarding the login problem: please try resetting your password from the sign-in page, and let me know if that does not help.

Best regards,
[YOUR NAME]
```

**AI draft before editing**

```text
Hello [NAME],

Thank you for your message about arranging a time to talk. [CONFIRM AVAILABILITY OR PROPOSE A TIME] Regarding your question: [ANSWER OR NEXT STEP]

Best regards,
[YOUR NAME]
```

---
