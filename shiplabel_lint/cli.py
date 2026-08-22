import argparse
import sys

from .linter import lint_stream


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
    args = parser.parse_args(argv)

    if args.path == "-":
        exit_code = _run(sys.stdin, "<stdin>")
    else:
        with open(args.path, newline="") as f:
            exit_code = _run(f, args.path)

    sys.exit(exit_code)


def _run(fileobj, source_name):
    had_error = False
    for finding in lint_stream(fileobj):
        print(f"{source_name}:{finding.line}: {finding.level}: {finding.code} {finding.message}")
        if finding.level == "error":
            had_error = True
    return 1 if had_error else 0


if __name__ == "__main__":
    main()
