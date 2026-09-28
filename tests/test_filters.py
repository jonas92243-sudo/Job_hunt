import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.ats import Job  # noqa: E402
from scanner.filters import (  # noqa: E402
    classify_title, degree_check, evaluate, is_us_location, required_years, title_prefilter,
)
from scanner.text import html_to_text  # noqa: E402

FILTERS = {
    "max_years_experience": 2,
    "include_unclear_level": True,
    "us_only": True,
    "include_general_engineering_degree": False,
    "title_require_keywords": ["engineer", "mechanical", "designer", "graduate"],
    "title_exclude_keywords": ["software", "technician"],
}

ME_DEGREE = "Basic qualifications: Bachelor's degree in mechanical engineering or aerospace engineering. "


def job(title, description, **kw):
    return Job(id="1", title=title, url="https://example.com/1", description=description, **kw)


class TitleTests(unittest.TestCase):
    def test_entry_titles(self):
        for title in [
            "Mechanical Engineer I", "Mechanical Engineer 1", "New Grad Mechanical Engineer",
            "Associate Mechanical Engineer", "Mechanical Design Engineer I/II",
            "Entry-Level Manufacturing Engineer", "Engineer, Mechanical I",
            "Mechanical Engineer, University Graduate 2027", "Junior Design Engineer",
            "Early Career Thermal Engineer",
        ]:
            self.assertEqual(classify_title(title), "entry", title)

    def test_rejected_titles(self):
        for title in [
            "Senior Mechanical Engineer", "Sr. Mechanical Engineer", "Mechanical Engineer II",
            "Mechanical Engineer 3", "Staff Thermal Engineer", "Mechanical Engineering Intern",
            "Mechanical Engineer Co-Op", "Principal Design Engineer", "Engineering Manager",
            "Lead Mechanical Engineer", "Mechanical Engineer III", "Mechanical Engineer (Contract)",
            "Insulation Design Engineer II, New Glenn Stage 2", "Summer 2027 Internship",
            "Lab Operations Engineer Co op", "Principle Systems Engineer",
        ]:
            self.assertTrue(classify_title(title).startswith("reject"), title)

    def test_unknown_titles(self):
        for title in ["Mechanical Engineer", "Mechanical Design Engineer, Starship",
                      "Thermal Engineer", "Engineer in Training"]:
            self.assertEqual(classify_title(title), "unknown", title)

    def test_prefilter_keywords(self):
        self.assertFalse(title_prefilter("Software Engineer I", FILTERS)[0])
        self.assertFalse(title_prefilter("Accountant", FILTERS)[0])
        self.assertFalse(title_prefilter("Mechanical Technician", FILTERS)[0])
        self.assertTrue(title_prefilter("Mechanical Engineer", FILTERS)[0])


class ExperienceTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(required_years("Requires 5+ years of experience in design."), 5)
        self.assertEqual(required_years("0-2 years of relevant experience."), 0)
        self.assertEqual(required_years("Minimum of two (2) years experience."), 2)
        self.assertEqual(required_years("1 to 3 years of professional experience"), 1)
        self.assertIsNone(required_years("We were founded 20 years ago. Great benefits."))
        self.assertIsNone(required_years("No requirements listed."))

    def test_bachelor_pairing(self):
        text = ("Bachelor's degree in engineering and 5+ years of experience, or Master's degree "
                "and 3+ years of experience, or PhD with 0 years of experience.")
        self.assertEqual(required_years(text), 5)

    def test_preferred_section_ignored(self):
        text = ("Basic qualifications: Bachelor's degree in mechanical engineering. "
                "1+ years of experience with CAD. "
                "Preferred qualifications: 5+ years of experience with CFD.")
        self.assertEqual(required_years(text), 1)

    def test_largest_required_number_wins(self):
        text = "5+ years of experience in mechanical design. 1+ years of experience with Python."
        self.assertEqual(required_years(text), 5)


