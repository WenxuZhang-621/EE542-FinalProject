# ingest/ — P1

Gmail → `EmailMessage` JSON.

Week 1:
- Day 2–3: Google Cloud project, Gmail API OAuth (test mode), fetch last 50 messages
- Day 3–4: parse MIME, HTML→text, download attachments
- Day 4–5: PDF text via pdfplumber, Excel via openpyxl
- Day 5–6: `python ingest/fetch_emails.py --since 7d --out data/emails.json`
- Day 6–7: integration; seed test inbox with the 20 sample emails

Setup: create OAuth client (Desktop app) in Google Cloud, download as `credentials.json`
at repo root. First run opens a browser for consent and writes `token.json`.
