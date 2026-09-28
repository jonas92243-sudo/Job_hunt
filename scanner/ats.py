"""Readers for the public job-board APIs of each applicant tracking system.

Every reader exposes:
    list_jobs(board, cstate, options) -> Listing, or None when nothing changed
    fill_details(board, job)          -> loads the description when the list lacks it
"""
import hashlib
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import quote

from .http import request_json, request_text
from .text import html_to_text

WORKDAY_US_ID = "bc33aa3152ec42d4995f4791a106ed09"
WORKDAY_PAGE = 20
WORKDAY_FULL_CRAWL_SECONDS = 3600


@dataclass
class Job:
    id: str
    title: str
    url: str
    apply_url: str = ""
    location: str = ""
    country: str = ""
    employment_type: str = ""
    posted: str = ""
    description: str = ""
    needs_details: bool = False


@dataclass
class Listing:
    jobs: list
    # Saved into the company state only after the scan fully succeeds.
    markers: dict = field(default_factory=dict)


# ------------------------------------------------------------------ Greenhouse

class Greenhouse:
    name = "greenhouse"

    @staticmethod
    def _base(board):
        return f"https://boards-api.greenhouse.io/v1/boards/{quote(board)}/jobs"

    def list_jobs(self, board, cstate, options):
        resp = request_json(self._base(board), etag=cstate.get("etag"))
        if resp.not_modified:
            return None
        jobs = []
        for j in resp.data.get("jobs", []):
            employment = ""
            for meta in j.get("metadata") or []:
                if (meta.get("name") or "").lower() in ("employment type", "job type", "time type"):
                    value = meta.get("value")
                    employment = value if isinstance(value, str) else ""
            jobs.append(Job(
                id=str(j["id"]),
                title=(j.get("title") or "").strip(),
                url=j.get("absolute_url") or "",
                location=(j.get("location") or {}).get("name") or "",
                employment_type=employment,
                posted=(j.get("first_published") or j.get("updated_at") or "")[:10],
                needs_details=True,
            ))
        return Listing(jobs, {"etag": resp.etag})

    def fill_details(self, board, job):
        resp = request_json(f"{self._base(board)}/{job.id}")
        job.description = html_to_text(resp.data.get("content"))


# ----------------------------------------------------------------------- Lever

class Lever:
    name = "lever"

    def list_jobs(self, board, cstate, options):
        resp = request_json(
            f"https://api.lever.co/v0/postings/{quote(board)}?mode=json", etag=cstate.get("etag")
        )
        if resp.not_modified:
            return None
        jobs = []
        for j in resp.data or []:
            cats = j.get("categories") or {}
            parts = [j.get("descriptionPlain") or ""]
            for section in j.get("lists") or []:
                parts.append(section.get("text") or "")
                parts.append(html_to_text(section.get("content")))
            parts.append(j.get("additionalPlain") or "")
            locations = cats.get("allLocations") or [cats.get("location") or ""]
            created = j.get("createdAt")
            jobs.append(Job(
                id=str(j["id"]),
                title=(j.get("text") or "").strip(),
                url=j.get("hostedUrl") or "",
                apply_url=j.get("applyUrl") or "",
                location="; ".join(x for x in locations if x),
                country=j.get("country") or "",
                employment_type=cats.get("commitment") or "",
                posted=time.strftime("%Y-%m-%d", time.gmtime(created / 1000)) if created else "",
                description="\n".join(p for p in parts if p),
            ))
        return Listing(jobs, {"etag": resp.etag})

    def fill_details(self, board, job):
        pass


# ----------------------------------------------------------------------- Ashby

