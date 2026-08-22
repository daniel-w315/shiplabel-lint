"""Row-by-row checks for shipping label manifest CSVs.

A manifest is a CSV export from a warehouse or shipping system: one row per
label, with a tracking number, carrier, weight, and destination address.
Everything here reads the input a row at a time so a manifest with a few
hundred thousand rows can be checked without holding the file in memory.
"""

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


@dataclass
class Finding:
    line: int
    code: str
    level: str  # "error" or "warning"
    message: str


def lint_stream(fileobj):
    """Yield Finding objects for a manifest, reading one row at a time.

    fileobj is any iterable of lines (an open file, sys.stdin, ...). Rows
    are never buffered into a list, so this is safe to run against input
    larger than available memory.
    """
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
        yield from _lint_row(row, col_index, line_no, seen_tracking)


def _lint_row(row, col_index, line_no, seen_tracking):
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
        pattern = CARRIER_TRACKING_PATTERNS.get(carrier)
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

    if not postal:
        yield Finding(line_no, "E030", "error", "missing destination postal code")
    elif not _looks_like_postal(postal):
        yield Finding(
            line_no, "E031", "error", f"destination postal code '{postal}' does not look valid"
        )


def _looks_like_postal(value):
    return bool(US_ZIP.match(value)) or bool(CA_POSTAL.match(value))
