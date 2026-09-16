# AlexRag Ingest Schema (JSONL)
**Frozen PT:** 2026-09-15
**Source (Mac):** `/Users/n_mac/Documents/AlexRag202609/data/ingest/*.jsonl`
**Parser:** DiscordChatExporter HTML → JSONL with `title=` timestamp fix (post-merge).
**Timezone:** America/Los_Angeles (PT); every row has `tz_label: "PT"`.

## Counts (verified)

| Channel | File | Messages | missing ts | ts_inherited |
|---|---|---:|---:|---:|
| equity-trades | `equity-trades.jsonl` | 6664 | 0 | 0 |
| alex-journal | `alex-journal.jsonl` | 5471 | 0 | 1 |
| prime-report | `prime-report.jsonl` | 3062 | 0 | 1 |
| pf-update | `pf-update.jsonl` | 1428 | 0 | 2 |

## Record fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Discord snowflake = **message_id** (stable sealed-cutoff key) |
| `ts` | string (ISO8601 with offset) | Minute-precision from exporter `title=`; PT offset `-07:00`/`-08:00` |
| `author` | string | Nearly always `Alex` |
| `text` | string | Message body; may be empty when chart-only |
| `attachment_paths` | string[] | Absolute paths under DiscordArchives `*_Files/` |
| `source_type` | string | `trade_log` / `journal` / `report` / `pf_update` |
| `path` | string | Source HTML export path |
| `captions` | string[] | Usually empty in current ingest |
| `ts_inherited` | bool | True when follow-on msg inherited prior header timestamp |
| `tz_label` | string | Always `PT` |

**Not present in current JSONL:** `edited` boolean / edit history. Some equity texts still contain literal `(edited)` in the body string from the export.

## Channel ↔ source_type

| JSONL file | source_type | MVP role |
|---|---|---|
| equity-trades.jsonl | trade_log | Fills GT |
| alex-journal.jsonl | journal | Why / charts; watch post-fill rationalization |
| prime-report.jsonl | report | Evening FOCUSLIST / narrative |
| pf-update.jsonl | pf_update | Portfolio/state only (not fills) |

## Sample (one line per channel)

### equity-trades

```json
{
  "id": "1026488135485505657",
  "ts": "2022-10-03T06:37:00-07:00",
  "author": "Alex",
  "text": "long 1/2p TH @ 13.09 (SL @ 12.78)",
  "attachment_paths": [],
  "source_type": "trade_log",
  "path": "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading - Alex - 🐼equity-trades [1026453297047015474]…",
  "captions": [],
  "ts_inherited": false,
  "tz_label": "PT"
}
```

### alex-journal

```json
{
  "id": "1001129596537811094",
  "ts": "2022-07-25T07:11:00-07:00",
  "author": "Alex",
  "text": "If CELH continue to hold this 80.35$ base top level, it will be on my focus again for BORS setup with a 85.08$ confirmation pivot",
  "attachment_paths": [
    "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading%20-%20Alex%20-%20%F0%9F%8E%96alex-journal%20%5B1001126327652458537%5D.html_Files/unknown-8abe4ee1a65a68a5.png",
    "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading%20-%20Alex%20-%20%F0%9F%8E%96alex-journal%20%5B1001126327652458537%5D.html_Files/1f525-8fe4fec316602fac.svg"
  ],
  "source_type": "journal",
  "path": "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading - Alex - 🎖alex-journal [1001126327652458537].…",
  "captions": [],
  "ts_inherited": false,
  "tz_label": "PT"
}
```

### prime-report

```json
{
  "id": "1082100601816629369",
  "ts": "2023-03-05T16:41:00-08:00",
  "author": "Alex",
  "text": "",
  "attachment_paths": [
    "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading%20-%20Alex%20-%20%E2%9C%8F%EF%B8%8Fprime-report%20%5B1082100049422598215%5D.html_Files/image-0b6fe44bbf524660.png",
    "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading%20-%20Alex%20-%20%E2%9C%8F%EF%B8%8Fprime-report%20%5B1082100049422598215%5D.html_Files/1f44d-1f3fc-eab0d8cb47a24399.svg"
  ],
  "source_type": "report",
  "path": "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading - Alex - ✏️prime-report [1082100049422598215]…",
  "captions": [],
  "ts_inherited": false,
  "tz_label": "PT"
}
```

### pf-update

```json
{
  "id": "1019260070774714499",
  "ts": "2022-09-13T07:55:00-07:00",
  "author": "Alex",
  "text": "",
  "attachment_paths": [
    "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading%20-%20Alex%20-%20%F0%9F%93%92pf-update%20%5B1019259954101747753%5D.html_Files/unknown-c9d4ea0b60a6bc63.png",
    "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading%20-%20Alex%20-%20%F0%9F%93%92pf-update%20%5B1019259954101747753%5D.html_Files/1f44d-27259a90ef10d877.svg"
  ],
  "source_type": "pf_update",
  "path": "/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading - Alex - 📒pf-update [1019259954101747753].htm…",
  "captions": [],
  "ts_inherited": false,
  "tz_label": "PT"
}
```

## Sealed-cutoff usage

- Scorers must treat `id` as `message_id`.
- Eligible iff `channel ∈ MVP` and `parse(ts) < decision_ts` (strict).
- Same-minute bursts: use message_id order within channel after timestamp compare.
- Prefer current JSONL IDs (stable); do not re-mint from HTML.
