"""Owner-run Shopify sanity spike; never run live from an agent worktree."""

import argparse
import html
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import astuple, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

MAX_REQUESTS = 20  # whole-run default (DEC-003, DEC-073, DEC-077)
HARD_MAX_REQUESTS = 50  # DEC-052 ceiling; --max-requests can only lower it
CATALOG = "/products.json?limit=1"


class StopStore(Exception):
    pass


class StopRun(Exception):
    pass


class RequestCap(Exception):
    pass


@dataclass
class Row:
    store: str
    path: str
    status: str = "skipped"
    retry_after: str = "-"
    etag_304: str = "-"
    currency: str = "unknown"
    state: str = "unknown"
    inventory: str = "-"
    latency_ms: str = "-"
    note: str = ""


def store_origin(store: str) -> str:
    url = urlsplit(store if "://" in store else f"https://{store}")
    if (
        url.scheme != "https"
        or not re.fullmatch(r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,63}", url.netloc)
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ValueError("Stores must be domains or HTTPS origins without credentials or paths")
    return f"https://{url.netloc.lower()}"


def seed_stores(path: Path) -> list[str]:
    """Read the JSON subset of YAML, allowing full-line header comments only."""
    data = json.loads(
        "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
    )
    if not isinstance(data, dict) or not isinstance(data.get("stores"), list):
        raise ValueError("Seed file must contain a stores list")
    stores = data["stores"]
    if not stores or any(
        not isinstance(s, dict) or not isinstance(s.get("domain"), str) for s in stores
    ):
        raise ValueError("Every seed store needs a domain")
    return [store_origin(s["domain"]) for s in stores]


def retry_delay(value: str) -> float:
    if value.isdigit():
        return float(value)
    try:
        return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except ValueError, TypeError, OverflowError:
        return 0


def json_object(response: httpx.Response | None) -> dict[str, Any]:
    if response is None or response.status_code != 200:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def probe(
    stores: list[str],
    contact: str,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    max_requests: int = MAX_REQUESTS,
) -> str:
    try:
        parts = urlsplit(contact.strip())
        public_url = parts.scheme in {"http", "https"} and bool(parts.hostname)
        public_url = public_url and parts.username is None and parts.password is None
    except ValueError:
        public_url = False
    if not public_url or not contact.isascii() or any(ord(c) < 32 for c in contact):
        raise ValueError("Set PULSO_BOT_CONTACT to the owner's public contact URL")
    if not 1 <= max_requests <= HARD_MAX_REQUESTS:
        raise ValueError(f"max_requests must be 1-{HARD_MAX_REQUESTS}")
    origins = list(dict.fromkeys(store_origin(s) for s in stores))
    user_agent = f"PulsoBot/0.1 (+{contact.strip()})"
    rows: list[Row] = []
    count, next_at, spacing = 0, clock(), 3.0
    with httpx.Client(
        headers={"User-Agent": user_agent},
        transport=transport,
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as client:

        def request(
            origin: str, path: str, robots: RobotFileParser | None = None, etag: str = ""
        ) -> httpx.Response | None:
            nonlocal count, next_at
            row = Row(origin, path)
            if robots is not None and not robots.can_fetch("PulsoBot", origin + path):
                row.note = "robots.txt Disallow"
                rows.append(row)
                return None
            if count >= max_requests:
                raise RequestCap(origin + path)
            rows.append(row)
            sleep(max(0, next_at - clock()))
            started = clock()
            count += 1
            try:
                response = client.get(
                    origin + path, headers={"If-None-Match": etag} if etag else {}
                )
            except httpx.HTTPError as exc:
                row.status, row.note = "error", type(exc).__name__
                raise StopStore from exc
            finally:
                row.latency_ms = f"{(clock() - started) * 1000:.1f}"
                next_at = clock() + spacing
            row.status = str(response.status_code)
            row.retry_after = response.headers.get("retry-after", "-")
            next_at = max(next_at, clock() + retry_delay(row.retry_after))
            row.etag_304 = ("yes" if response.status_code == 304 else "no") if etag else "-"
            location = response.headers.get("location", "")
            if "/password" in location.lower() or re.search(
                r"<input\b[^>]*\btype\s*=\s*[\"\x27]password[\"\x27]", response.text, re.I
            ):
                row.state = "password"
            elif path != "/robots.txt" and response.status_code == 404:
                row.state = "headless/unavailable (possible)"
            data = json_object(response)
            if isinstance(data.get("currency"), str):
                row.currency = data["currency"]
            products = data.get("products")
            if isinstance(products, list) or isinstance(data.get("variants"), list):
                row.state = "public JSON"
                items = products if isinstance(products, list) else [data]
                row.inventory = (
                    "yes"
                    if any(
                        isinstance(v, dict) and "inventory_quantity" in v
                        for p in items
                        if isinstance(p, dict) and isinstance(p.get("variants"), list)
                        for v in p["variants"]
                    )
                    else "no"
                )
            if response.has_redirect_location:
                row.note = "redirect not followed"
            if response.status_code in (429, 430, 403):
                row.note = "run stopped; no retry"
                raise StopRun(f"HTTP {response.status_code} from {origin}{path}")
            if row.state == "password":
                row.note = "store stopped; no retry"
                raise StopStore
            return response

        stop = "none; run finished"
        for origin in origins:
            try:
                spacing = 3.0
                robots_response = request(origin, "/robots.txt")
                assert robots_response is not None
                robots = RobotFileParser()
                if robots_response.status_code == 404:
                    robots.parse([])
                elif (
                    robots_response.status_code == 200
                    and not robots_response.text.lstrip().startswith("<")
                ):
                    robots.parse(robots_response.text.splitlines())
                else:
                    rows[-1].note = "robots unavailable; store stopped"
                    continue
                spacing = max(3.0, float(robots.crawl_delay("PulsoBot") or 0))
                rate = robots.request_rate("PulsoBot")
                if rate is not None:
                    if rate.requests == 0:
                        rows[-1].note = "robots request rate is zero; store skipped"
                        continue
                    spacing = max(spacing, rate.seconds / rate.requests)
                next_at = max(next_at, clock() + spacing)
                products_response = request(origin, CATALOG, robots)
                data = json_object(products_response)
                etag = (
                    products_response.headers.get("etag", "")
                    if products_response is not None
                    else ""
                )
                if etag and products_response is not None and products_response.status_code == 200:
                    request(origin, CATALOG, robots, etag)
                else:
                    rows.append(
                        Row(origin, CATALOG, note="conditional GET skipped: no usable ETag")
                    )
                request(origin, "/meta.json", robots)
                products = data.get("products")
                first = products[0] if isinstance(products, list) and products else {}
                handle = first.get("handle") if isinstance(first, dict) else None
                if isinstance(handle, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", handle):
                    request(origin, f"/products/{handle}.js", robots)
                else:
                    rows.append(Row(origin, "/products/<handle>.js", note="no usable first handle"))
            except StopStore:
                continue
            except RequestCap as exc:
                stop = f"request budget of {max_requests} spent; next request not sent ({exc})"
                break
            except StopRun as exc:
                stop = f"{exc}; whole run stopped, no retry"
                break
    reached = {row.store for row in rows}
    unreached = [origin for origin in origins if origin not in reached]
    headers = (
        "Store | Path | Status | Retry-After | ETag -> 304 | Currency | State | "
        "inventory_quantity | Latency ms | Note"
    )
    report = [
        "## Shopify home-PC spike",
        f"\nCaptured at {datetime.now(UTC).isoformat()}; {count}/{max_requests} requests; "
        f"{len(reached)}/{len(origins)} stores reached.",
        f"Stop reason: {stop}.",
        f"Not reached: {', '.join(unreached) or 'none'}.",
        "States are observations; 404 alone cannot establish a headless store.\n",
        f"| {headers} |",
        "| " + " | ".join(["---"] * 10) + " |",
    ]
    for row in rows:
        cells = [
            html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")
            for value in astuple(row)
        ]
        report.append("| " + " | ".join(cells) + " |")
    return "\n".join(report) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stores", nargs="*", help="store domains or HTTPS origins")
    parser.add_argument(
        "--seed-file", type=Path, help="draft seed_v1.yaml; diagnostic only, flags unchanged"
    )
    parser.add_argument("--out", type=Path, help="write Markdown results (default: stdout)")
    parser.add_argument(
        "--max-requests",
        type=int,
        default=MAX_REQUESTS,
        help=f"whole-run request budget, 1-{HARD_MAX_REQUESTS} (default {MAX_REQUESTS})",
    )
    args = parser.parse_args(argv)
    contact = os.environ.get("PULSO_BOT_CONTACT", "")
    if not contact.strip():
        parser.error("PULSO_BOT_CONTACT is required; owner chooses a public contact URL")
    if bool(args.stores) == bool(args.seed_file):
        parser.error("provide store domains OR --seed-file")
    if args.out and not args.out.parent.is_dir():
        parser.error("--out directory must exist before any request is sent")
    if (Path(__file__).resolve().parents[3] / ".git").is_file():
        parser.error(
            "Live probes are forbidden in linked worktrees; owner runs from C:\\dev\\pulso"
        )
    try:
        stores = seed_stores(args.seed_file) if args.seed_file else args.stores
        report = probe(stores, contact, max_requests=args.max_requests)
        if args.out:
            args.out.write_text(report, encoding="utf-8", newline="\n")
        else:
            print(report, end="")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
