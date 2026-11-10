"""Best-effort discovery dates. These do NOT represent official exchange listing dates.

Streamlit Community Cloud may wipe /tmp when restarting or redeploying.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path

DEFAULT_PATH=Path('/tmp/kraken_signal_v3_observed_pairs.json')


def record_seen(pair_ids: set[str], filepath: Path=DEFAULT_PATH, now: datetime|None=None) -> dict:
    now=now or datetime.now(timezone.utc)
    existing={}
    if filepath.exists():
        try:
            existing=json.loads(filepath.read_text())
        except (OSError,ValueError,TypeError):
            existing={}
    initial=not bool(existing)
    before=set(existing)
    stamp=now.isoformat()
    for pid in pair_ids:
        if pid not in existing: existing[pid]=stamp
    try:
        filepath.parent.mkdir(parents=True,exist_ok=True)
        tmp=filepath.with_suffix('.tmp')
        tmp.write_text(json.dumps(existing,sort_keys=True))
        tmp.replace(filepath)
    except OSError: pass
    return {"initial_baseline":initial,"new_ids":set() if initial else pair_ids-before,
            "known_ids":set(existing),"first_seen":existing,"updated_utc":stamp}
