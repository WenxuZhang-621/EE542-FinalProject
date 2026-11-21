# agent/ — the expediter clone

The digital clone of a senior expediter: it knows the buyer playbook, searches the
supplier's emails, and drafts follow-ups for the buyer to approve. Nothing is ever sent.

| File | What it does |
|---|---|
| `buyer_playbook.md` | The expert rules §1–§8, each a paraphrase of public procurement guidance with its sources |
| `style_samples/` | Four sample follow-ups (three English, one Chinese) used as tone examples |
| `playbook.py` | Parses the playbook; `load_playbook(conn)` also returns the company rules users uploaded |
| `uploads.py` | Company rules: preview pasted text, save reviewed rules as U1, U2…, enable, edit, delete |
| `draft.py` | `draft_followup(conn, po_number) -> FollowUpDraft` |
| `tools.py` | The five tools the chat model can call |
| `chat.py` | `chat(conn, messages)`: the tool-calling loop behind `POST /api/chat` |
| `compare.py` | The same questions to a generic model and to the clone, side by side |
| `llm.py` | The chat model client, configured like `extract/` (`LLM_*` in `.env`) |

## Drafting a follow-up

```python
from agent.draft import draft_followup, DraftError, NoExceptionError

draft = draft_followup(conn, "PO-M2-0001", buyer_name="Alice Chen")
draft.subject, draft.body, draft.why, draft.rule_ids, draft.email_ids
```

```bash
python agent/draft.py PO-M2-0001 --buyer "Alice Chen"    # prints the draft as JSON
```

What the model gets:

1. The order and its open exceptions, and up to three emails about this PO, latest first,
   with quoted earlier messages removed.
2. Up to five of this supplier's other emails, found with `rag.search_emails`.
3. The playbook rules tagged for these exceptions, plus the three closest rules by meaning.
   Uploaded company rules are marked `[company]` and override the public guidance.
4. One sample follow-up for tone, and a reply-by date two business days from today.

How the answer is checked:

- Rule ids and email refs the model cites must come from that material; others are dropped.
- A draft without a body or without any rule citation is requested once more.
- The PO number is added to the subject if missing; replies get `Re:` and the original thread.
- The language follows the supplier's latest email (Chinese or English).

Errors: `NoExceptionError` when the PO has nothing to follow up on (the API should answer
409), `DraftError` when the PO is unknown or the model fails twice. If embeddings are not
available, the draft is still written, without the supplier history.

The signature comes from `buyer_name`, else `BUYER_NAME` in `.env`, else "Purchasing team".

## Chat ("Ask the expediter")

```bash
python agent/chat.py "Which orders are at risk this week?"
```

`POST /api/chat` with `{"messages": [{"role": "user", "content": "..."}], "buyerName": "..."}`
returns `{answer, toolsUsed, sources, drafts}`. The page sends the whole conversation; the
backend keeps no chat state and uses the last 10 messages.

| Tool | What it returns |
|---|---|
| `list_exceptions(kind?)` | Open problems, most urgent first, with counts per kind |
| `get_po(po_number)` | Ordered terms, the supplier's latest terms, problems, change history, latest emails |
| `search_emails(query, supplier?, po_number?)` | RAG search over the stored supplier emails |
| `search_playbook(query, kind?)` | The closest playbook rules; a query naming a PO uses that PO's problem |
| `draft_followup(po_number)` | A follow-up draft for review; the answer only summarizes it |

- At most five rounds of tool calls; then the model answers with what it found.
- Every email and rule in a tool result carries a ref (`E1`, `R3`). The model cites refs;
  `sources` lists the cited emails and rules, and the text shows them as "(§3)" or
  "(email of Nov 10)". Refs the tools never returned are dropped.
- The answer is in the language of the question (detected in code), as plain text.
- Tool errors (unknown PO, search unavailable) go back to the model, which says it could
  not find the answer. Only `draft_followup` creates anything, and it never sends email.
- `on_draft` lets the API store drafts made in chat (for the Follow-ups page) once the
  drafts table exists.

## Company rules (Playbook page → Add your rules)

1. The buyer pastes a policy or uploads a `.md` / `.txt` file.
2. `POST /api/playbook/preview` splits it into rules without saving: text already in the
   playbook format is parsed as is, other text is split by the model, and without a model by
   bullets and lines (headings are skipped). Problem kinds are guessed from keywords.
3. The buyer edits titles, text and problem kinds, removes rules, and saves:
   `POST /api/playbook/rules` stores them as U1, U2… (numbers are never reused).
4. Enabled rules join the playbook. Drafts and chat mark them `[company]`, apply them when their
   condition matches the order, and cite them as "Your rule U1"; they win over the expert rules.

Limits: 50,000 characters per upload, 50 rules, 1,000 characters per rule. Uploaded text is
reference material for the model, never instructions, and no tool can send email.
`PATCH` / `DELETE /api/playbook/rules/{id}` switch, edit or remove an uploaded rule; the
built-in §1–§8 are read-only.

## Generic model vs the clone

```bash
python agent/compare.py                        # three questions about the M2 demo orders
python agent/compare.py "Your question" ...    # your own questions
```

The generic model gets only the question (no tools, orders, emails or playbook); the clone
is the chat above. Both use the model in `.env`. The result is printed and saved as
`data/compare_<date>.md` (git-ignored), ready to show or record.

## Tests

`python -m pytest tests/test_draft.py tests/test_chat.py tests/test_compare.py tests/test_playbook.py tests/test_uploads.py` runs offline:
a fake model returns scripted answers and tool calls, and word-hash vectors stand in for
embeddings.
