#!/usr/bin/env python3
"""Daily paper-trading snapshot → Digital Brain vault.

Pulls the live paper results off the Oracle box (via the Tailscale Funnel API)
after market close and appends a dated entry to the TNFund journal so the
long/short and per-symbol sample compounds over time. Runs on the Mac (the
vault lives in iCloud here). Scheduled by com.taranveer.paper-journal.
"""
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from collections import defaultdict

API = "https://quant-os.tail1c374e.ts.net/api"
VAULT = Path(
    "/Users/taranveersingh/Library/Mobile Documents/iCloud~md~obsidian/"
    "Documents/Digital Brain/Projects & Building/TNFund Trading Bot/"
    "13 - Daily Paper Journal.md"
)
LOCAL_JOURNAL = Path("/Users/taranveersingh/Automated-Trading-Bot/paper_journal_local.md")


def _get(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=25) as r:
        return json.load(r)


def build_entry() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    perf = _get("/paper/performance").get("rows", [])
    trades = _get("/paper/trades?range=today").get("trades", [])

    # Long/short split by the closing leg (SELL closes a long, COVER a short).
    longs = [t for t in trades if t["side"] == "SELL"]
    shorts = [t for t in trades if t["side"] == "COVER"]

    def side_line(name, ts):
        n = len(ts)
        pnl = sum(t["pnl"] for t in ts)
        wins = sum(1 for t in ts if t["pnl"] > 0)
        wr = (wins / n * 100) if n else 0.0
        return f"- **{name}:** {n} closed | ${pnl:+.2f} | {wr:.0f}% win"

    net = sum(t["pnl"] for t in trades if t["side"] in ("SELL", "COVER"))

    # Per-symbol from the performance endpoint (today columns).
    sym_lines = []
    for r in sorted(perf, key=lambda x: x["symbol"]):
        sym_lines.append(
            f"| {r['symbol']} | {int(r['today_shares'] // 100)} | "
            f"${r['today_pnl']:+.2f} | {r['today_win_rate']:.0f}% |"
        )

    # Counter-trend vs trend-aligned split (the forward A/B for the
    # mean-reversion finding). Comes from the analytics round-trip pairing.
    trend_line = ""
    try:
        by_trend = _get("/paper/analytics?range=today").get("by_trend", [])
        parts = [
            f"{b['key']} {b['trades']} | ${b['pnl']:+.2f} | {b['win_rate']:.0f}% win"
            for b in by_trend if b["key"] != "untagged" and b["trades"]
        ]
        if parts:
            trend_line = "\n- **Trend A/B (entry vs 60s drift):** " + "  ·  ".join(parts)
    except Exception:
        pass

    # Conviction: avg imbalance ratio on winning vs losing closes (if logged).
    conv_line = ""
    closes = [t for t in trades if t["side"] in ("SELL", "COVER") and t.get("imbalance_ratio") is not None]
    if closes:
        w = [t["imbalance_ratio"] for t in closes if t["pnl"] > 0]
        l = [t["imbalance_ratio"] for t in closes if t["pnl"] < 0]
        aw = (sum(w) / len(w)) if w else 0.0
        al = (sum(l) / len(l)) if l else 0.0
        conv_line = f"\n- **Conviction (avg imbalance ratio):** winners {aw:.2f} vs losers {al:.2f}"

    out = [
        f"\n## {today}",
        f"**Net P&L:** ${net:+.2f}  ·  **{len(trades)} legs**",
        "",
        side_line("LONG", longs),
        side_line("SHORT", shorts),
        "",
        "| Symbol | Trades | P&L | Win% |",
        "|---|---|---|---|",
        *sym_lines,
    ]
    if trend_line:
        out.append(trend_line)
    if conv_line:
        out.append(conv_line)
    return "\n".join(out) + "\n"


PENDING = Path.home() / ".pais" / "paper_journal_pending.md"


def _append_vault(text: str) -> None:
    if not VAULT.exists():
        header = (
            "---\ntags:\n  - trading\n  - bot\n  - journal\n---\n\n"
            "# Daily Paper Journal\n\n> **[[00 - Index|TNFund Trading Bot]]**\n\n"
            "Auto-appended daily after market close by `daily_paper_snapshot.py`. "
            "Each entry: net P&L, long vs short, per-symbol, and conviction split. "
            "Lets the long/short & symbol asymmetry build a real sample over weeks.\n"
        )
        VAULT.write_text(header)
    with VAULT.open("a") as f:
        f.write(text)


def main():
    try:
        entry = build_entry()
    except Exception as e:
        print(f"[paper-journal] API unavailable ({e}) — skipping snapshot")
        return

    # Always write to local journal first (never fails on permissions).
    with LOCAL_JOURNAL.open("a") as f:
        f.write(entry)
    print(f"[paper-journal] local → {LOCAL_JOURNAL.name}")

    # Flush any entries stranded by a previous permission failure first, so
    # the journal stays chronological even across broken days.
    backlog = ""
    if PENDING.exists():
        backlog = PENDING.read_text()

    try:
        _append_vault(backlog + entry)
        if backlog:
            PENDING.unlink()
            print(f"[paper-journal] flushed {len(backlog)} pending bytes")
        print(f"[paper-journal] vault → {VAULT.name}")
    except PermissionError:
        # launchd-spawned python3 has no iCloud (TCC) access unless granted
        # Full Disk Access. Stage locally; the next run — or any run from a
        # terminal context — flushes it into the vault.
        PENDING.parent.mkdir(parents=True, exist_ok=True)
        with PENDING.open("a") as f:
            f.write(entry)
        print(f"[paper-journal] vault unwritable (TCC) — staged to {PENDING}")


if __name__ == "__main__":
    main()