class Ashby:
    name = "ashby"

    def list_jobs(self, board, cstate, options):
        resp = request_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{quote(board)}", etag=cstate.get("etag")
        )
        if resp.not_modified:
            return None
        jobs = []
        for j in resp.data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            address = ((j.get("address") or {}).get("postalAddress")) or {}
            locations = [j.get("location") or ""]
            for extra in j.get("secondaryLocations") or []:
                locations.append(extra.get("location") or "")
            secondary_countries = [
                (((s.get("address") or {}).get("postalAddress")) or {}).get("addressCountry") or ""
                for s in j.get("secondaryLocations") or []
            ]
            country = address.get("addressCountry") or ""
            if any(c.lower().startswith("united states") for c in secondary_countries):
                country = "United States"
            jobs.append(Job(
                id=str(j["id"]),
                title=(j.get("title") or "").strip(),
                url=j.get("jobUrl") or "",
                apply_url=j.get("applyUrl") or "",
                location="; ".join(x for x in locations if x),
                country=country,
                employment_type=j.get("employmentType") or "",
                posted=(j.get("publishedAt") or "")[:10],
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            ))
        return Listing(jobs, {"etag": resp.etag})

    def fill_details(self, board, job):
        pass


# --------------------------------------------------------------------- Workday

class Workday:
    """board is 'tenant/wdN/site', for example 'blueorigin/wd5/BlueOrigin'.

    Workday returns 20 jobs per request in no dependable order, so a full crawl
    of the search results is needed to find new postings. To keep traffic low a
    single request checks whether the result count or first page changed; the
    full crawl runs only then, and at least once an hour.
    """
    name = "workday"

    @staticmethod
    def _parts(board):
        tenant, wd, site = board.split("/")
        host = f"https://{tenant}.{wd}.myworkdayjobs.com"
        return host, f"{host}/wday/cxs/{tenant}/{site}", site

    def _search(self, api, facets, text, offset):
        body = {"appliedFacets": facets, "limit": WORKDAY_PAGE, "offset": offset, "searchText": text}
        return request_json(f"{api}/jobs", body=body).data

    @staticmethod
    def _country_facet(data):
        """Find the facet that filters by country, if this site has one."""
        def walk(facets):
            for facet in facets or []:
                param = facet.get("facetParameter")
                for value in facet.get("values") or []:
                    if value.get("id") == WORKDAY_US_ID and param:
                        return param
                    if "values" in value:
                        found = walk([value])
                        if found:
                            return found
            return None
        return walk(data.get("facets"))

    def list_jobs(self, board, cstate, options):
        host, api, site = self._parts(board)
        text = options.get("workday_search_text", "mechanical")
        max_pages = options.get("workday_max_pages", 75)

        facet_key = cstate.get("wd_country_facet")
        if facet_key is None:
            facet_key = self._country_facet(self._search(api, {}, text, 0)) or ""
        facets = {facet_key: [WORKDAY_US_ID]} if facet_key and options.get("us_only", True) else {}

        first = self._search(api, facets, text, 0)
        total = first.get("total") or 0
        postings = list(first.get("jobPostings") or [])
        digest = hashlib.sha1(
            "|".join(p.get("externalPath", "") for p in postings).encode()
        ).hexdigest()[:12]
        signature = f"{total}:{digest}"
        now = int(time.time())
        recent_crawl = now - cstate.get("wd_full_at", 0) < WORKDAY_FULL_CRAWL_SECONDS
        if signature == cstate.get("wd_sig") and recent_crawl:
            return None

        offsets = list(range(WORKDAY_PAGE, min(total, max_pages * WORKDAY_PAGE), WORKDAY_PAGE))
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = pool.map(lambda off: self._search(api, facets, text, off), offsets)
            for page in pages:
                postings.extend(page.get("jobPostings") or [])

        jobs, seen_paths = [], set()
        for p in postings:
            path = p.get("externalPath")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            location = p.get("locationsText") or ""
            if not location or location.split()[0].isdigit():
                # "3 Locations": fall back to the place named in the job's address.
                segments = path.split("/")
                location = segments[2].replace("-", " ") if len(segments) > 3 else ""
            jobs.append(Job(
                id=path,
                title=(p.get("title") or "").strip(),
                url=f"{host}/{site}{path}",
                location=location,
                country="United States" if facets else "",
                posted=p.get("postedOn") or "",
                needs_details=True,
            ))
        markers = {"wd_sig": signature, "wd_full_at": now, "wd_country_facet": facet_key}
        return Listing(jobs, markers)

    def fill_details(self, board, job):
        _, api, _ = self._parts(board)
        info = request_json(f"{api}{job.id}").data.get("jobPostingInfo") or {}
        job.description = html_to_text(info.get("jobDescription"))
        job.employment_type = info.get("timeType") or ""
        locations = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
        job.location = "; ".join(x for x in locations if x) or job.location
        if not job.country:
            job.country = (info.get("country") or {}).get("descriptor") or ""
        job.url = info.get("externalUrl") or job.url
        job.apply_url = f"{job.url}/apply"
        job.posted = info.get("startDate") or job.posted


