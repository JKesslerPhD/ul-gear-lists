"""Text normalization shared by the classifier and the analysis scripts."""
import re
import unicodedata

# Community abbreviations and spelling variants -> canonical brand text.  Deliberately conservative:
# "or" (Outdoor Research) and "bd" (Black Diamond) are left out because they are ordinary tokens.
BRAND_ALIASES = {
    "ee": "enlightened equipment", "gg": "gossamer gear", "hmg": "hyperlite mountain gear",
    "mld": "mountain laurel designs", "s2s": "sea to summit", "sts": "sea to summit",
    "ugq": "underground quilts", "wm": "western mountaineering", "tnf": "the north face",
    "hg": "hammock gear", "bpw": "bear paw wilderness designs",
    "thermarest": "therm a rest", "therma rest": "therm a rest", "therm-a-rest": "therm a rest",
    "palante": "palante packs", "zpak": "zpacks", "z packs": "zpacks", "hyperlite": "hyperlite mountain gear",
    "sixmoondesigns": "six moon designs", "mountainlaurel": "mountain laurel designs",
}
_ABBREV = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(BRAND_ALIASES, key=len, reverse=True)) + r")\b")

_WEIGHT = re.compile(
    r":\s*[\d.,]+\s*(oz|lb|kg|g)\b|[\d.,]+\s*(oz|lb|kg|g)\b|\bx\s*\d+\b|\(\s*[\d.,]+\s*(oz|lb|kg|g)\s*\)",
    re.IGNORECASE,
)


def expand_brands(text):
    return _ABBREV.sub(lambda m: BRAND_ALIASES[m.group(0)], text)


def normalize_text(name, desc=""):
    """Lowercase name + description, drop weights/quantities, expand brand abbreviations."""
    t = unicodedata.normalize("NFKD", f"{name} {desc}".strip())
    t = "".join(c for c in t if ord(c) < 0x2000 or c == " ")
    t = _WEIGHT.sub(" ", t).lower()
    t = re.sub(r"[#\-=+*|_]{2,}", " ", t)
    return expand_brands(re.sub(r"\s+", " ", t).strip())
