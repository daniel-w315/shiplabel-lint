import argparse
import json
import sys

from .linter import lint_stream, load_carrier_patterns


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="shiplabel-lint",
        description="Check a shipping label manifest CSV for problems, one row at a time.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="path to manifest CSV, or - for stdin (default: -)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format: 'text' for human-readable lines, 'json' for a single "
        "JSON array of findings (default: text)",
    )
    parser.add_argument(
        "--rules",
        metavar="PATH",
        help="path to an INI file with a [carriers] section mapping carrier "
        "name to tracking number regex, replacing the built-in patterns",
    )
    args = parser.parse_args(argv)

    if args.rules:
        try:
            carrier_patterns = load_carrier_patterns(args.rules)
        except (OSError, ValueError) as exc:
            print(f"shiplabel-lint: {exc}", file=sys.stderr)
            sys.exit(2)
    else:
        carrier_patterns = None

    if args.path == "-":
        exit_code = _run(sys.stdin, "<stdin>", args.format, carrier_patterns)
    else:
        with open(args.path, newline="") as f:
            exit_code = _run(f, args.path, args.format, carrier_patterns)

    sys.exit(exit_code)


def _run(fileobj, source_name, output_format, carrier_patterns):
    if output_format == "json":
        return _run_json(fileobj, source_name, carrier_patterns)
    return _run_text(fileobj, source_name, carrier_patterns)


def _run_text(fileobj, source_name, carrier_patterns):
    had_error = False
    for finding in lint_stream(fileobj, carrier_patterns):
        print(f"{source_name}:{finding.line}: {finding.level}: {finding.code} {finding.message}")
        if finding.level == "error":
            had_error = True
    return 1 if had_error else 0


def _run_json(fileobj, source_name, carrier_patterns):
    had_error = False
    findings = []
    for finding in lint_stream(fileobj, carrier_patterns):
        findings.append(
            {
                "source": source_name,
                "line": finding.line,
                "code": finding.code,
                "level": finding.level,
                "message": finding.message,
            }
        )
        if finding.level == "error":
            had_error = True
    print(json.dumps(findings))
    return 1 if had_error else 0


if __name__ == "__main__":
    main()
