"""Single source of truth for local synthetic role permissions."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

from packages.contracts.report import DemoRole


class DemoPermission(StrEnum):
    VIEW_REPORTS = "view_reports"
    APPEND_FEEDBACK = "append_feedback"
    MANAGE_FAILURES = "manage_failures"
    MANAGE_PLAYBOOKS = "manage_playbooks"
    MANAGE_UPLOADS = "manage_uploads"
    VIEW_AUDIT = "view_audit"
    USE_OPERATIONS = "use_operations"
    PUBLISH_CONFIGURATION = "publish_configuration"


_ROLE_PERMISSIONS = MappingProxyType(
    {
        DemoRole.REVIEWER: frozenset(
            {
                DemoPermission.VIEW_REPORTS,
                DemoPermission.APPEND_FEEDBACK,
            }
        ),
        DemoRole.ADMINISTRATOR: frozenset(DemoPermission),
        DemoRole.OPERATIONS: frozenset(
            {
                DemoPermission.VIEW_REPORTS,
                DemoPermission.MANAGE_FAILURES,
                DemoPermission.MANAGE_UPLOADS,
                DemoPermission.VIEW_AUDIT,
                DemoPermission.USE_OPERATIONS,
            }
        ),
    }
)

_OPERATIONS_ACTIONS = (
    "view_configuration",
    "run_retention",
    "retry_deletion",
    "run_backup_restore",
    "view_audit",
    "preview_notification",
)


def permissions_for(role: DemoRole) -> frozenset[DemoPermission]:
    """Return the immutable permission set for an allowlisted demo role."""

    return _ROLE_PERMISSIONS[role]


def has_permission(role: DemoRole, permission: DemoPermission) -> bool:
    return permission in permissions_for(role)


def operations_actions(role: DemoRole) -> tuple[str, ...]:
    """Derive the operations-center presentation from the enforcement policy."""

    if not has_permission(role, DemoPermission.USE_OPERATIONS):
        return ()
    if has_permission(role, DemoPermission.PUBLISH_CONFIGURATION):
        return (
            _OPERATIONS_ACTIONS[0],
            DemoPermission.PUBLISH_CONFIGURATION.value,
            *_OPERATIONS_ACTIONS[1:],
        )
    return _OPERATIONS_ACTIONS
