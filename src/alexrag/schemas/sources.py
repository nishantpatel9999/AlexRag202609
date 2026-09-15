"""Corpus source types, retrieval precedence, and first-class conflict labels.

See docs/CORPUS.md. MVP does not ingest operator Mac Discord/GitBook paths.
"""

from __future__ import annotations

from typing import Literal

# Machine names used in JSONL / RAG. Order IS retrieval precedence when sources conflict.
SOURCE_TYPES = (
    "trade_log",  # equity-trades: fills/closes, text tape (ground truth)
    "journal",  # alex-journal: same-time charts/notes
    "gameplan",  # morning gameplan
    "report",  # prime-report: evening focuslists
    "pf_update",  # pf-update: portfolio snapshots, NOT a fill log
    "gitbook",  # doctrine only (live GitBook + distillation/ebook; not a local GitBook mirror)
)
SourceType = Literal["trade_log", "journal", "gameplan", "report", "pf_update", "gitbook"]

PRECEDENCE_DEFAULT = SOURCE_TYPES

CHANNEL_TO_SOURCE: dict[str, SourceType] = {
    "equity-trades": "trade_log",
    "alex-journal": "journal",
    "morning-gameplan": "gameplan",
    "prime-report": "report",
    "pf-update": "pf_update",
}

# Conflicts are common in the live corpus. Labels are first-class on Proposal / eval notes.
CONFLICT_LABELS = (
    "no_trade_plan_then_entry",
    "short_vs_rulebook_default",
    "fill_vs_same_time_journal",
    "gameplan_vs_tape",
    "evening_report_vs_intraday",
    "doctrine_vs_tape",
)
ConflictLabel = Literal[
    "no_trade_plan_then_entry",
    "short_vs_rulebook_default",
    "fill_vs_same_time_journal",
    "gameplan_vs_tape",
    "evening_report_vs_intraday",
    "doctrine_vs_tape",
]

# Operator-local DiscordChatExporter inventories (Mac Studio). Not ingested in MVP.
PF_UPDATE_MAC_HTML = (
    "/Users/n_mac/DiscordArchives/PrimeTrading/"
    "PrimeTrading - Alex - 📒pf-update [1019259954101747753].html"
)

CORPUS_CHANNELS = (
    {
        "channel": "equity-trades",
        "source_type": "trade_log",
        "approx_messages": 6664,
        "role": "text tape / fills / closes; ground truth when sources disagree",
        "mvp": True,
    },
    {
        "channel": "alex-journal",
        "source_type": "journal",
        "approx_messages": 5471,
        "role": "chart-heavy same-session notes",
        "mvp": True,
    },
    {
        "channel": "prime-report",
        "source_type": "report",
        "approx_messages": 3062,
        "role": "evening focuslists",
        "mvp": True,
    },
    {
        "channel": "pf-update",
        "source_type": "pf_update",
        "approx_messages": None,
        "role": "portfolio snapshots (NAV/DD/positions); not a fill log; never overrides tape",
        "mvp": True,
        "mac_html": PF_UPDATE_MAC_HTML,
        "mac_html_files": (
            "/Users/n_mac/DiscordArchives/PrimeTrading/"
            "PrimeTrading - Alex - 📒pf-update [1019259954101747753]_Files"
        ),
    },
)

OUT_OF_MVP_CHANNELS = (
    {
        "channel": "focuslist-ideas",
        "mvp": False,
        "role": "out of MVP; do not ingest",
    },
)

DOCTRINE_SOURCES = (
    "live GitBook (no local mirror; no full offline GitBook scrape for MVP)",
    "PRIMETRADING_RULEBOOK_DISTILLATION.md",
    "PrimeTrading_Ebook.pdf",
)

DEFAULT_DISCORD_TZ = "America/Los_Angeles"
GOLDEN_CASE_COUNT = 48
