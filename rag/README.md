# rag/ — retrieval for the expediter clone

Finds the supplier emails and playbook rules that the clone needs when it drafts a
follow-up or answers a question.

- `embed.py` turns text into vectors through any OpenAI-compatible `/v1/embeddings`
  endpoint (`EMBED_BASE_URL`, `EMBED_MODEL`, `EMBED_API_KEY` in `.env`).
- `index.py` chunks the stored emails, keeps their vectors in `data/po.sqlite`
  (tables `rag_chunks` and `rag_rules`), and searches them.

## How it works

- **Source:** the emails the pipeline already stored (`email_messages`), not Gmail directly.
  Only emails about tracked orders are indexed: from a supplier address in the PO list, or
  mentioning a tracked PO. Newsletters and personal mail are never embedded, so they are
  never sent to the embedding service. With an empty PO list nothing is indexed.
- **Chunks:** each email body becomes one chunk of about 500 tokens (longer bodies are
  split by paragraph), with quoted earlier messages removed. Each attachment with text
  becomes its own chunk. Every chunk starts with From / Date / Subject.
- **Self-updating:** each search first embeds new or changed emails and drops chunks of
  emails that are gone, so `/api/sync` needs no extra call. Changing `EMBED_MODEL` or
  `EMBED_BASE_URL` re-embeds everything.
- **Vectors:** unit-length float32 in SQLite; cosine similarity with numpy. A few hundred
  emails take milliseconds, so there is no vector database.

## API

```python
from rag.index import search_emails, search_playbook

search_emails(conn, "late shipment", supplier="Alder Components", po_number=None, k=5)
# -> [{email_id, date, from, subject, po_numbers, snippet, score}], best chunk per email

search_playbook(conn, "supplier raised the price", kind="price_change", k=3)
# -> [{id, title, text, kinds, source, checked, origin, score}]
```

- `supplier` can be a name, an address or a domain. An email belongs to the supplier if it
  comes from the supplier's address in the PO list or mentions one of the supplier's POs.
  An address shared by several suppliers (one test account playing every supplier) only
  counts through the PO mentions.
- `po_number` keeps only emails that mention that PO (`PO-1001` is not `PO-100`).
- A query that names a PO ranks emails about that PO higher.

## Command line

```bash
python rag/index.py build
python rag/index.py search "factory holiday" --supplier sales@alder.example.com
python rag/index.py playbook "the supplier raised the price" --kind price_change
```

## Models

| Where | `.env` |
|---|---|
| Development (default) | `EMBED_MODEL=text-embedding-3-small`, `EMBED_BASE_URL` empty (OpenAI, uses `LLM_API_KEY`) |
| Our GPU (bge-m3 through the tunnel) | `EMBED_BASE_URL=http://localhost:8002/v1`, `EMBED_MODEL=BAAI/bge-m3` |
| Offline, no key | `EMBED_MODEL=hashing` (word-hash vectors; tests use this) |

With OpenAI, email text is sent to OpenAI for embedding, the same as for extraction.

## Tests

`python -m pytest tests/test_rag.py tests/test_playbook.py` runs offline with word-hash vectors.
