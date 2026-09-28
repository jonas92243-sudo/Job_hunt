"""Add a company to companies.toml.

    python add_company.py "Company Name" https://jobs.lever.co/company
    python add_company.py "Company Name"            (tries to find the board by name)
    python add_company.py "Company Name" --check    (look only, change nothing)

The link is the page that lists the company's open jobs. Supported job systems:
Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Oracle, ClearCompany, and
career sites built on Jibe (iCIMS) or Radancy.
"""
import argparse
import os
import re
import sys
import tomllib
from urllib.parse import urlsplit

from scanner.ats import READERS
from scanner.http import HttpError

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPANIES = os.path.join(ROOT, "companies.toml")

URL_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board\?for=([\w-]+)", re.I)),
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([\w.-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.%-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)", re.I)),
    ("clearcompany", re.compile(r"([\w-]+)\.hrmdirect\.com", re.I)),
]
WORKDAY_URL = re.compile(
    r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", re.I
)
ORACLE_URL = re.compile(r"https?://([\w.-]+)/hcmUI/CandidateExperience/[\w-]+/sites/([\w-]+)", re.I)


def from_url(url):
    m = WORKDAY_URL.search(url)
    if m:
        return [("workday", f"{m.group(1).lower()}/{m.group(2).lower()}/{m.group(3)}")]
    m = ORACLE_URL.search(url)
    if m:
        return [("oracle", f"{m.group(1).lower()}/{m.group(2)}")]
    for ats, pattern in URL_PATTERNS:
        m = pattern.search(url)
        if m:
            return [(ats, m.group(1))]
    # Jibe and Radancy sites run on the company's own web address, so try both.
    host = urlsplit(url if "//" in url else f"https://{url}").netloc.lower()
    return [("jibe", host), ("radancy", host)] if "." in host else []


def guesses(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    slugs = dict.fromkeys(["".join(words), "-".join(words), words[0] if words else ""])
    found = []
    for slug in slugs:
        if not slug:
            continue
        for ats in ("greenhouse", "lever", "ashby"):
            found.append((ats, slug))
        found.append(("smartrecruiters", "".join(w.capitalize() for w in words)))
    return list(dict.fromkeys(found))


def probe(ats, board):
    """Return the job list when the board exists and has jobs, else None."""
    try:
        listing = READERS[ats].list_jobs(board, {"seen": {}}, {"us_only": False,
                                                                "workday_search_text": "",
                                                                "workday_max_pages": 1,
                                                                "oracle_search_text": "",
                                                                "jibe_search_text": "",
                                                                "radancy_search_text": "",
                                                                "smartrecruiters_search_text": ""})
    except (HttpError, OSError, ValueError, KeyError, AttributeError, TypeError):
        return None
    return listing.jobs if listing and listing.jobs else None


def main():
    parser = argparse.ArgumentParser(description="Add a company to the scanner.")
    parser.add_argument("name", help='company name, in quotes, for example "Blue Origin"')
    parser.add_argument("url", nargs="?", help="link to the company's job listing page")
    parser.add_argument("--check", action="store_true", help="look only, change nothing")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.url:
        candidates = from_url(args.url)
        if not candidates:
            print("That does not look like a web link. Use the address of the page that lists")
            print("the company's open jobs.")
            return 1
    else:
        candidates = guesses(args.name)

    for ats, board in candidates:
        jobs = probe(ats, board)
        if jobs:
            break
    else:
        print(f"No readable job board found for '{args.name}'.")
        if args.url:
            print("The company may use a job system the scanner cannot read. Try the address")
            print("of one specific job posting instead, in case it lives on a different site.")
        else:
            print("Try again with the link to the company's job listing page.")
        return 1

    print(f"Found a {ats} board '{board}' with {len(jobs)} job(s). Examples:")
    for job in jobs[:5]:
        print(f"   {job.title}  |  {job.location}")
    if not args.url:
        print("This board was found by guessing from the name. Check that the examples above")
        print("belong to the right company before relying on it.")

    with open(COMPANIES, "rb") as f:
        existing = tomllib.load(f).get("company", [])
    if any(c["ats"] == ats and c["board"].lower() == board.lower() for c in existing):
        print("Already in companies.toml. Nothing to do.")
        return 0
    if args.check:
        print("Check only: companies.toml was not changed.")
        return 0

    safe_name = args.name.replace("\\", "\\\\").replace('"', '\\"')
    with open(COMPANIES, "a", encoding="utf-8") as f:
        f.write(f'\n[[company]]\nname = "{safe_name}"\nats = "{ats}"\nboard = "{board}"\n')
    print(f"Added {args.name} to companies.toml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
