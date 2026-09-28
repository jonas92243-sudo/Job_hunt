"""Decide whether a posting is a full-time, entry-level, U.S. job that asks for a
Mechanical Engineering bachelor's degree.

Everything here works on plain text and has no network access, so it is covered
by tests/test_filters.py.
"""
import re
from dataclasses import dataclass

# ---------------------------------------------------------------- title rules

NOT_FULL_TIME_TITLE = re.compile(
    r"\b(intern(ship)?s?|co-?ops?|part[- ]time|temporary|temp|seasonal|contractor|contract|"
    r"apprentice(ship)?|fellowship|student|postdoc\w*|post-doc\w*|ph\.?d)\b",
    re.I,
)

SENIOR_TITLE = re.compile(
    r"\b(senior|sr|staff|principal|lead|manager|mgr|director|head|chief|vp|vice president|"
    r"fellow|architect|supervisor|expert|distinguished|superintendent|president|experienced|"
    r"advanced|mid[- ]level|leader)\b",
    re.I,
)

_LEVEL_NOUN = r"(engineer|engineering|eng|engr|designer|analyst|technologist|scientist|level|lvl|grade)"

HIGHER_LEVEL_TITLE = re.compile(
    r"\b(ii|iii|iv|vi)\b|\b" + _LEVEL_NOUN + r"\s*-?\s*[2-9]\b|\b[2-9]\s*$",
    re.I,
)

ENTRY_LEVEL_TITLE = re.compile(
    r"\b(new[- ]grad(uate)?s?|new college grad(uate)?s?|entry[- ]level|early[- ]career|"
    r"early in career|university grad(uate)?s?|college grad(uate)?s?|recent grad(uate)?s?|"
    r"graduate|junior|jr|associate|rotational|rotation|development program|"
    r"leadership program|trainee|campus|ncg|20(26|27))\b"
    r"|\b" + _LEVEL_NOUN + r"\s*-?\s*(1|i)\b",
    re.I,
)
# "Engineer, Mechanical I": a bare roman numeral one closing the title.
TRAILING_LEVEL_ONE = re.compile(r"\bI\s*$")

# ------------------------------------------------------------ description rules

ENTRY_LEVEL_TEXT = re.compile(
    r"\b(new[- ]grad(uate)?s?|recent(ly)? graduate[sd]?|entry[- ]level|early[- ]career|"
    r"no (prior )?experience (is )?(required|necessary)|graduating (in|by|between)|"
    r"upcoming graduates?|0\s*(-|–|to)\s*[1-3]\s*\+?\s*years?)\b",
    re.I,
)

# Spelled-out words match in any case; abbreviations (BS, B.S., MS) only in capitals.
BACHELOR_WORD = re.compile(
    r"(?i:\b(bachelor'?s?|bachelor’s|baccalaureate|undergraduate degree|(4|four)[- ]year degree)\b)"
    r"|(?<![A-Za-z])B\.?S\.?(?:c\.?)?(?:M\.?E\.?)?(?![A-Za-z])"
    r"|(?<![A-Za-z])B\.?Eng\.?(?![A-Za-z])"
)
BSME = re.compile(r"(?<![A-Za-z])B\.?S\.?M\.?E\.?(?![A-Za-z])")
ADVANCED_WORD = re.compile(
    r"(?i:\b(master'?s?|master’s|ph\.?d\.?|doctorate|doctoral)\b)"
    r"|(?<![A-Za-z])M\.?S\.?(?![A-Za-z])"
)
MECHANICAL = re.compile(r"\bmechanical\b", re.I)
GENERAL_DEGREE = re.compile(
    r"\b(engineering|stem|science|related (field|discipline)|"
    r"technical (field|discipline|degree))\b",
    re.I,
)
OTHER_DISCIPLINE = re.compile(
    r"\b(electrical|electronics?|computer|software|chemical|civil|industrial|materials?|"
    r"metallurgical|naval|marine|ocean|structural|nuclear|biomedical|aerospace|aeronautical|"
    r"optical|accounting|finance|business|welding|architecture)\b",
    re.I,
)

PREFERRED_SECTION = re.compile(
    r"\b(preferred (qualifications?|skills?|experience|requirements?)|nice[- ]to[- ]haves?|"
    r"desired (qualifications?|skills?|experience)|bonus points|pluses|"
    r"preferred:|what would be nice)\b",
    re.I,
)

_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}
_WORD_NUMBER = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r")\b(?=[^.\n]{0,25}\b(?:years?|yrs?)\b)", re.I
)
_PAREN_NUMBER = re.compile(r"\(\s*\d{1,2}\s*\+?\s*\)")
YEARS = re.compile(
    r"(?<![\d.$,])(?P<lo>\d{1,2})\s*(?:\+|plus\b|or more\b)?\s*"
    r"(?:(?:-|–|—|to)\s*(?P<hi>\d{1,2})\s*(?:\+|plus\b)?\s*)?"
    r"(?:years?|yrs?)\b",
    re.I,
)
_EXPERIENCE_CONTEXT = re.compile(r"experience|minimum|at least|\bexp\b", re.I)

