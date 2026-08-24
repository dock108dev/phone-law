from __future__ import annotations

from packages.authorization import (
    DemoPermission,
    has_permission,
    operations_actions,
    permissions_for,
)
from packages.contracts.report import DemoRole


def test_role_permissions_are_exact_and_immutable() -> None:
    assert permissions_for(DemoRole.REVIEWER) == frozenset(
        {DemoPermission.VIEW_REPORTS, DemoPermission.APPEND_FEEDBACK}
    )
    assert permissions_for(DemoRole.ADMINISTRATOR) == frozenset(DemoPermission)
    assert permissions_for(DemoRole.OPERATIONS) == frozenset(
        {
            DemoPermission.VIEW_REPORTS,
            DemoPermission.MANAGE_FAILURES,
            DemoPermission.MANAGE_UPLOADS,
            DemoPermission.VIEW_AUDIT,
            DemoPermission.USE_OPERATIONS,
        }
    )


def test_capability_and_operations_decisions_derive_from_policy() -> None:
    assert has_permission(DemoRole.ADMINISTRATOR, DemoPermission.PUBLISH_CONFIGURATION)
    assert not has_permission(DemoRole.OPERATIONS, DemoPermission.PUBLISH_CONFIGURATION)
    assert not has_permission(DemoRole.REVIEWER, DemoPermission.MANAGE_UPLOADS)

    assert operations_actions(DemoRole.REVIEWER) == ()
    assert "publish_configuration" not in operations_actions(DemoRole.OPERATIONS)
    assert "publish_configuration" in operations_actions(DemoRole.ADMINISTRATOR)
