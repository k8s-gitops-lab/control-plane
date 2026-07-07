from __future__ import annotations

import sys

from platform_checks import load_values


def shell_quote(value: object) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def main() -> None:
    for key, value in load_values().items():
        print(f"export {key}={shell_quote(value)}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        sys.exit(f"Missing platform.yml key: {exc}")