NOT_FULL_TIME_TYPE = re.compile(r"intern|part|contract|temp|seasonal|co-?op|fixed term", re.I)

# ------------------------------------------------------------- location rules

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
_US_WORD = re.compile(r"\b(united states|u\.s\.a?\.?|usa)\b", re.I)
_US_CODE = re.compile(r"\bUS\b")
_STATE_NAME = re.compile(
    r"\b(" + "|".join(n for n in US_STATES.values() if n != "Georgia") + r")\b", re.I
)
_FOREIGN = re.compile(
    r"\b(canada|mexico|india|china|japan|germany|france|united kingdom|uk|england|scotland|"
    r"ireland|australia|singapore|israel|netherlands|poland|spain|italy|brazil|taiwan|korea|"
    r"malaysia|philippines|vietnam|thailand|sweden|switzerland|denmark|norway|finland|belgium|"
    r"austria|czech|hungary|romania|portugal|turkey|uae|saudi|qatar|egypt|south africa|"
    r"new zealand|costa rica|colombia|argentina|chile|indonesia|bangalore|bengaluru|hyderabad|"
    r"pune|chennai|toronto|vancouver|montreal|ottawa|ontario|quebec|london|munich|berlin|paris|"
    r"tokyo|shanghai|beijing|shenzhen|penang|tel aviv|dublin|guadalajara|monterrey|tijuana|"
    r"juarez|chihuahua|hsinchu|taipei|seoul|emea|apac|asia|europe|africa|latin america|"
    r"international|united arab emirates|abu dhabi|dubai|saudi arabia|riyadh|doha|cairo|"
    r"nigeria|ghana|rwanda|kenya|ivory coast|côte d’ivoire|cote d'ivoire|morocco|tunisia|"
    r"johannesburg|greece|athens|ukraine|kyiv|estonia|latvia|lithuania|slovenia|croatia|"
    r"serbia|bulgaria|luxembourg|iceland|amsterdam|warsaw|zurich|geneva|stockholm|copenhagen|"
    r"oslo|helsinki|madrid|barcelona|rome|milan|turin|brussels|vienna|prague|budapest|"
    r"bucharest|lisbon|istanbul|sydney|melbourne|brisbane|canberra|auckland|nz|brasil|"
    r"são paulo|sao paulo|ciudad de méxico|cdmx|bogota|buenos aires|lima|peru|jakarta|manila|"
    r"bangkok|hanoi|ho chi minh|kuala lumpur|hong kong|osaka|yokohama|busan|gurgaon|gurugram|"
    r"noida|mumbai|delhi|kolkata|ahmedabad|pakistan|bangladesh|sri lanka|british columbia|"
    r"alberta)\b",
    re.I,
)
_PLACE_SPLIT = re.compile(r";|\||\s+or\s+|\s+&\s+")
_CODE = re.compile(r"\b[A-Z]{2}\b")
# State codes that are also common country codes (Canada, India, Germany, ...).
_AMBIGUOUS_CODES = {"CA", "IN", "DE", "ID", "IL", "CO"}


@dataclass
class Verdict:
    match: bool
    reason: str = ""        # why it was rejected
    level_note: str = ""    # shown in the alert
    degree_note: str = ""   # shown in the alert


def is_us_location(location, country=""):
    """True when the location is in the U.S. or cannot be told apart from it."""
    if country:
        c = country.strip().lower()
        return c in ("us", "usa") or c.startswith("united states")
    if not location or not location.strip():
        return True
    # A posting open in several places counts when any one of them is in the U.S.
    places = [_classify_place(p) for p in _PLACE_SPLIT.split(location) if p.strip()]
    if "us" in places:
        return True
    return "foreign" not in places


def _classify_place(place):
    """'us', 'foreign' or 'unknown' for one place name."""
    codes = set(_CODE.findall(place)) & set(US_STATES)
    if _US_WORD.search(place) or _US_CODE.search(place) or _STATE_NAME.search(place):
        return "us"
    if _FOREIGN.search(place):
        # "Vancouver, WA" and "Paris, TX" are U.S. towns sharing a foreign name.
        return "us" if codes - _AMBIGUOUS_CODES else "foreign"
    return "us" if codes else "unknown"


def classify_title(title):
    """Return 'reject:<why>', 'entry' or 'unknown' from the title alone."""
    if NOT_FULL_TIME_TITLE.search(title):
        return "reject:not a full-time role"
    if SENIOR_TITLE.search(title):
        return "reject:senior title"
    if ENTRY_LEVEL_TITLE.search(title) or TRAILING_LEVEL_ONE.search(title):
        return "entry"
    if HIGHER_LEVEL_TITLE.search(title):
        return "reject:level II or above"
    return "unknown"


def title_prefilter(title, filters):
    """Cheap check made before downloading the full description."""
    verdict = classify_title(title)
    if verdict.startswith("reject:"):
        return False, verdict[7:]
    lowered = title.lower()
    for word in filters.get("title_exclude_keywords", []):
        if word.lower() in lowered:
            return False, f"title contains '{word}'"
    required = filters.get("title_require_keywords", [])
    if required and not any(word.lower() in lowered for word in required):
        return False, "title has none of the required keywords"
    return True, ""


