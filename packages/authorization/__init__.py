"""Authoritative demo authorization policy."""

from packages.authorization.demo_policy import (
    DemoPermission,
    has_permission,
    operations_actions,
    permissions_for,
)

__all__ = [
    "DemoPermission",
    "has_permission",
    "operations_actions",
    "permissions_for",
]