# ------------------------------------------------------------- SmartRecruiters

class SmartRecruiters:
    name = "smartrecruiters"
    PAGE = 100

    def list_jobs(self, board, cstate, options):
        base = f"https://api.smartrecruiters.com/v1/companies/{quote(board)}/postings"
        query = f"?limit={self.PAGE}&q={quote(options.get('smartrecruiters_search_text', 'mechanical'))}"
        if options.get("us_only", True):
            query += "&country=us"
        jobs, offset = [], 0
        while True:
            data = request_json(f"{base}{query}&offset={offset}").data
            content = data.get("content") or []
            for j in content:
                loc = j.get("location") or {}
                jobs.append(Job(
                    id=str(j["id"]),
                    title=(j.get("name") or "").strip(),
                    url=f"https://jobs.smartrecruiters.com/{board}/{j['id']}",
                    location=loc.get("fullLocation") or ", ".join(
                        x for x in (loc.get("city"), loc.get("region")) if x
                    ),
                    country=loc.get("country") or "",
                    employment_type=(j.get("typeOfEmployment") or {}).get("label") or "",
                    posted=(j.get("releasedDate") or "")[:10],
                    needs_details=True,
                ))
            offset += self.PAGE
            if not content or offset >= (data.get("totalFound") or 0) or offset >= 2000:
                break
        return Listing(jobs)

    def fill_details(self, board, job):
        data = request_json(
            f"https://api.smartrecruiters.com/v1/companies/{quote(board)}/postings/{job.id}"
        ).data
        sections = ((data.get("jobAd") or {}).get("sections")) or {}
        parts = []
        for key in ("jobDescription", "qualifications", "additionalInformation"):
            section = sections.get(key) or {}
            parts.append(section.get("title") or "")
            parts.append(html_to_text(section.get("text")))
        job.description = "\n".join(p for p in parts if p)
        job.url = data.get("postingUrl") or job.url
        job.apply_url = data.get("applyUrl") or ""


# ---------------------------------------------------------------------- Oracle

class Oracle:
    """board is 'host/siteNumber', for example 'egup.fa.us2.oraclecloud.com/CX'.

    Results come newest first, so after the first scan only the newest page is
    read unless every job on it is new.
    """
    name = "oracle"
    PAGE = 200

    def _page(self, host, site, keyword, offset):
        finder = f"findReqs;siteNumber={site},limit={self.PAGE},offset={offset},sortBy=POSTING_DATES_DESC"
        if keyword:
            finder += f",keyword=%22{quote(keyword)}%22"
        url = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
               f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}")
        items = request_json(url).data.get("items") or [{}]
        return items[0].get("requisitionList") or [], items[0].get("TotalJobsCount") or 0

    def list_jobs(self, board, cstate, options):
        host, site = board.split("/")
        keyword = options.get("oracle_search_text", "mechanical")
        seen = cstate.get("seen", {})
        jobs, offset = [], 0
        while True:
            rows, total = self._page(host, site, keyword, offset)
            for r in rows:
                places = [r.get("PrimaryLocation") or ""]
                places += [s.get("Name") or "" for s in r.get("secondaryLocations") or []]
                jobs.append(Job(
                    id=str(r["Id"]),
                    title=(r.get("Title") or "").strip(),
                    url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r['Id']}",
                    location="; ".join(p for p in places if p),
                    posted=r.get("PostedDate") or "",
                    needs_details=True,
                ))
            offset += self.PAGE
            page_all_new = bool(rows) and all(str(r["Id"]) not in seen for r in rows)
            first_scan = not cstate.get("baseline_done")
            if not rows or offset >= total or offset >= 3000:
                break
            if not first_scan and not page_all_new:
                break
        return Listing(jobs)

    def fill_details(self, board, job):
        host, site = board.split("/")
        url = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
               f"?expand=all&onlyData=true&finder=ById;Id=%22{quote(job.id)}%22,siteNumber={site}")
        items = request_json(url).data.get("items") or []
        if not items:
            raise ValueError(f"no details returned for job {job.id}")
        d = items[0]
        parts = [d.get("ExternalDescriptionStr"), d.get("ExternalResponsibilitiesStr"),
                 d.get("ExternalQualificationsStr")]
        job.description = "\n".join(html_to_text(p) for p in parts if p)
        job.employment_type = d.get("JobSchedule") or ""


