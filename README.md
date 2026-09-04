# shiplabel-lint

Checks a shipping label manifest CSV for rows that will fail when they hit
the carrier's label API or the printer, and tells you which line each
problem is on.

## The problem

A manifest is a CSV export from a warehouse system: one row per package,
with a tracking number, carrier, weight, and destination address. These get
handed off in batches, sometimes tens of thousands of rows at once, to
whatever prints the actual labels. When row 40,000 has a zero weight or a
tracking number that got truncated by a spreadsheet edit, you usually find
out partway through a print run instead of before it starts.

This tool reads the manifest once, row by row, and reports every problem it
finds along with the line number, so you can fix the source data before it
goes anywhere near a printer or a carrier API.

It's built to stream: it never reads the whole file into memory, so it works
the same way on a 50-row test file and a half-million-row nightly export.

## Expected columns

At minimum a manifest needs:

- `tracking_number`
- `carrier` (`ups`, `fedex`, `usps`, or `dhl`)
- `weight_oz`
- `dest_postal`

Extra columns (`service_level`, `dest_country`, ...) are allowed and
ignored. If `length_in`, `width_in`, and `height_in` are all present, they're
used to flag oversize packages and packages that will be billed on
dimensional weight instead of actual weight.

## Usage

```
$ python -m shiplabel_lint.cli examples/sample.csv
examples/sample.csv:2: warning: W031 dimensional weight (49.7oz) exceeds actual weight (32.0oz) and may be used for billing instead
examples/sample.csv:3: error: E010 missing tracking number
examples/sample.csv:3: warning: W031 dimensional weight (27.6oz) exceeds actual weight (16.0oz) and may be used for billing instead
examples/sample.csv:4: warning: W031 dimensional weight (96.7oz) exceeds actual weight (48.0oz) and may be used for billing instead
examples/sample.csv:5: error: E012 duplicate tracking number '1Z999AA10123456784'
examples/sample.csv:5: warning: W031 dimensional weight (49.7oz) exceeds actual weight (20.0oz) and may be used for billing instead
examples/sample.csv:6: error: E011 tracking number '123' does not match expected format for fedex
examples/sample.csv:6: error: E022 weight must be greater than zero
examples/sample.csv:6: warning: W031 dimensional weight (115.1oz) exceeds actual weight (0.0oz) and may be used for billing instead
```

Exit code is 1 if any errors were found, 0 otherwise (warnings alone don't
fail the check). Pass `-` or nothing to read from stdin:

```
$ cat examples/sample.csv | python -m shiplabel_lint.cli
```

Pass `--format json` to get a single JSON array of findings instead, for
feeding into a CI step:

```
$ python -m shiplabel_lint.cli --format json examples/sample.csv
[{"source": "examples/sample.csv", "line": 3, "code": "E010", "level": "error", "message": "missing tracking number"}, ...]
```

## Checks

| Code | Meaning |
| --- | --- |
| E001 | manifest is missing a required column |
| E010 | row has no tracking number |
| E011 | tracking number doesn't match the expected format for its carrier |
| E012 | tracking number appears more than once in the manifest |
| E020 | row has no weight |
| E021 | weight isn't a number |
| E022 | weight is zero or negative |
| E023 | length_in/width_in/height_in given for a row but not all three |
| E024 | a dimension isn't a number |
| E025 | a dimension is zero or negative |
| E030 | row has no destination postal code |
| E031 | destination postal code doesn't look like a valid US/CA code |
| W010 | carrier isn't one this tool knows how to validate |
| W020 | weight is above the typical single-package carrier limit |
| W030 | package is oversize (longest side over 108in, or length+girth over 130in) |
| W031 | dimensional weight exceeds actual weight and may be used for billing |

## Using it as a library

```python
from shiplabel_lint import lint_stream

with open("manifest.csv", newline="") as f:
    for finding in lint_stream(f):
        print(finding.line, finding.code, finding.message)
```

`lint_stream` is a generator over an open file (or `sys.stdin`, or anything
else iterable line by line) — it pulls one row at a time and never holds the
rest of the file in memory.

No third-party dependencies, standard library only.

## Running the tests

```
$ python -m unittest discover -s tests
```
