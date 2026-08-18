"""Typed configuration with fail-closed staging and production validation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppProfile(StrEnum):
    TEST = "test"
    DEMO = "demo"
    LOCAL_DEV = "local_dev"
    LIVE_TEST = "live_test"
    STAGING = "staging"
    PRODUCTION = "production"


UNSAFE_TEXT_MARKERS = (
    "change-me",
    "changeme",
    "example",
    "placeholder",
    "demo",
    "local",
    "test",
)


class Settings(BaseSettings):
    """Environment settings shared by the API, worker, migration, and probes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_profile: AppProfile = AppProfile.DEMO
    app_version: str = "0.1.0"
    service_name: str = "application"
    allow_real_call_data: bool = False
    real_call_processing_authorized: bool = False
    real_data_approval_reference: str = ""

    auth_mode: str = "fake"
    app_secret: SecretStr = Field(
        default=SecretStr("demo-placeholder-not-a-deployable-secret"),
        repr=False,
    )
    database_url: SecretStr = Field(
        default=SecretStr(
            "postgresql+psycopg://colacci_demo:local-demo-only-password@db:5432/colacci_demo"
        ),
        repr=False,
    )

    object_storage_backend: str = "local_synthetic"
    object_storage_bucket: str = "synthetic-only"
    call_source_adapter: str = "fixture"
    transcriber_adapter: str = "fixture"
    analyzer_adapter: str = "fixture"
    notification_adapter: str = "noop"

    media_temp_root: Path = Path("/tmp/colacci-law-slice3a/objects")  # nosec B108
    manual_upload_root: Path = Path("/tmp/colacci-law-slice4-local/objects")  # nosec B108
    manual_upload_manifest_path: Path = Path(  # nosec B108
        "/tmp/colacci-law-slice4-local/synthetic-manifest.json"
    )
    media_max_bytes: int = 20 * 1024 * 1024
    media_max_duration_seconds: float = 60.0
    live_transcription_enabled: bool = False
    live_transcription_authorized: bool = False
    transcription_approval_reference: str = ""
    transcription_model_id: str = "gpt-4o-transcribe-diarize"
    transcription_fallback_model_id: str = "gpt-transcribe"
    transcription_timeout_seconds: float = 30.0
    transcription_max_requests: int = 0
    transcription_max_total_audio_seconds: float = 0
    transcription_max_total_bytes: int = 0
    transcription_test_budget_usd: Decimal = Decimal("0.00")
    transcription_live_execution_confirmed: bool = False
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    openai_project_id: SecretStr | None = Field(default=None, repr=False)
    openai_project_data_controls_approved: bool = False
    openai_base_url: str = "https://api.openai.com/v1"

    audio_retention_days: int = 0
    transcript_retention_days: int = 0
    analysis_retention_days: int = 0
    audit_retention_days: int = 0
    retention_policy_approved: bool = False

    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:15173"])
    firm_timezone: str = "America/New_York"
    log_level: str = "INFO"

    @property
    def synthetic_mode(self) -> bool:
        return self.app_profile in {
            AppProfile.TEST,
            AppProfile.DEMO,
            AppProfile.LOCAL_DEV,
            AppProfile.LIVE_TEST,
        }

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return the database URL only at the database boundary."""

        return self.database_url.get_secret_value()

    @model_validator(mode="after")
    def reject_unsafe_configuration(self) -> Settings:
        issues: set[str] = set()

        if self.synthetic_mode:
            if self.allow_real_call_data:
                issues.add("allow_real_call_data")
            if self.real_call_processing_authorized:
                issues.add("real_call_processing_authorized")

        if self.media_max_bytes <= 0 or self.media_max_bytes > 25 * 1024 * 1024:
            issues.add("media_max_bytes")
        if self.media_max_duration_seconds <= 30 or self.media_max_duration_seconds > 3600:
            issues.add("media_max_duration_seconds")
        if self.transcription_timeout_seconds <= 0 or self.transcription_timeout_seconds > 120:
            issues.add("transcription_timeout_seconds")

        if self.app_profile is AppProfile.LIVE_TEST:
            self._collect_live_test_issues(issues)
        elif self.app_profile is AppProfile.LOCAL_DEV:
            self._collect_local_dev_issues(issues)
        else:
            if self.live_transcription_enabled or self.live_transcription_authorized:
                issues.add("live_transcription_profile")
            if self.transcription_approval_reference.strip():
                issues.add("transcription_approval_reference")

        if self.app_profile in {AppProfile.STAGING, AppProfile.PRODUCTION}:
            self._collect_deployment_issues(issues)

        resolved_media_root = self.media_temp_root.resolve(strict=False)
        if self.synthetic_mode and not str(resolved_media_root).startswith(  # nosec B108
            "/tmp/colacci-law-"
        ):
            issues.add("media_temp_root")
        resolved_upload_root = self.manual_upload_root.resolve(strict=False)
        resolved_manifest = self.manual_upload_manifest_path.resolve(strict=False)
        if self.synthetic_mode and (
            not str(resolved_upload_root).startswith(  # nosec B108
                "/tmp/colacci-law-slice4-"
            )
            or not str(resolved_manifest).startswith(  # nosec B108
                "/tmp/colacci-law-slice4-"
            )
        ):
            issues.add("manual_upload_boundary")

        if self.allow_real_call_data:
            if self.app_profile not in {AppProfile.STAGING, AppProfile.PRODUCTION}:
                issues.add("app_profile")
            if not self.real_call_processing_authorized:
                issues.add("real_call_processing_authorized")
            if _is_unsafe_text(self.real_data_approval_reference, minimum_length=8):
                issues.add("real_data_approval_reference")

        if issues:
            field_names = ",".join(sorted(issues))
            raise ValueError(f"unsafe configuration fields: {field_names}")

        return self

    def _collect_local_dev_issues(self, issues: set[str]) -> None:
        safe_shapes = {
            ("fixture", "fixture", "fixture"),
            ("generated_synthetic", "openai_cli_local", "disabled"),
            ("transcript_only", "transcript_only_import", "fixture"),
        }
        configured_shape = (
            self.call_source_adapter,
            self.transcriber_adapter,
            self.analyzer_adapter,
        )
        if configured_shape not in safe_shapes:
            issues.add("local_dev_adapter_shape")
        if self.object_storage_backend != "local_synthetic":
            issues.add("object_storage_backend")
        if self.notification_adapter != "noop":
            issues.add("notification_adapter")
        if self.auth_mode != "fake":
            issues.add("auth_mode")
        if self.live_transcription_enabled or self.live_transcription_authorized:
            issues.add("live_transcription_profile")
        if self.transcription_approval_reference.strip():
            issues.add("transcription_approval_reference")
        if self.media_temp_root.resolve(strict=False) != Path(
            "/tmp/colacci-law-slice3c/objects"  # nosec B108
        ):
            issues.add("media_temp_root")

    def _collect_live_test_issues(self, issues: set[str]) -> None:
        if not self.live_transcription_enabled:
            issues.add("live_transcription_enabled")
        if not self.live_transcription_authorized:
            issues.add("live_transcription_authorized")
        if self.transcription_approval_reference != "OWNER-CHAT-2026-08-17-SLICE-3B":
            issues.add("transcription_approval_reference")
        if self.transcription_model_id != "gpt-4o-transcribe-diarize":
            issues.add("transcription_model_id")
        if self.transcription_max_requests != 4:
            issues.add("transcription_max_requests")
        if self.transcription_max_total_audio_seconds != 120:
            issues.add("transcription_max_total_audio_seconds")
        if self.transcription_max_total_bytes != 20 * 1024 * 1024:
            issues.add("transcription_max_total_bytes")
        if self.transcription_test_budget_usd != Decimal("1.00"):
            issues.add("transcription_test_budget_usd")
        if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
            issues.add("openai_api_key")
        if self.openai_project_id is None or not self.openai_project_id.get_secret_value().strip():
            issues.add("openai_project_id")
        if not self.openai_project_data_controls_approved:
            issues.add("openai_project_data_controls_approved")
        if not _safe_openai_base_url(self.openai_base_url):
            issues.add("openai_base_url")
        if self.call_source_adapter != "generated_synthetic":
            issues.add("call_source_adapter")
        if self.transcriber_adapter != "openai_live":
            issues.add("transcriber_adapter")
        if self.analyzer_adapter != "disabled":
            issues.add("analyzer_adapter")
        if self.notification_adapter != "noop":
            issues.add("notification_adapter")
        if self.object_storage_backend != "local_synthetic":
            issues.add("object_storage_backend")
        if self.media_temp_root.resolve(strict=False) != Path(
            "/tmp/colacci-law-slice3b/objects"  # nosec B108
        ):
            issues.add("media_temp_root")

    def _collect_deployment_issues(self, issues: set[str]) -> None:
        if self.auth_mode != "sso":
            issues.add("auth_mode")

        if _is_unsafe_text(self.app_secret.get_secret_value(), minimum_length=32):
            issues.add("app_secret")

        if self.object_storage_backend != "private_cloud":
            issues.add("object_storage_backend")
        if _is_unsafe_text(self.object_storage_bucket, minimum_length=3):
            issues.add("object_storage_bucket")

        if self.call_source_adapter == "fixture":
            issues.add("call_source_adapter")
        if self.call_source_adapter not in {"disabled", "manual_upload"}:
            issues.add("call_source_adapter")
        if self.transcriber_adapter != "disabled":
            issues.add("transcriber_adapter")
        if self.analyzer_adapter != "disabled":
            issues.add("analyzer_adapter")

        retention_values = (
            self.audio_retention_days,
            self.transcript_retention_days,
            self.analysis_retention_days,
            self.audit_retention_days,
        )
        if not self.retention_policy_approved or any(value <= 0 for value in retention_values):
            issues.add("retention_settings")

        if self.debug:
            issues.add("debug")
        if not self.cors_origins or any(
            not _safe_deployment_origin(item) for item in self.cors_origins
        ):
            issues.add("cors_origins")

        if _unsafe_database_url(self.database_url.get_secret_value()):
            issues.add("database_url")


def _is_unsafe_text(value: str, *, minimum_length: int) -> bool:
    normalized = value.strip().lower()
    return len(value.strip()) < minimum_length or any(
        marker in normalized for marker in UNSAFE_TEXT_MARKERS
    )


def _safe_deployment_origin(origin: str) -> bool:
    if origin == "*":
        return False
    parsed = urlsplit(origin)
    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and bool(hostname)
        and hostname
        not in {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
        }
    )


def _safe_openai_base_url(value: str) -> bool:
    parsed = urlsplit(value)
    allowed_hosts = {
        "api.openai.com",
        "us.api.openai.com",
        "eu.api.openai.com",
        "au.api.openai.com",
        "ca.api.openai.com",
        "jp.api.openai.com",
        "in.api.openai.com",
        "sg.api.openai.com",
        "kr.api.openai.com",
        "gb.api.openai.com",
        "ae.api.openai.com",
    }
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() in allowed_hosts
        and parsed.path.rstrip("/") == "/v1"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _unsafe_database_url(value: str) -> bool:
    normalized = value.lower()
    parsed = urlsplit(value.replace("postgresql+psycopg", "postgresql", 1))
    hostname = (parsed.hostname or "").lower()
    username = (parsed.username or "").lower()
    password = parsed.password or ""
    return (
        parsed.scheme not in {"postgresql", "postgres"}
        or hostname
        in {
            "",
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "db",
        }
        or _is_unsafe_text(username, minimum_length=3)
        or _is_unsafe_text(password, minimum_length=16)
        or any(marker in normalized for marker in ("example", "placeholder", "change-me"))
    )
