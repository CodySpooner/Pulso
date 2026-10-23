import argparse
import json
from pathlib import Path

from pulso_workers.celery_app import configuration


def test_worker_image_uses_one_consumer() -> None:
    dockerfile = Path(__file__).resolve().parents[3] / "infra/docker/worker.Dockerfile"
    command = next(
        line.removeprefix("CMD ")
        for line in dockerfile.read_text().splitlines()
        if line.startswith("CMD ")
    )
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--concurrency", "-c", type=int, default=configuration()["worker_concurrency"]
    )
    options, _ = parser.parse_known_args(json.loads(command))
    assert options.concurrency == 1
