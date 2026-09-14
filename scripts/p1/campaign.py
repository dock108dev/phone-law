"""Append-only campaign accounting. No network, credentials, refunds or implicit creation."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CAMPAIGN = "colacci-law-p1-20260913"


class AdmissionError(Exception):
    """Fixed local diagnostic code."""


def encoded(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def private_directory(path: Path) -> None:
    if not path.is_absolute() or path != path.resolve():
        raise AdmissionError("unsafe_path")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise AdmissionError("unsafe_directory")
    # Ancestors may be traversable but must not be writable by another user,
    # except OS-owned sticky temporary roots (isolated test directories).
    for parent in path.parents:
        info = parent.stat()
        if info.st_uid not in (0, os.getuid()) or (
            info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
        ):
            raise AdmissionError("unsafe_ancestor")


def read_private(path: Path, limit: int = 1024 * 1024) -> bytes:
    private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise AdmissionError("unsafe_file")
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise AdmissionError("file_limit")
        return raw


def create_private(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def decode(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        result = json.loads(raw, object_pairs_hook=pairs)
        if type(result) is not dict or encoded(result) != raw:
            raise ValueError
        return result
    except ValueError, TypeError, RecursionError:
        raise AdmissionError("invalid_record") from None


@dataclass(frozen=True)
class Debit:
    requests: int = 0
    microseconds: int = 0
    bytes: int = 0
    micro_usd: int = 0

    def __post_init__(self) -> None:
        caps = (6, 540_000_000, 24 * 1024 * 1024, 2_000_000)
        if any(
            type(v) is not int or not 0 <= v <= cap
            for v, cap in zip(asdict(self).values(), caps, strict=True)
        ):
            raise AdmissionError("capacity_exceeded")

    def plus(self, other: Debit) -> Debit:
        return Debit(**{k: v + asdict(other)[k] for k, v in asdict(self).items()})

    def remaining(self) -> dict[str, int]:
        return {
            k: v - asdict(self)[k]
            for k, v in asdict(Debit(6, 540_000_000, 24 * 1024 * 1024, 2_000_000)).items()
        }


def reconciliation(raw: bytes) -> tuple[Debit, bool]:
    record = decode(raw)
    if set(record) != {"schema", "campaign", "status", "evidence", "debit", "unknown", "reviewer"}:
        raise AdmissionError("reconciliation_invalid")
    if (
        record["schema"] != 1
        or record["campaign"] != CAMPAIGN
        or record["status"] != "reconciled"
        or not record["reviewer"]
    ):
        raise AdmissionError("reconciliation_required")
    if not isinstance(record["unknown"], list) or not record["evidence"]:
        raise AdmissionError("reconciliation_invalid")
    for item in record["evidence"]:
        if digest(read_private(Path(item["path"]))) != item["sha256"]:
            raise AdmissionError("reconciliation_evidence_changed")
    return Debit(**record["debit"]), bool(record["unknown"])


class Campaign:
    """Lock the stable private state directory, including throughout admission/dispatch.

    An immutable initialized marker precedes journal creation. Each append is fsynced
    before atomically replacing a head witness. An interrupted transition fails closed.
    """

    def __init__(self, root: Path) -> None:
        self._held = False
        self.root = root
        self.ledger = root / (CAMPAIGN + ".jsonl")
        self.marker = root / (CAMPAIGN + ".initialized")
        self.head = root / (CAMPAIGN + ".head")

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        private_directory(self.root)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AdmissionError("campaign_busy") from None
            self._held = True
            yield
        finally:
            self._held = False
            os.close(fd)

    def initialize(self, record: bytes) -> None:
        debit, unknown = reconciliation(record)
        if unknown:
            raise AdmissionError("history_unresolved")
        with self.locked():
            if any(p.exists() or p.is_symlink() for p in (self.marker, self.ledger, self.head)):
                raise AdmissionError("already_initialized_or_legacy_state")
            create_private(
                self.marker,
                encoded({"schema": 1, "campaign": CAMPAIGN, "reconciliation": digest(record)}),
            )
            create_private(self.ledger, b"")
            self._append(
                {"kind": "initialized", "reconciliation": record.decode(), "debit": asdict(debit)},
                b"",
            )

    def state(self) -> tuple[Debit, str, bytes]:
        if not self.marker.exists():
            if self.ledger.exists() or self.head.exists():
                raise AdmissionError("missing_initialized_marker")
            raise AdmissionError("first_initialization_required")
        marker = decode(read_private(self.marker))
        if (
            set(marker) != {"schema", "campaign", "reconciliation"}
            or marker["schema"] != 1
            or marker["campaign"] != CAMPAIGN
        ):
            raise AdmissionError("incompatible_state")
        try:
            raw, head = read_private(self.ledger), read_private(self.head)
        except FileNotFoundError:
            raise AdmissionError("initialized_state_missing") from None
        if head != encoded({"sha256": digest(raw)}) or not raw.endswith(b"\n"):
            raise AdmissionError("interrupted_or_corrupt_state")
        total, pending, previous = Debit(), "", b""
        for number, line in enumerate(raw.splitlines(keepends=True)):
            event = decode(line)
            if event.pop("previous", None) != digest(previous):
                raise AdmissionError("chain_invalid")
            kind = event.get("kind")
            if number == 0:
                if (
                    set(event) != {"kind", "reconciliation", "debit"}
                    or kind != "initialized"
                    or digest(event["reconciliation"].encode()) != marker["reconciliation"]
                ):
                    raise AdmissionError("genesis_invalid")
                total, unknown = reconciliation(event["reconciliation"].encode())
                if unknown or asdict(total) != event["debit"]:
                    raise AdmissionError("history_unresolved")
            elif kind == "reserved" and not pending:
                if (
                    set(event) != {"kind", "debit", "identity"}
                    or not isinstance(event["identity"], str)
                    or len(event["identity"]) != 64
                ):
                    raise AdmissionError("reservation_invalid")
                debit = Debit(**event["debit"])
                self.validate_input_debit(debit)
                total = total.plus(debit)
                pending = "reserved"
            elif kind in ("dispatched", "completed"):
                if (
                    set(event) != {"kind"}
                    or pending != {"dispatched": "reserved", "completed": "dispatched"}[kind]
                ):
                    raise AdmissionError("transition_invalid")
                pending = "dispatched" if kind == "dispatched" else ""
            else:
                raise AdmissionError("transition_invalid")
            previous += line
        return total, pending, raw

    @staticmethod
    def validate_input_debit(debit: Debit) -> None:
        if (
            debit.requests != 1
            or not 0 < debit.microseconds <= 90_000_000
            or not 0 < debit.bytes <= 4 * 1024 * 1024
            or debit.micro_usd <= 0
        ):
            raise AdmissionError("input_cap_exceeded")

    def reserve(self, debit: Debit, identity: str) -> None:
        if not self._held:
            raise AdmissionError("lock_required")
        total, pending, raw = self.state()
        if pending:
            raise AdmissionError("unresolved_debit")
        self.validate_input_debit(debit)
        total.plus(debit)
        if len(identity) != 64:
            raise AdmissionError("identity_invalid")
        self._append({"kind": "reserved", "debit": asdict(debit), "identity": identity}, raw)

    def transition(self, kind: str) -> None:
        if not self._held:
            raise AdmissionError("lock_required")
        _, pending, raw = self.state()
        if (
            kind not in ("dispatched", "completed")
            or pending != {"dispatched": "reserved", "completed": "dispatched"}[kind]
        ):
            raise AdmissionError("transition_invalid")
        self._append({"kind": kind}, raw)

    def _append(self, event: dict[str, Any], raw: bytes) -> None:
        line = encoded({**event, "previous": digest(raw)})
        fd = os.open(self.ledger, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        with os.fdopen(fd, "wb") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        temporary = self.head.with_suffix(".pending")
        create_private(temporary, encoded({"sha256": digest(raw + line)}))
        os.replace(temporary, self.head)
        sync_directory(self.root)
