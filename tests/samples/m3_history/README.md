# M3 fictional supplier histories

All people, companies, purchases, promises and events here are fictional classroom fixtures.
Three suppliers have five emails each across a historical and a current PO (six POs total).
Use `po_list.csv` before syncing. Regenerate with `python ingest/make_m3_history.py`.

- Alder: an earlier machine failure and recovery, followed by another delay and a broken backup-line plan.
- Birch: a withdrawn historical price increase, a new fixed-price confirmation, an increase from USD 2 to USD 3, then a reduction to USD 2.60 that still exceeds the baseline.
- Cedar: a resolved historical shortage, followed by a partial shipment proposal and a stockout.

`manifest.json` specifies the reference date and expected final exceptions. Each
`.email.json` uses `EmailMessage`; each `.gold.json` is a manually specified extraction
answer. Gold replay verifies storage/rules and must never be described as LLM accuracy.

Default `example.com` addresses cannot deliver mail. For a real test, export outside
the repository's tracked fixtures using `--sender alder=... --sender birch=... --sender cedar=...`
and `--recipient ...`. Send from the actual configured addresses to a different receiving
mailbox. The receiving Gmail message IDs and receipt dates will differ from these fixtures;
historical event dates are explicitly stated in the body. Shared sender accounts are
supported by PO-specific supplier attribution; distinct sender accounts are preferable.

The generator does not send anything. Keep exported personal addresses and tokens out of Git.