# ------------------------------------------------------------------------ Jibe

class Jibe:
    """iCIMS career sites built on Jibe. board is the careers host, for example
    'careers.jhuapl.edu'. Results come newest first and include the description.
    """
    name = "jibe"
    PAGE = 100

    def list_jobs(self, board, cstate, options):
        keyword = quote(options.get("jibe_search_text", "mechanical"))
        seen = cstate.get("seen", {})
        first_scan = not cstate.get("baseline_done")
        jobs, page = [], 1
        while True:
            data = request_json(
                f"https://{board}/api/jobs?page={page}&limit={self.PAGE}&keywords={keyword}"
                "&sortBy=posted_date&descending=true&internal=false"
            ).data
            rows = [r.get("data") or {} for r in data.get("jobs") or []]
            for r in rows:
                parts = [r.get("description"), r.get("responsibilities"), r.get("qualifications")]
                place = ", ".join(x for x in (r.get("city"), r.get("state")) if x)
                jobs.append(Job(
                    id=str(r.get("slug") or r.get("req_id")),
                    title=(r.get("title") or "").strip(),
                    url=f"https://{board}/jobs/{r.get('slug')}?lang=en-us",
                    apply_url=r.get("apply_url") or "",
                    location=place or r.get("location_name") or "",
                    country=r.get("country_code") or r.get("country") or "",
                    employment_type=(r.get("employment_type") or "").replace("_", " "),
                    posted=(r.get("posted_date") or "")[:10],
                    description="\n".join(html_to_text(p) for p in parts if p),
                ))
            page_all_new = bool(rows) and all(str(r.get("slug")) not in seen for r in rows)
            total = data.get("totalCount") or 0
            if not rows or page * self.PAGE >= total or page >= 30:
                break
            if not first_scan and not page_all_new:
                break
            page += 1
        return Listing(jobs)

    def fill_details(self, board, job):
        pass


# ---------------------------------------------------------------- ClearCompany

