"""Export the API contract without settings, network access or a running server."""

import argparse
import json
from pathlib import Path

from pulso_api.main import create_app


def export(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("apps/api/openapi.json"))
    export(parser.parse_args().out)


if __name__ == "__main__":
    main()
