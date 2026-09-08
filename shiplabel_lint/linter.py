"""Row-by-row checks for shipping label manifest CSVs.

A manifest is a CSV export from a warehouse or shipping system: one row per
label, with a tracking number, carrier, weight, and destination address.
Everything here reads the input a row at a time so a manifest with a few
hundred thousand rows can be checked without holding the file in memory.
"""

import configparser
import csv
import re
from dataclasses import dataclass

REQUIRED_COLUMNS = {"tracking_number", "carrier", "weight_oz", "dest_postal"}

# These are close approximations of the real formats, not the carriers'
# published specs. Good enough to catch obviously wrong values (empty
# fields, transposed digits, a UPS number in a FedEx column) without
# needing carrier API access to check.
CARRIER_TRACKING_PATTERNS = {
    "ups": re.compile(r"^1Z[0-9A-Z]{16}$"),
    "fedex": re.compile(r"^\d{12}$|^\d{15}$|^\d{20}$"),
    "usps": re.compile(r"^\d{20,22}$"),
    "dhl": re.compile(r"^\d{10}$|^\d{11}$"),
}

US_ZIP = re.compile(r"^\d{5}(-\d{4})?$")
CA_POSTAL = re.compile(r"^[A-Za-z]\d[A-Za-z] ?\d[A-Za-z]\d$")

# 150 lb, the single-package limit most ground services enforce before
# a shipment needs to be split or booked as freight.
MAX_WEIGHT_OZ = 2400

# Industry-standard dimensional weight divisor for inches/pounds. Carriers
# bill on the greater of actual weight and (L*W*H)/139, so a large, light
# box (styrofoam, an empty-looking mailer) can cost more than its scale
# weight suggests.
DIM_WEIGHT_DIVISOR = 139

# UPS/FedEx ground oversize thresholds: any single side over 108in, or
# length + girth (the longest side plus twice the sum of the other two)
# over 130in, gets billed as an oversize package regardless of weight.
MAX_DIMENSION_IN = 108
MAX_LENGTH_PLUS_GIRTH_IN = 130


@dataclass
class Finding:
    line: int
    code: str
    level: str  # "error" or "warning"
    message: str


def lint_stream(fileobj, carrier_patterns=None):
    """Yield Finding objects for a manifest, reading one row at a time.

    fileobj is any iterable of lines (an open file, sys.stdin, ...). Rows
    are never buffered into a list, so this is safe to run against input
    larger than available memory.

    carrier_patterns, if given, replaces CARRIER_TRACKING_PATTERNS (see
    load_carrier_patterns) so tracking number formats can be adjusted
    without editing this module.
    """
    if carrier_patterns is None:
        carrier_patterns = CARRIER_TRACKING_PATTERNS
    reader = csv.reader(fileobj)
    try:
        header = next(reader)
    except StopIteration:
        yield Finding(0, "E000", "error", "input is empty")
        return

    col_index = {name.strip().lower(): i for i, name in enumerate(header)}
    missing = REQUIRED_COLUMNS - col_index.keys()
    if missing:
        yield Finding(
            1,
            "E001",
            "error",
            f"missing required column(s): {', '.join(sorted(missing))}",
        )
        return

    seen_tracking = set()
    for line_no, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue
        yield from _lint_row(row, col_index, line_no, seen_tracking, carrier_patterns)