class DegreeTests(unittest.TestCase):
    def test_mechanical_degree(self):
        for text in [
            "Bachelor's degree in Mechanical Engineering",
            "BS in Aerospace, Mechanical, or Electrical Engineering",
            "B.S. degree in an engineering discipline (mechanical preferred)",
            "BSME required",
            "Bachelor of Science in Mechanical Engineering or related field",
            "Bachelor’s degree in mechanical engineering",
        ]:
            self.assertTrue(degree_check("Design Engineer", text, FILTERS), text)

    def test_other_degrees(self):
        for text in [
            "Bachelor's degree in Computer Science",
            "Master's degree in Mechanical Engineering required",
            "High school diploma. Mechanical aptitude.",
            "PhD in Mechanical Engineering",
        ]:
            self.assertFalse(degree_check("Design Engineer", text, FILTERS), text)

    def test_general_engineering_degree(self):
        text = "Bachelor's degree in engineering."
        self.assertTrue(degree_check("Mechanical Engineer", text, FILTERS))
        self.assertFalse(degree_check("Design Engineer", text + " Mechanical design work.", FILTERS))
        relaxed = dict(FILTERS, include_general_engineering_degree=True)
        self.assertTrue(degree_check("Design Engineer", text + " Mechanical design work.", relaxed))
        for wording in [
            "Undergraduate degree in engineering or related field",
            "Bachelor’s degree in a related discipline.",
            "Bachelor’s degree in a science, engineering, technology, or mathematics field",
        ]:
            self.assertTrue(
                degree_check("Mechanisms Engineer I", wording + "\nMechanical design work.", relaxed),
                wording,
            )

    def test_general_degree_naming_another_discipline(self):
        relaxed = dict(FILTERS, include_general_engineering_degree=True)
        for wording in [
            "Bachelor's degree in Electrical Engineering or related field",
            "Bachelor's degree in Naval Architecture, Marine Engineering, or a related field",
        ]:
            self.assertFalse(
                degree_check("Build Engineer", wording + "\nWorks with mechanical teams.", relaxed),
                wording,
            )


class LocationTests(unittest.TestCase):
    def test_us(self):
        for loc in ["Hawthorne, CA", "Dallas, TX, United States", "Remote - US", "US-TX-Fort Worth",
                    "Albuquerque, New Mexico", "Greater Seattle Area", "", "3 Locations",
                    "Vancouver, WA", "Paris, TX", "San Francisco",
                    " Palo Alto, CA; Asia; Canada; Europe; Remote International",
                    "Boston, MA; Mountain View, CA; Toronto, ON"]:
            self.assertTrue(is_us_location(loc), loc)

    def test_foreign(self):
        for loc in ["Toronto, ON, CA", "Bangalore, India", "Munich, Germany", "Guadalajara, Mexico",
                    "London, UK", "Abu Dhabi, United Arab Emirates; London, England, United Kingdom",
                    "Auckland, NZ", "Abuja, Nigeria", "Asia Pacific", "Remote International",
                    "Pune", "Bristol; Cheltenham; London"]:
            self.assertFalse(is_us_location(loc), loc)

    def test_country_field_wins(self):
        self.assertTrue(is_us_location("Anywhere", "United States of America"))
        self.assertTrue(is_us_location("Anywhere", "US"))
        self.assertFalse(is_us_location("Springfield", "Canada"))


class EvaluateTests(unittest.TestCase):
    def test_new_grad_match(self):
        v = evaluate(job("Mechanical Engineer I", ME_DEGREE + "0-2 years of experience.",
                         location="Dallas, TX"), FILTERS)
        self.assertTrue(v.match)
        self.assertIn("Entry-level title", v.level_note)

    def test_unlabelled_title_with_low_experience(self):
        v = evaluate(job("Mechanical Design Engineer", ME_DEGREE + "1+ years of experience."), FILTERS)
        self.assertTrue(v.match)

    def test_unlabelled_title_with_high_experience(self):
        v = evaluate(job("Mechanical Design Engineer", ME_DEGREE + "5+ years of experience."), FILTERS)
        self.assertFalse(v.match)
        self.assertIn("5+", v.reason)

    def test_entry_title_with_high_experience(self):
        v = evaluate(job("Associate Mechanical Engineer", ME_DEGREE + "6+ years of experience."),
                     FILTERS)
        self.assertFalse(v.match)

    def test_wrong_degree(self):
        v = evaluate(job("Engineer I", "Bachelor's degree in Chemical Engineering."), FILTERS)
        self.assertFalse(v.match)

    def test_internship_employment_type(self):
        v = evaluate(job("Mechanical Engineer", ME_DEGREE, employment_type="Intern"), FILTERS)
        self.assertFalse(v.match)

    def test_foreign_location(self):
        v = evaluate(job("Mechanical Engineer I", ME_DEGREE, location="Bangalore, India"), FILTERS)
        self.assertFalse(v.match)

    def test_unclear_level(self):
        v = evaluate(job("Mechanical Engineer", ME_DEGREE), FILTERS)
        self.assertTrue(v.match)
        self.assertIn("unclear", v.level_note)
        strict = dict(FILTERS, include_unclear_level=False)
        self.assertFalse(evaluate(job("Mechanical Engineer", ME_DEGREE), strict).match)


class TextTests(unittest.TestCase):
    def test_double_escaped_html(self):
        raw = "&lt;p&gt;Bachelor&amp;#39;s degree&lt;/p&gt;&lt;ul&gt;&lt;li&gt;2+ years&lt;/li&gt;&lt;/ul&gt;"
        self.assertEqual(html_to_text(raw), "Bachelor's degree\n2+ years")


if __name__ == "__main__":
    unittest.main()
