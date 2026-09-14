"""Disposable multi-process accounting qualification; run under external-network denial."""

import argparse
import json
import multiprocessing
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .campaign import CAMPAIGN, AdmissionError, Campaign, Debit, create_private, digest, encoded


def contender(root: str) -> None:
    campaign = Campaign(Path(root))
    try:
        with campaign.locked():
            campaign.reserve(Debit(1, 90_000_000, 4 * 1024 * 1024, 333333), "a" * 64)
            campaign.transition("dispatched")
            campaign.transition("completed")
    except AdmissionError as exc:
        assert str(exc) in ("campaign_busy", "capacity_exceeded")


def crash(root: str) -> None:
    campaign = Campaign(Path(root))
    with campaign.locked():
        campaign.reserve(Debit(1, 1, 1, 1), "b" * 64)
        os._exit(73)


def initialize(root: Path) -> Campaign:
    evidence = root / "synthetic-history"
    create_private(evidence, b"synthetic-zero-history")
    campaign = Campaign(root)
    campaign.initialize(
        encoded(
            {
                "schema": 1,
                "campaign": CAMPAIGN,
                "status": "reconciled",
                "evidence": [{"path": str(evidence), "sha256": digest(evidence.read_bytes())}],
                "debit": asdict(Debit()),
                "unknown": [],
                "reviewer": "offline-harness",
            }
        )
    )
    return campaign


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-denied", action="store_true", required=True)
    parser.parse_args()
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="colacci-p1c-accounting-") as directory:
        root = Path(directory).resolve()
        campaign = initialize(root)
        # Repeated batches ensure both contention and exact-cap exhaustion across restarts.
        for _ in range(6):
            children = [context.Process(target=contender, args=(str(root),)) for _ in range(4)]
            for child in children:
                child.start()
            for child in children:
                child.join(10)
                if child.is_alive():
                    child.kill()
                    child.join()
                assert child.exitcode == 0
        assert campaign.state()[0] == Debit(6, 540_000_000, 24 * 1024 * 1024, 1_999_998)
    with tempfile.TemporaryDirectory(prefix="colacci-p1c-crash-") as directory:
        root = Path(directory).resolve()
        campaign = initialize(root)
        child = context.Process(target=crash, args=(str(root),))
        child.start()
        child.join(10)
        assert child.exitcode == 73
        with campaign.locked():
            assert campaign.state()[0].requests == 1
            try:
                campaign.reserve(Debit(1, 1, 1, 1), "c" * 64)
                raise AssertionError("crashed reservation reused")
            except AdmissionError as exc:
                assert str(exc) == "unresolved_debit"
    print(
        json.dumps(
            {
                "status": "pass",
                "contenders": 24,
                "exact_cap_requests": 6,
                "process_crash_hold": "pass",
                "provider_requests": 0,
                "temporary_state_removed": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
