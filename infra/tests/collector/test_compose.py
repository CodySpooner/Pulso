"""Compose config validation only: never connects to the Docker engine."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("profiles", [[], ["collector"], ["collector", "collector-tools"]])
def test_profile_config_and_image_environment_contract(profiles: list[str]) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Compose config unavailable (no Docker CLI)")
    result = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            ".env.example",
            "-f",
            "infra/docker-compose.yml",
            *(arg for profile in profiles for arg in ("--profile", profile)),
            "config",
            "--format",
            "json",
            "--no-env-resolution",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "COMPOSE_PROJECT_NAME": "pulso-config-test",
            "COMPOSE_PROFILES": "",
            "PG_PASSWORD": "fixture-only",
            "S3_ACCESS_KEY_ID": "fixture-only",
            "S3_SECRET_ACCESS_KEY": "fixture-only",
            "PULSO_SCHEDULER": "on",
            "COLLECTORS_LIVE": "on",
        },
        text=True,
        capture_output=True,
        check=True,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    expected = {"postgres", "redis", "s3"}
    if "collector" in profiles:
        expected |= {"worker", "worker-ops", "beat"}
    if "collector-tools" in profiles:
        expected.add("migrate")
    assert set(services) == expected
    assert services["postgres"]["image"] == "pgvector/pgvector:0.8.7-pg18-trixie"
    assert services["postgres"]["command"] == ["postgres", "-c", "dynamic_shared_memory_type=mmap"]
    assert services["postgres"]["volumes"][0]["target"] == "/var/lib/postgresql"
    for name in expected - {"migrate"}:
        assert services[name]["restart"] == "unless-stopped"
    for name in expected - {"postgres", "redis", "s3"}:
        service = services[name]
        assert len(service["env_file"]) == 1
        assert service["env_file"][0]["path"].endswith(".env.collector")
        assert service["env_file"][0]["format"] == "raw"
        assert "PULSO_SCHEDULER" not in service.get("environment", {})
        assert "COLLECTORS_LIVE" not in service.get("environment", {})
        assert all(dep["condition"] == "service_healthy" for dep in service["depends_on"].values())
    if "collector" in profiles:
        for name in ("worker", "worker-ops", "beat"):
            assert services[name]["build"]["dockerfile"] == "infra/docker/worker.Dockerfile"
            assert not any("concurrency" in arg for arg in (services[name].get("command") or []))
        assert services["worker"].get("command") is None  # P1-33 owns the image CMD.
        assert services["beat"]["volumes"][0]["target"] == "/home/pulso"
    if "collector-tools" in profiles:
        assert services["migrate"]["build"]["dockerfile"] == "infra/docker/api.Dockerfile"
        assert services["migrate"]["command"] == ["alembic", "-c", "alembic.ini", "upgrade", "head"]
        assert services["migrate"]["restart"] == "no"
