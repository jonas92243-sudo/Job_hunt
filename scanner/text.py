"""HTML to plain text conversion for job descriptions."""
import html
import re

_HIDDEN = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_BLOCK_TAGS = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|table|section)\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


def html_to_text(value):
    if not value:
        return ""
    # Greenhouse double-escapes its HTML, so unescape before and after stripping tags.
    text = html.unescape(value)
    text = _HIDDEN.sub(" ", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n", text)
    return text.strip()
