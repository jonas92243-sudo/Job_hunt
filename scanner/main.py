"""Scan every company in companies.toml once and alert on new matching jobs."""
import argparse
import os
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import state as state_store
from .ats import READERS
from .filters import evaluate, is_us_location, title_prefilter
from .notify import Notifier, digest_messages, job_alert

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURE_ALERT_AT = 12   # consecutive failed scans (about an hour) before warning


@dataclass
class ScanResult:
    company: dict
    key: str
    status: str = "ok"            # ok | unchanged | error
    error: str = ""
    listed: int = 0
    new: int = 0
    matches: list = field(default_factory=list)   # (job, verdict)
    rejected: list = field(default_factory=list)  # (job, verdict), for --explain
    markers: dict = field(default_factory=dict)
    complete: bool = True
    baseline: bool = False


def load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def company_key(company):
    return f"{company['ats']}:{company['board']}"


def scan_company(company, cstate, config):
    """Fetch one board and work out which unseen jobs match. Sends nothing."""
    result = ScanResult(company, company_key(company))
    result.baseline = not cstate.get("baseline_done")
    filters = config.get("filters", {})
    options = dict(config.get("scan", {}), us_only=filters.get("us_only", True))
    reader = READERS.get(company["ats"])
    if reader is None:
        result.status, result.error = "error", f"unknown ats '{company['ats']}'"
        return result
    try:
        listing = reader.list_jobs(company["board"], cstate, options)
    except Exception as e:  # one broken board must not stop the others
        result.status, result.error = "error", f"{type(e).__name__}: {e}"
        return result
    if listing is None:
        result.status = "unchanged"
        return result

    result.markers = listing.markers
    result.listed = len(listing.jobs)
    seen = cstate["seen"]
    state_store.refresh_and_prune(cstate, [j.id for j in listing.jobs])
    unseen = [j for j in listing.jobs if j.id not in seen]
    result.new = len(unseen)

    # Rule out what the title and location already decide, before loading descriptions.
    candidates = []
    for job in unseen:
        ok, _ = title_prefilter(job.title, filters)
        if ok and filters.get("us_only", True):
            ok = is_us_location(job.location, job.country)
        if ok:
            candidates.append(job)
        else:
            state_store.mark_seen(cstate, job.id)

    def load(job):
        if job.needs_details:
            reader.fill_details(company["board"], job)
        return job

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(job, pool.submit(load, job)) for job in candidates]
    for job, future in futures:
        if future.exception() is not None:
            # Left unseen so the next scan tries again.
            result.complete = False
            print(f"  [{company['name']}] could not load '{job.title}': {future.exception()}")
            continue
        verdict = evaluate(job, filters)
        if verdict.match:
            result.matches.append((job, verdict))
        else:
            result.rejected.append((job, verdict))
            state_store.mark_seen(cstate, job.id)
    return result


def deliver(result, cstate, notifier, config):
    """Send alerts for one company and record what was delivered."""
    name = result.company["name"]
    if result.baseline:
        wants_digest = config.get("alerts", {}).get("baseline_digest", True)
        delivered = True
        if wants_digest and result.matches:
            limit = config.get("alerts", {}).get("baseline_digest_max", 25)
            for message in digest_messages(name, result.matches, limit):
                delivered = notifier.send(message) and delivered
        if delivered:
            for job, _ in result.matches:
                state_store.mark_seen(cstate, job.id)
            if result.complete:
                cstate["baseline_done"] = True
        else:
            result.complete = False
    else:
        for job, verdict in result.matches:
            if notifier.send(job_alert(name, job, verdict)):
                state_store.mark_seen(cstate, job.id)
            else:
                result.complete = False
    if result.complete:
        # Only now is it safe to skip this board while it stays unchanged.
        cstate.update({k: v for k, v in result.markers.items() if v is not None})


def track_failures(result, cstate, notifier):
    if result.status == "error":
        cstate["failures"] = cstate.get("failures", 0) + 1
        if cstate["failures"] == FAILURE_ALERT_AT:
            notifier.send(
                f"⚠️ **{result.company['name']}** could not be scanned for "
                f"{FAILURE_ALERT_AT} runs in a row ({result.error}). "
                "Its job board address in companies.toml may have changed."
            )
    elif cstate.get("failures"):
        cstate["failures"] = 0


def heartbeat(state, notifier, config, company_count, errors):
    alerts = config.get("alerts", {})
    if not alerts.get("daily_heartbeat", True):
        return
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    if now.hour < alerts.get("heartbeat_hour_utc", 14) or state.get("heartbeat_date") == today:
        return
    message = f"✅ Job scanner is running. Watching {company_count} companies."
    if errors:
        message += f" Boards failing right now: {', '.join(errors)}."
    if notifier.send(message):
        state["heartbeat_date"] = today


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan company job boards for entry-level ME roles.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print alerts instead of sending them to Discord")
    parser.add_argument("--no-save", action="store_true", help="do not write the state file")
    parser.add_argument("--explain", action="store_true",
                        help="also print why the remaining candidate jobs were rejected")
    parser.add_argument("--company", action="append", default=[],
                        help="scan only this company name (repeatable)")
    parser.add_argument("--config", default=os.path.join(ROOT, "config.toml"))
    parser.add_argument("--companies", default=os.path.join(ROOT, "companies.toml"))
    parser.add_argument("--state", default=os.path.join(ROOT, "state", "seen.json"))
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    config = load_toml(args.config)
    companies = load_toml(args.companies).get("company", [])
    if args.company:
        wanted = {c.lower() for c in args.company}
        companies = [c for c in companies if c["name"].lower() in wanted]
    if not companies:
        print("No companies to scan. Add some to companies.toml.")
        return 1

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook and not args.dry_run:
        print("DISCORD_WEBHOOK_URL is not set. Use --dry-run to print alerts instead.")
        return 2
    notifier = Notifier(webhook, dry_run=args.dry_run)

    state = state_store.load(args.state)
    cstates = {company_key(c): state_store.company_state(state, company_key(c)) for c in companies}

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda c: scan_company(c, cstates[company_key(c)], config), companies
        ))

    errors = []
    for result in results:
        cstate = cstates[result.key]
        name = result.company["name"]
        track_failures(result, cstate, notifier)
        if result.status == "error":
            errors.append(name)
            print(f"{name}: ERROR {result.error}")
            continue
        if result.status == "unchanged":
            print(f"{name}: no change")
            continue
        deliver(result, cstate, notifier, config)
        label = "first scan, " if result.baseline else ""
        print(f"{name}: {label}{result.listed} listed, {result.new} new, "
              f"{len(result.matches)} matched")
        for job, verdict in result.matches:
            print(f"    + {job.title} | {job.location} | {verdict.degree_note} | {verdict.level_note}")
        if args.explain:
            for job, verdict in result.rejected:
                print(f"    - {job.title} | {verdict.reason}")

    if not args.company:
        heartbeat(state, notifier, config, len(companies), errors)
    if not args.no_save:
        state_store.save(args.state, state)
    print(f"Done. {notifier.sent} message(s) sent, {len(errors)} board(s) failed.")
    # A few failing boards are reported through Discord; only fail the run when all do.
    return 1 if len(errors) == len(companies) else 0
