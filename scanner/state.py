"""Remembers which jobs were already seen so each posting alerts once."""
import json
import os
from datetime import date, timedelta

REFRESH_DAYS = 7    # rewrite a job's last-seen date at most weekly to keep the file stable
FORGET_DAYS = 45    # drop jobs that have been gone from the board this long


def load(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"companies": {}}


def save(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=0, sort_keys=True)
    os.replace(tmp, path)


def company_state(state, key):
    cstate = state.setdefault("companies", {}).setdefault(key, {})
    cstate.setdefault("seen", {})
    return cstate


def mark_seen(cstate, job_id, today=None):
    cstate["seen"][job_id] = (today or date.today()).isoformat()


def refresh_and_prune(cstate, listed_ids, today=None):
    """Called after a full listing: keep listed jobs fresh, forget long-gone ones."""
    today = today or date.today()
    seen = cstate["seen"]
    refresh_before = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    forget_before = (today - timedelta(days=FORGET_DAYS)).isoformat()
    for job_id in listed_ids:
        if job_id in seen and seen[job_id] < refresh_before:
            seen[job_id] = today.isoformat()
    for job_id in [j for j, d in seen.items() if d < forget_before]:
        del seen[job_id]
