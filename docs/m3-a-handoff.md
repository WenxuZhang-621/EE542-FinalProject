# M3 A: imported baselines, supplier inbox, and Gmail drafts

Based on main `4078abe`, including B's committed `FollowUpDraft`, RAG, playbook and chat.

## Integration contracts

- `purchase_orders.in_po_list`: 1 only after a PO-list import, 0 for email-created rows.
  Existing databases migrate automatically. Legacy rows with import-only contact/date
  fields are retained as imported; other rows require a PO-list import.
- `ingest.po_import.import_po_list(file, conn=...)` is the sole CSV/XLSX importer.
  The API returns `new`, `tracked`, `errors`, `missing_columns`, plus a new `completed`
  array. Imported terms are immutable on repeat imports. Completion fills the original
  terms while preserving supplier-confirmed values and source email history.
- `rules.sync_exceptions` evaluates only imported POs. New supplier claims cannot
  replace the ordered price, quantity or requested date. `/api/orders` returns
  `status: "unmatched"` and `inPoList: false` for email-only POs. They are not exceptions.
- `fetch(since, supplier_emails=..., ...)` intersects the sender allowlist with the
  user's query, excludes sent/draft messages, paginates, batches contacts and caps the
  combined result at 50 by default. Without an explicit list, contacts come from the
  configured database. An empty list never contacts Gmail. The live API returns 409,
  `Import your PO list first`, before Gmail access when there are no imported contacts.
- `save_draft(draft: FollowUpDraft, *, conn=None, db_path=None) -> str` is ready for
  C's approve endpoint. It resolves `reply_to_email_id` through `mailbox_messages`,
  verifies the connected account, retrieves the actual Message-ID/References/thread,
  and calls only `drafts.create`. It preserves the parent subject for Gmail threading.
  C must persist the returned ID and `state="saved"` after approval and serialize
  repeated approval requests. The create call has no automatic HTTP retries; after
  an ambiguous network failure check Gmail Drafts before retrying.
- Drafts with no source email (for example a no-reply PO), disconnected source accounts,
  unmatched POs or a different supplier recipient fail explicitly. There is no fallback
  to the current default mailbox. A separate no-reply drafting policy is future work.

## Gmail authorization

The CLI and web OAuth flow share `gmail.readonly` and `gmail.compose`. Old read-only
tokens are shown as unauthorized and require reconnecting. Saved scopes are checked
as granted, rather than replaced with requested scopes during token loading.
Google's compose permission includes sending; this application's draft module never
calls a sending endpoint. Tokens and live emails stay local and ignored by Git.

References: [Gmail drafts](https://developers.google.com/workspace/gmail/api/guides/drafts),
[reply threading](https://developers.google.com/workspace/gmail/api/guides/threads),
[credential scopes](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.credentials.html).

## C's remaining integration work

Implement the planned drafts table and draft/list/approve/reject endpoints, call
`save_draft` only after explicit buyer approval, and connect the Follow-ups page.
The current approve handler in the UI still only changes local demo state; this A
change does not claim that C's end-to-end approval UI is complete. Add the empty-list
import action and a dedicated unmatched-orders section. Minimal frontend compatibility
for the new status, import completion and truthful OAuth copy is included here.

## Reproducible checks and demo data

```bash
python -m pytest -q
python ingest/check_m2.py
python ingest/make_m3_history.py
python ingest/po_import.py tests/samples/m3_history/po_list.csv --db data/m3-demo.sqlite
```

`tests/test_m3_ingestion.py` verifies both processing orders produce the same complete
exception rows, migration, imported-contact filtering, batching, and the 15-email
history fixture reaching B's RAG/draft code without mixing suppliers sharing a sender.
`tests/test_gmail_drafts.py` verifies original-account routing, threading headers,
recipient validation, disconnected accounts, rejected drafts, and no sending.
The two overlong parametrized test IDs in the baseline Windows suite were replaced
with short readable IDs without changing the assertions.

Live acceptance is recorded separately from offline assertions. Real Gmail reception
and draft persistence do not by themselves establish LLM extraction accuracy. The
M3 fixture reference answers are used to isolate A's storage/rule behavior.

## Acceptance recorded on 2026-11-21

- Python suite: 166 tests passed. Frontend TypeScript: `tsc --noEmit` passed.
- M2 regression replay: 40 imported POs, 10 messages, all seven expected exceptions.
- Live Gmail: all 15 authorized fictional messages arrived in the controlled test
  inbox and their bodies matched the fixtures. The six matching imported POs produced
  one delay, one price-change and one stockout after replaying the labelled extractions.
- One explicitly approved TEST draft was saved in the receiving account and original
  Gmail thread. Its labels included `DRAFT` and excluded `SENT`; it was not sent.
- This live run used a separate local database and authorization store. No production
  deployment or existing team database was modified. Raw emails, account addresses,
  OAuth files and Gmail IDs are retained locally and are not committed.
- Sender filtering and RAG attribution with a shared demo sender have offline tests.
  The live run used an additional `subject:M3-DEMO` filter; it is not a claim of a
  separate live experiment with unrelated senders or of live LLM extraction accuracy.