def _lint_row(row, col_index, line_no, seen_tracking, carrier_patterns):
    def get(name):
        idx = col_index.get(name)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()

    tracking = get("tracking_number")
    carrier = get("carrier").lower()
    weight_raw = get("weight_oz")
    postal = get("dest_postal")

    if not tracking:
        yield Finding(line_no, "E010", "error", "missing tracking number")
    else:
        pattern = carrier_patterns.get(carrier)
        if pattern is None:
            yield Finding(
                line_no,
                "W010",
                "warning",
                f"unknown carrier '{carrier}', cannot validate tracking number format",
            )
        elif not pattern.match(tracking):
            yield Finding(
                line_no,
                "E011",
                "error",
                f"tracking number '{tracking}' does not match expected format for {carrier}",
            )
        if tracking in seen_tracking:
            yield Finding(
                line_no, "E012", "error", f"duplicate tracking number '{tracking}'"
            )
        else:
            seen_tracking.add(tracking)

    weight = None
    if not weight_raw:
        yield Finding(line_no, "E020", "error", "missing weight")
    else:
        try:
            weight = float(weight_raw)
        except ValueError:
            yield Finding(
                line_no, "E021", "error", f"weight '{weight_raw}' is not a number"
            )
        else:
            if weight <= 0:
                yield Finding(line_no, "E022", "error", "weight must be greater than zero")
            elif weight > MAX_WEIGHT_OZ:
                yield Finding(
                    line_no,
                    "W020",
                    "warning",
                    f"weight {weight}oz exceeds typical carrier limit of {MAX_WEIGHT_OZ}oz",
                )

    yield from _lint_dimensions(get, line_no, weight)

    if not postal:
        yield Finding(line_no, "E030", "error", "missing destination postal code")
    elif not _looks_like_postal(postal):
        yield Finding(
            line_no, "E031", "error", f"destination postal code '{postal}' does not look valid"
        )


def _lint_dimensions(get, line_no, weight):
    """Check length_in/width_in/height_in, if the manifest has them.

    These columns are optional, so a manifest without them (or a row that
    leaves them all blank) is checked without this step. weight is the
    already-parsed weight_oz for the row, or None if it was missing/invalid.
    """
    raw = (get("length_in"), get("width_in"), get("height_in"))
    if not any(raw):
        return
    if not all(raw):
        yield Finding(
            line_no,
            "E023",
            "error",
            "incomplete dimensions: length_in, width_in, and height_in must all be given together",
        )
        return

    try:
        length, width, height = (float(v) for v in raw)
    except ValueError:
        yield Finding(line_no, "E024", "error", "dimensions must be numbers")
        return

    if length <= 0 or width <= 0 or height <= 0:
        yield Finding(line_no, "E025", "error", "dimensions must be greater than zero")
        return

    longest, mid, short = sorted((length, width, height), reverse=True)
    length_plus_girth = longest + 2 * (mid + short)
    if longest > MAX_DIMENSION_IN or length_plus_girth > MAX_LENGTH_PLUS_GIRTH_IN:
        yield Finding(
            line_no,
            "W030",
            "warning",
            f"package is oversize (longest side {longest}in, length+girth "
            f"{length_plus_girth}in exceeds carrier limits)",
        )

    dim_weight_oz = (length * width * height / DIM_WEIGHT_DIVISOR) * 16
    if weight is not None and dim_weight_oz > weight:
        yield Finding(
            line_no,
            "W031",
            "warning",
            f"dimensional weight ({dim_weight_oz:.1f}oz) exceeds actual weight "
            f"({weight}oz) and may be used for billing instead",
        )


def _looks_like_postal(value):
    return bool(US_ZIP.match(value)) or bool(CA_POSTAL.match(value))


def load_carrier_patterns(path):
    """Load a carrier -> tracking number regex mapping from a rules file.

    The file is an INI file with a single [carriers] section, e.g.:

        [carriers]
        ups = ^1Z[0-9A-Z]{16}$
        ontrac = ^[A-Z]\\d{7}$

    The returned dict replaces CARRIER_TRACKING_PATTERNS entirely rather
    than merging with it, so a rules file is a full statement of which
    carriers to validate and how.
    """
    parser = configparser.ConfigParser()
    with open(path) as f:
        parser.read_file(f)

    if not parser.has_section("carriers"):
        raise ValueError(f"{path}: missing [carriers] section")

    patterns = {}
    for carrier, raw_pattern in parser.items("carriers"):
        try:
            patterns[carrier] = re.compile(raw_pattern)
        except re.error as exc:
            raise ValueError(
                f"{path}: invalid regex for carrier '{carrier}': {exc}"
            ) from exc
    return patterns
