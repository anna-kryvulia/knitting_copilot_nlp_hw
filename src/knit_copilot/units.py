"""Unit normalisation: everything in the system is metric (mm, cm, m, g, per 10 cm).

Purpose: convert imperial values found in patterns and Ravelry data.
Input: numbers or short strings ("US 7", "5.5 in"). Output: metric numbers, rounded for display.
"""

import re

INCH_CM = 2.54
YARD_M = 0.9144
GAUGE_4IN_CM = 4 * INCH_CM  # 10.16 cm

# US knitting needle sizes → mm (Craft Yarn Council needle conversion)
US_NEEDLE_MM: dict[str, float] = {
    "0": 2.0, "1": 2.25, "1.5": 2.5, "2": 2.75, "2.5": 3.0, "3": 3.25, "4": 3.5, "5": 3.75,
    "6": 4.0, "7": 4.5, "8": 5.0, "9": 5.5, "10": 6.0, "10.5": 6.5, "10.75": 7.0, "11": 8.0,
    "13": 9.0, "15": 10.0, "17": 12.0, "19": 15.0, "35": 19.0, "50": 25.0,
}


def inch_to_cm(inches: float) -> float:
    return round(inches * INCH_CM, 1)


def yards_to_m(yards: float) -> int:
    return round(yards * YARD_M)


def gauge_per_4in_to_10cm(stitches: float) -> float:
    """Stitches over 4 in (10.16 cm) → stitches over 10 cm."""
    return round(stitches * 10 / GAUGE_4IN_CM, 1)


def gauge_to_per_10cm(stitches: float, divisor: float, unit: str = "in") -> float:
    """Ravelry style gauge: `stitches` over `divisor` inches (or cm) → per 10 cm."""
    length_cm = divisor * INCH_CM if unit == "in" else divisor
    return round(stitches * 10 / length_cm, 1)


def us_needle_to_mm(size: str | float) -> float:
    """'US 7', '7', 10.5 → mm. Raises KeyError for unknown sizes."""
    key = re.sub(r"(?i)^\s*us\s*", "", str(size)).strip()
    key = key.rstrip("0").rstrip(".") if "." in key else key
    return US_NEEDLE_MM[key]


def fraction_to_float(text: str) -> float:
    """'5 ½', '5 1/2', '5.5' → 5.5"""
    text = text.replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4").strip()
    total = 0.0
    for part in text.split():
        if "/" in part:
            num, den = part.split("/")
            total += float(num) / float(den)
        else:
            total += float(part)
    return total
