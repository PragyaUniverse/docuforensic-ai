#!/usr/bin/env python
"""Create or reset a reviewer login. The password is typed at a prompt, never passed as an argument."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import auth


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Again: "):
        print("The passwords don't match.")
        return 1
    try:
        auth.create_user(args.username, password)
    except ValueError as exc:
        print(exc)
        return 1
    print(f"Saved {args.username}. Set AUTH_ENABLED=true to require login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