class ClearCompany:
    """board is the hrmdirect.com subdomain, for example 'firefly'."""
    name = "clearcompany"
    _ITEM = re.compile(r"<item>(.*?)</item>", re.S)
    _LOCATION = re.compile(r"Location:\s*</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)

    @staticmethod
    def _tag(item, name):
        m = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
        return html.unescape(m.group(1)).strip() if m else ""

    def list_jobs(self, board, cstate, options):
        feed = request_text(f"https://{quote(board)}.hrmdirect.com/employment/rss.php?search=true")
        jobs = []
        for item in self._ITEM.findall(feed):
            link = self._tag(item, "link").replace("http://", "https://")
            req = re.search(r"req=(\d+)", link)
            if not req:
                continue
            jobs.append(Job(
                id=req.group(1),
                title=self._tag(item, "title"),
                url=link,
                posted=self._tag(item, "pubDate")[5:16],
                needs_details=True,
            ))
        if not jobs and "<rss" not in feed:
            raise ValueError("the job feed did not return a job list")
        return Listing(jobs)

    def fill_details(self, board, job):
        page = request_text(job.url)
        start = page.find('class="jobDesc"')
        if start < 0:
            raise ValueError(f"no description found for job {job.id}")
        job.description = html_to_text(page[start - 5: start + 30000].split(">", 1)[1])
        location = self._LOCATION.search(page)
        if location:
            job.location = html_to_text(location.group(1))


# --------------------------------------------------------------------- Radancy

class Radancy:
    """Career sites built by Radancy (TalentBrew). board is the careers host, for
    example 'careers.l3harris.com'. Like Workday, results are crawled in full
    only when the first page or the result count changed, and once an hour.
    """
    name = "radancy"
    PAGE = 100
    _ITEM = re.compile(
        r'<a[^>]+href="(/[^"]*?/job/[^"]+)"[^>]*data-job-id="(\d+)"[^>]*>(.*?)</a>', re.S
    )
    _TITLE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S)
    _LOCATION = re.compile(r'class="[^"]*job-location[^"]*"[^>]*>(.*?)</span>', re.S)
    _PAGES = re.compile(r'data-total-pages="(\d+)"')
    _TOTAL = re.compile(r'data-total-results="(\d+)"')
    _JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

    def _page(self, board, keyword, page):
        url = (
            f"https://{board}/en/search-jobs/results?ActiveFacetID=0&CurrentPage={page}"
            f"&RecordsPerPage={self.PAGE}&Distance=50&RadiusUnitType=0&Keywords={quote(keyword)}"
            "&Location=&ShowRadius=False&IsPagination=False&CustomFacetName=&FacetTerm=&FacetType=0"
            "&SearchResultsModuleName=Search+Results&SearchFiltersModuleName=Search+Filters"
            "&SortCriteria=0&SortDirection=0&SearchType=5&PostalCode=&ResultsType=0"
            "&fc=&fl=&fcf=&afc=&afl=&afcf="
        )
        return request_json(url).data.get("results") or ""

    def list_jobs(self, board, cstate, options):
        keyword = options.get("radancy_search_text", "mechanical")
        first = self._page(board, keyword, 1)
        items = self._ITEM.findall(first)
        total = self._TOTAL.search(first)
        pages = self._PAGES.search(first)
        digest = hashlib.sha1("|".join(i[1] for i in items).encode()).hexdigest()[:12]
        signature = f"{total.group(1) if total else len(items)}:{digest}"
        now = int(time.time())
        recent_crawl = now - cstate.get("wd_full_at", 0) < WORKDAY_FULL_CRAWL_SECONDS
        if signature == cstate.get("wd_sig") and recent_crawl:
            return None

        for page in range(2, min(int(pages.group(1)) if pages else 1, 30) + 1):
            items.extend(self._ITEM.findall(self._page(board, keyword, page)))

        jobs, seen_ids = [], set()
        for href, job_id, inner in items:
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            title = self._TITLE.search(inner)
            location = self._LOCATION.search(inner)
            jobs.append(Job(
                id=job_id,
                title=html_to_text(title.group(1)) if title else "",
                url=f"https://{board}{href}",
                location=html_to_text(location.group(1)) if location else "",
                needs_details=True,
            ))
        return Listing(jobs, {"wd_sig": signature, "wd_full_at": now})

    def fill_details(self, board, job):
        page = request_text(job.url)
        for block in self._JSON_LD.findall(page):
            try:
                data = json.loads(block, strict=False)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                job.description = html_to_text(data.get("description"))
                job.posted = data.get("datePosted") or job.posted
                return
        raise ValueError(f"no description found for job {job.id}")


READERS = {
    r.name: r
    for r in (Greenhouse(), Lever(), Ashby(), Workday(), SmartRecruiters(), Oracle(),
              Jibe(), ClearCompany(), Radancy())
}
