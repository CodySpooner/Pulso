import json
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

import httpx
import pytest

from spikes import shopify_probe
from spikes.shopify_probe import main, probe, retry_delay, seed_stores, store_origin

SEEDS = Path(__file__).resolve().parents[2] / "seeds/seed_v1.yaml"
CONTACT = "https://pulso.example/bot"


class Clock:
    now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def fixture_response(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /cart\n")
    if request.url.path == "/products.json":
        assert request.url.query == b"limit=1"
        if "if-none-match" in request.headers:
            assert request.headers["if-none-match"] == '"catalog-v1"'
            return httpx.Response(304)
        return httpx.Response(
            200,
            headers={"ETag": '"catalog-v1"'},
            json={"products": [{"handle": "test-product", "variants": [{"price": "12.00"}]}]},
        )
    if request.url.path == "/meta.json":
        return httpx.Response(200, json={"currency": "USD"})
    assert request.url.path == "/products/test-product.js"
    return httpx.Response(200, json={"variants": [{"inventory_quantity": 0}]})


def run_probe(
    respond: Callable[[httpx.Request], httpx.Response] = fixture_response,
    stores: list[str] | None = None,
) -> tuple[str, list[httpx.Request], list[float]]:
    clock = Clock()
    requests: list[httpx.Request] = []
    times: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == f"PulsoBot/0.1 (+{CONTACT})"
        requests.append(request)
        times.append(clock())
        clock.sleep(0.125)
        return respond(request)

    report = probe(
        stores or ["shop.example"],
        CONTACT,
        transport=httpx.MockTransport(handle),
        sleep=clock.sleep,
        clock=clock,
    )
    return report, requests, times


def test_sequence_spacing_304_currency_inventory_and_latency() -> None:
    report, requests, times = run_probe(stores=["one.example", "two.example"])
    assert [r.url.path for r in requests[:5]] == [
        "/robots.txt",
        "/products.json",
        "/products.json",
        "/meta.json",
        "/products/test-product.js",
    ]
    assert len(requests) == 10
    assert all(b - a >= 3 for a, b in pairwise(times))
    assert "| 304 | - | yes |" in report
    assert "| USD |" in report
    assert "| public JSON | yes | 125.0 |" in report
    assert "10/50 requests" in report


def test_request_cap_is_global() -> None:
    report, requests, _ = run_probe(stores=[f"shop{i}.example" for i in range(12)])
    assert len(requests) == 50
    assert requests[-1].url.host == "shop9.example"
    assert "Request cap reached; run stopped" in report


@pytest.mark.parametrize("status", [429, 430, 403])
@pytest.mark.parametrize("path", ["/robots.txt", "/products.json", "/meta.json"])
def test_block_stops_store_without_retry_and_honours_retry_after(status: int, path: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "blocked.example" and request.url.path == path:
            return httpx.Response(status, headers={"Retry-After": "60"})
        return fixture_response(request)

    report, requests, times = run_probe(respond, ["blocked.example", "other.example"])
    blocked = [r for r in requests if r.url.host == "blocked.example"]
    assert blocked[-1].url.path == path
    assert sum(r.url.path == path for r in blocked) == 1
    assert times[len(blocked)] - times[len(blocked) - 1] >= 60
    assert f"| {status} | 60 |" in report
    assert "store stopped; no retry" in report


@pytest.mark.parametrize(
    "rule,path",
    [
        ("/products.json", "/products.json"),
        ("/meta.json", "/meta.json"),
        ("/products/*.js$", "/products/test-product.js"),
        ("/*?limit=1", "/products.json"),
    ],
)
def test_robots_disallow_is_recorded_without_request(rule: str, path: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=f"User-agent: *\nDisallow: {rule}\n")
        return fixture_response(request)

    report, requests, _ = run_probe(respond)
    assert all(r.url.path != path for r in requests)
    assert "robots.txt Disallow" in report


def test_robots_specific_agent_allow_and_delay() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /\n"
                "User-agent: PulsoBot\nDisallow: /products/\n"
                "Allow: /products/test-product.js\nCrawl-delay: 7\n",
            )
        return fixture_response(request)

    _, requests, times = run_probe(respond)
    assert len(requests) == 5
    assert all(b - a >= 7 for a, b in pairwise(times))


@pytest.mark.parametrize("status", [302, 401, 500])
def test_unavailable_robots_stops_without_following_redirects(status: int) -> None:
    report, requests, _ = run_probe(
        lambda r: httpx.Response(
            status, headers={"Location": "https://elsewhere.example/robots.txt"}
        )
    )
    assert len(requests) == 1
    assert "robots unavailable; store stopped" in report


def test_password_redirect_is_observed_without_following() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products.json":
            return httpx.Response(302, headers={"Location": "/password"})
        return fixture_response(request)

    report, requests, _ = run_probe(respond)
    assert len(requests) == 2
    assert "| password |" in report


@pytest.mark.parametrize(
    "payload", [{}, {"products": []}, {"products": [None]}, {"products": [{"handle": "../cart"}]}]
)
def test_missing_etag_and_handle_skip_dependent_probes(payload: dict[str, object]) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products.json":
            return httpx.Response(200, json=payload)
        return fixture_response(request)

    report, requests, _ = run_probe(respond)
    assert len(requests) == 3
    assert "no usable ETag" in report
    assert "no usable first handle" in report


def test_transport_failure_counts_toward_cap_and_is_recorded() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fixture failure", request=request)

    report, requests, times = run_probe(respond, [f"shop{i}.example" for i in range(60)])
    assert len(requests) == 50
    assert all(b - a >= 3 for a, b in pairwise(times))
    assert "ConnectError" in report


def test_contact_required_before_any_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PULSO_BOT_CONTACT", raising=False)
    with pytest.raises(SystemExit, match="2"):
        main(["shop.example"])
    with pytest.raises(ValueError, match="PULSO_BOT_CONTACT"):
        probe(["shop.example"], "")


@pytest.mark.parametrize(
    "store",
    [
        "http://shop.example",
        "https://user:pass@shop.example",
        "shop.example/cart",
        "shop.example?token=secret",
    ],
)
def test_invalid_store_refused(store: str) -> None:
    with pytest.raises(ValueError):
        store_origin(store)


def test_seed_file_is_json_compatible_yaml_with_all_entries_disabled() -> None:
    text = SEEDS.read_text(encoding="utf-8")
    data = json.loads("\n".join(line for line in text.splitlines() if not line.startswith("#")))
    assert [len(data[key]) for key in ("stores", "cj_categories", "keywords")] == [30, 10, 50]
    assert all(
        row["enabled"] is False
        for key in ("stores", "cj_categories", "keywords")
        for row in data[key]
    )
    assert all(row["geo"] == "US" and row["tz"] == 0 for row in data["keywords"])
    assert seed_stores(SEEDS)[0] == "https://sageandsill.com"
    assert "pending owner approval (DEC-011)" in text


def test_retry_after_http_date_and_invalid_values() -> None:
    assert retry_delay("Fri, 01 Jan 2100 00:00:00 GMT") > 0
    assert retry_delay("Sun, 06 Nov 1994 08:49:37 GMT") == 0
    assert retry_delay("invalid") == 0


@pytest.mark.parametrize("status", [200, 404])
def test_non_304_etag_result_and_missing_inventory_are_explicit(status: int) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if "if-none-match" in request.headers:
            return httpx.Response(status, json={"products": []})
        if request.url.path.endswith(".js"):
            return httpx.Response(200, json={"variants": [{}]})
        return fixture_response(request)

    report, _, _ = run_probe(respond)
    assert f"| {status} | - | no |" in report
    assert "| public JSON | no |" in report
    if status == 404:
        assert "headless/unavailable (possible)" in report


def test_duplicate_stores_are_never_reprobed() -> None:
    _, requests, _ = run_probe(stores=["shop.example", "https://SHOP.example/"])
    assert len(requests) == 5


def test_cli_blocks_worktrees_before_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PULSO_BOT_CONTACT", CONTACT)
    monkeypatch.setattr(shopify_probe, "__file__", str(tmp_path / "infra/scripts/spikes/probe.py"))
    (tmp_path / ".git").write_text("gitdir: example", encoding="utf-8")
    with pytest.raises(SystemExit, match="2"):
        main(["shop.example"])


def test_cli_seed_input_file_and_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PULSO_BOT_CONTACT", CONTACT)
    monkeypatch.setattr(shopify_probe, "__file__", str(tmp_path / "infra/scripts/spikes/probe.py"))
    clock = Clock()

    def offline_probe(stores: list[str], contact: str) -> str:
        return probe(
            stores,
            contact,
            transport=httpx.MockTransport(fixture_response),
            sleep=clock.sleep,
            clock=clock,
        )

    monkeypatch.setattr(shopify_probe, "probe", offline_probe)
    output = tmp_path / "spike.md"
    main(["--seed-file", str(SEEDS), "--out", str(output)])
    assert "50/50 requests" in output.read_text(encoding="utf-8")
    main(["shop.example"])
    assert "5/50 requests" in capsys.readouterr().out
