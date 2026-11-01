"""Command-line interface for local dataset inspection."""

import argparse
import json
import sys

from finlabel.profile import inspect_csv


def main() -> int:
    parser = argparse.ArgumentParser(prog="finlabel")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="inspect a local CSV without printing rows")
    inspect.add_argument("csv_path", help="path to a UTF-8 CSV file")
    inspect.add_argument("--target", help="optional target column for class counts")
    args = parser.parse_args()

    try:
        profile = inspect_csv(args.csv_path, target=args.target)
    except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        print("finlabel: {}".format(exc), file=sys.stderr)
        return 2

    print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