def _normalize_numbers(text):
    text = _WORD_NUMBER.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], text)
    return _PAREN_NUMBER.sub(" ", text)


def _experience_mentions(text):
    """Yield (position, minimum_years) for each 'N years of experience' style phrase."""
    for m in YEARS.finditer(text):
        lo = int(m.group("lo"))
        if lo > 15:
            continue
        window = text[max(0, m.start() - 60): m.end() + 80]
        if _EXPERIENCE_CONTEXT.search(window):
            yield m.start(), lo


def required_years(description):
    """Best estimate of the years of experience a bachelor's holder needs, or None."""
    text = _normalize_numbers(description)
    preferred = PREFERRED_SECTION.search(text)
    required_part = text[: preferred.start()] if preferred else text
    mentions = list(_experience_mentions(required_part))
    if not mentions:
        mentions = list(_experience_mentions(text))
        required_part = text
    if not mentions:
        return None

    # "Bachelor's with 2+ years, or Master's with 0+ years": use the number tied to the bachelor's.
    paired = []
    for b in BACHELOR_WORD.finditer(required_part):
        for pos, years in mentions:
            if b.end() <= pos <= b.end() + 150:
                between = required_part[b.end(): pos]
                if not ADVANCED_WORD.search(between):
                    paired.append(years)
                break
    if paired:
        return min(paired)

    unpaired = []
    for pos, years in mentions:
        before = required_part[max(0, pos - 60): pos]
        if not ADVANCED_WORD.search(before):
            unpaired.append(years)
    if not unpaired:
        unpaired = [years for _, years in mentions]
    return max(unpaired)


_SENTENCE_END = re.compile(r"\n|[.;]\s")


def _sentence_around(text, start, end):
    """The sentence holding text[start:end], so a degree is not tied to unrelated wording."""
    before = text[max(0, start - 120): start]
    breaks = list(_SENTENCE_END.finditer(before))
    if breaks:
        before = before[breaks[-1].end():]
    after = text[end: end + 200]
    stop = _SENTENCE_END.search(after)
    if stop:
        after = after[: stop.start()]
    return before + text[start:end] + after


def degree_check(title, description, filters):
    """Return a note describing the degree match, or '' when the posting does not qualify."""
    if BSME.search(description):
        return "Mechanical Engineering B.S. listed"
    bachelor_spans = [m.span() for m in BACHELOR_WORD.finditer(description)]
    if not bachelor_spans:
        return ""
    sentences = [_sentence_around(description, start, end) for start, end in bachelor_spans]
    if any(MECHANICAL.search(s) for s in sentences):
        return "Mechanical Engineering B.S. listed"
    # "Bachelor's degree in engineering or a related field": open to any engineering
    # graduate, as long as the sentence does not name some other discipline instead.
    general_degree = any(
        GENERAL_DEGREE.search(s) and not OTHER_DISCIPLINE.search(s) for s in sentences
    )
    if general_degree and MECHANICAL.search(title):
        return "Engineering B.S. listed, mechanical role"
    if (
        general_degree
        and filters.get("include_general_engineering_degree", True)
        and MECHANICAL.search(description)
        and _has_mechanical_title(title, filters)
    ):
        return "General engineering B.S. listed, mechanical work mentioned"
    return ""


def _has_mechanical_title(title, filters):
    keywords = filters.get("mechanical_title_keywords", [])
    lowered = title.lower()
    return not keywords or any(word.lower() in lowered for word in keywords)


def evaluate(job, filters):
    """Full decision for a job whose description has been loaded."""
    ok, reason = title_prefilter(job.title, filters)
    if not ok:
        return Verdict(False, reason)

    if job.employment_type and NOT_FULL_TIME_TYPE.search(job.employment_type):
        return Verdict(False, f"employment type is {job.employment_type}")

    if filters.get("us_only", True) and not is_us_location(job.location, job.country):
        return Verdict(False, f"outside the U.S. ({job.location or job.country})")

    degree_note = degree_check(job.title, job.description, filters)
    if not degree_note:
        return Verdict(False, "no Mechanical Engineering bachelor's requirement found")

    max_years = filters.get("max_years_experience", 2)
    years = required_years(job.description)
    title_class = classify_title(job.title)

    if title_class == "entry":
        if years is not None and years > max_years + 1:
            return Verdict(False, f"entry-style title but asks for {years}+ years")
        note = "Entry-level title"
        if years is not None:
            note += f", {years}+ yrs experience stated"
        return Verdict(True, level_note=note, degree_note=degree_note)

    if years is not None:
        if years <= max_years:
            return Verdict(True, level_note=f"{years}+ yrs experience stated", degree_note=degree_note)
        return Verdict(False, f"asks for {years}+ years of experience")

    if ENTRY_LEVEL_TEXT.search(job.description):
        return Verdict(True, level_note="Entry-level wording in description", degree_note=degree_note)

    if filters.get("include_unclear_level", True):
        return Verdict(True, level_note="Level unclear: no experience requirement stated",
                       degree_note=degree_note)
    return Verdict(False, "experience level could not be determined")
