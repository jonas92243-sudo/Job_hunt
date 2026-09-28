"""Discord webhook alerts."""
import json
import time
import urllib.error
import urllib.request

from .http import USER_AGENT

DISCORD_LIMIT = 2000


class Notifier:
    def __init__(self, webhook_url, dry_run=False):
        self.webhook_url = webhook_url
        self.dry_run = dry_run or not webhook_url
        self.sent = 0

    def send(self, content):
        """Post one message. Returns True when Discord accepted it."""
        content = content[:DISCORD_LIMIT]
        if self.dry_run:
            print("---- alert (dry run) ----")
            print(content)
            self.sent += 1
            return True
        payload = json.dumps({
            "content": content,
            "allowed_mentions": {"parse": []},
        }).encode("utf-8")
        for attempt in range(4):
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            )
            try:
                with urllib.request.urlopen(req, timeout=20):
                    self.sent += 1
                    time.sleep(0.4)  # stay under Discord's webhook rate limit
                    return True
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    try:
                        wait = float(json.loads(e.read().decode()).get("retry_after", 2))
                    except (ValueError, json.JSONDecodeError):
                        wait = 2.0
                    time.sleep(min(wait, 30) + 0.2)
                    continue
                print(f"Discord rejected the message: HTTP {e.code}")
                return False
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                print(f"Discord request failed: {e}")
                time.sleep(2)
        return False


def short_location(location, limit=4):
    places = [p.strip() for p in location.split(";") if p.strip()]
    places = list(dict.fromkeys(places))
    if len(places) > limit:
        return "; ".join(places[:limit]) + f"; +{len(places) - limit} more"
    return "; ".join(places)


def job_alert(company, job, verdict):
    location = short_location(job.location) or "Location not listed"
    lines = [
        f"🆕 **{job.title}**, {company}",
        f"📍 {location}",
        f"🎓 {verdict.degree_note} · {verdict.level_note}",
    ]
    if job.posted:
        lines.append(f"🗓️ Posted: {job.posted}")
    lines.append(f"Posting: <{job.url}>")
    if job.apply_url and job.apply_url != job.url:
        lines.append(f"Apply: <{job.apply_url}>")
    return "\n".join(lines)


def _digest_rank(match):
    """Clearest entry-level matches first."""
    _, verdict = match
    if verdict.level_note.startswith("Entry-level"):
        return 0
    return 2 if verdict.level_note.startswith("Level unclear") else 1


def digest_messages(company, matches, limit=25):
    """Summaries of the jobs already open when a company is first scanned."""
    header = f"📋 **{company}** is now being watched. Open roles that match today ({len(matches)}):"
    if len(matches) > limit:
        header = (f"📋 **{company}** is now being watched. {len(matches)} open roles match today; "
                  f"the {limit} strongest are listed:")
    matches = sorted(matches, key=_digest_rank)[:limit]
    messages, current = [], header
    for job, verdict in matches:
        place = short_location(job.location, limit=2) or "location n/a"
        line = f"\n• [{job.title}](<{job.url}>) · {place} · {verdict.level_note}"
        if len(current) + len(line) > DISCORD_LIMIT - 50:
            messages.append(current)
            current = f"📋 **{company}** (continued):"
        current += line
    messages.append(current)
    return messages
