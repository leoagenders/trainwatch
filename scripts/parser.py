"""
Defect detector announcement parser.

Standard CSX detector announcement structure:
  "CSX detector, milepost <MP>, [track <N>,] no defects, repeat no defects,
   total axles <N>, train length <N> feet, speed <N> miles per hour,
   temperature <N> degrees, detector out."

Whisper output is unreliable on numbers — we use multiple strategies and
snap to plausible values where possible.
"""
import re

KNOWN_DETECTORS = [3.0, 17.4, 33.7, 46.8, 58.2]
SNAP_TOLERANCE = 1.5


def _snap_to_known(value):
    if value is None:
        return None
    best = None
    best_dist = SNAP_TOLERANCE + 1
    for known in KNOWN_DETECTORS:
        d = abs(value - known)
        if d < best_dist:
            best = known
            best_dist = d
    if best is not None and best_dist <= SNAP_TOLERANCE:
        return best
    return value


def _normalize_milepost(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    digit_groups = re.findall(r"\d+", s)
    if not digit_groups:
        return None

    candidates = set()

    if "." in s:
        try:
            m = re.search(r"(\d+\.\d+)", s)
            if m:
                candidates.add(float(m.group(1)))
        except ValueError:
            pass
        try:
            cleaned = re.sub(r"[^\d\.]", "", s)
            if cleaned.count(".") > 1:
                last_dot = cleaned.rfind(".")
                cleaned = cleaned[:last_dot].replace(".", "") + cleaned[last_dot:]
            candidates.add(float(cleaned))
        except (ValueError, IndexError):
            pass

    all_digits = "".join(digit_groups)
    if len(all_digits) >= 2:
        try:
            candidates.add(float(all_digits[:-1] + "." + all_digits[-1:]))
        except ValueError:
            pass

    if len(digit_groups) >= 2:
        try:
            int_part = digit_groups[0]
            frac_part = "".join(digit_groups[1:])
            candidates.add(float(f"{int_part}.{frac_part}"))
        except ValueError:
            pass

    if len(digit_groups) >= 3:
        try:
            int_part = digit_groups[0] + digit_groups[1]
            frac_part = digit_groups[2]
            candidates.add(float(f"{int_part}.{frac_part}"))
        except ValueError:
            pass

    try:
        candidates.add(float(all_digits))
    except ValueError:
        pass

    for c in candidates:
        snapped = _snap_to_known(c)
        if snapped in KNOWN_DETECTORS:
            return snapped

    sorted_candidates = sorted(candidates)
    return sorted_candidates[0] if sorted_candidates else None


def _extract_milepost(text):
    pattern = (
        r"milepost[\s,:]*"
        r"([\d\.,\s]+?)"
        r"(?=\s*(?:no|track|total|speed|temp|defect|length|train|axle|repeat|over|detector|$))"
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return _normalize_milepost(m.group(1))
    pattern2 = r"\bm\.?\s*p\.?\s*([\d\.,\s]+)"
    m = re.search(pattern2, text, re.IGNORECASE)
    if m:
        return _normalize_milepost(m.group(1))
    return None


def _normalize_axle_count(raw):
    """
    Whisper outputs axles in many forms:
      "32" -> 32
      "268" -> 268
      "6.2" -> 62 (Whisper decimal-mangled an integer)
      "4, 8, 0" -> 480
      "2, 1, 2" -> 212
      "1,200" -> 1200
    Real freight axle counts: ~50 (short local) to ~1000+ (long unit train).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    # Extract all digit runs
    digit_groups = re.findall(r"\d+", s)
    if not digit_groups:
        return None
    # Concatenate all digits
    all_digits = "".join(digit_groups)
    if not all_digits:
        return None
    try:
        val = int(all_digits)
    except ValueError:
        return None
    # Plausibility check: real axle counts are 20-2000
    if 20 <= val <= 2000:
        return val
    # Unreasonably small (e.g., "2" alone) — probably mis-parsed
    if val < 20:
        return None
    # Unreasonably large (e.g., "62000") — Whisper concatenated extra digits
    # Try truncating to 3-4 digits
    if val > 2000:
        for length in (4, 3):
            if len(all_digits) > length:
                try:
                    truncated = int(all_digits[:length])
                    if 20 <= truncated <= 2000:
                        return truncated
                except ValueError:
                    pass
        return None
    return val


def _extract_axles(text):
    """
    Capture text after 'axle'/'axles'/"axle's" up to the next keyword or end.
    Tolerates apostrophes, commas, decimal points.
    """
    pattern = (
        r"axle(?:s|'s|\u2019s)?[\s,:]+"
        r"([\d\.\,\s]+?)"
        r"(?=\s*(?:detector|length|train|speed|temp|over|repeat|defect|track|out|\.|$))"
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return _normalize_axle_count(m.group(1))
    return None


def _extract_int_with_unit(text, unit_pattern):
    """Extract an integer followed by a unit keyword like 'feet' or 'mph'."""
    pattern = rf"([\d,\s]+?)\s*(?:{unit_pattern})"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        if digits:
            try:
                val = int(digits)
                return val
            except ValueError:
                return None
    return None


def _extract_int(pattern, text):
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def parse_detector(transcript):
    if not transcript:
        return None
    lower = transcript.lower()
    if "detector" not in lower:
        return None

    railroad = "CSX"
    if "norfolk southern" in lower:
        railroad = "NS"

    milepost = _extract_milepost(transcript)
    axle_count = _extract_axles(transcript)

    # Train length: prefer "X feet"
    train_length = _extract_int_with_unit(transcript, r"feet|ft|foot")
    if train_length is not None and not (100 <= train_length <= 25000):
        train_length = None  # implausible

    # Speed
    speed = _extract_int(r"speed[\s,:]+(\d{1,3})", transcript)
    if speed is None:
        m = re.search(r"(\d{1,3})\s*(?:miles per hour|mph)", lower)
        if m:
            speed = int(m.group(1))
    if speed is not None and not (5 <= speed <= 90):
        speed = None  # implausible

    # Temperature
    temp = _extract_int(r"temp(?:erature)?[\s,:]+(-?\d{1,3})", transcript)
    if temp is None:
        m = re.search(r"(-?\d{1,3})\s*degrees?", lower)
        if m:
            temp = int(m.group(1))
    if temp is not None and not (-20 <= temp <= 130):
        temp = None  # implausible

    defects = 0
    if re.search(r"\bdefect(s)?\b", lower):
        if not re.search(r"no\s+defect", lower):
            defects = 1

    return {
        "railroad": railroad,
        "milepost": milepost,
        "axle_count": axle_count,
        "train_length_feet": train_length,
        "speed_mph": speed,
        "temperature_f": temp,
        "defects_detected": defects,
        "raw_text": transcript,
    }


if __name__ == "__main__":
    real_world_tests = [
        # Actual transcripts from the live system:
        "CSX detector, milepost 46.8. CSX detector, milepost 46.8, no defects, repeat no defects. Total axle 6.2. Detector out.",
        "CXX detector, milepost 46.8, no defects, repeat no defects. Total axles 32.",
        "CSX detector, milepost 46.8, no defects. Repeat no defects. Total axle's 268. Detector out.",
        "CXX detector, milepost 46.8.",
        "CSX detector, milepost 46.8, no defects, total axles 212, train length 6800 feet, speed 47 miles per hour, temperature 72 degrees.",
        "Detector, milepost 33.7, no defects, total axles 360, length 8500 feet, speed 42 mph, temperature 68 degrees.",
    ]
    for t in real_world_tests:
        print(f"\nInput: {t[:80]}{'...' if len(t) > 80 else ''}")
        r = parse_detector(t)
        if r:
            print(f"  Milepost: {r.get('milepost')}")
            print(f"  Axles:    {r.get('axle_count')}")
            print(f"  Length:   {r.get('train_length_feet')}")
            print(f"  Speed:    {r.get('speed_mph')}")
            print(f"  Temp:     {r.get('temperature_f')}")
            print(f"  Defects:  {r.get('defects_detected')}")
