"""Default pattern catalogues for the ShieldOps interceptor.

These are ``frozenset`` so the module-level defaults cannot be mutated by
client code. The interceptor copies them into per-instance ``set`` attributes
at construction time, preserving the existing pattern of
``interceptor._blocked_tools.update(...)`` for advanced post-construct
configuration.
"""

from __future__ import annotations

DEFAULT_BLOCKED_PATTERNS: frozenset[str] = frozenset(
    {
        "delete_database",
        "drop_table",
        "modify_iam_root",
        "rm_rf",
        "format_disk",
        "disable_firewall",
        "delete_backup",
    }
)

DEFAULT_HIGH_RISK_PATTERNS: frozenset[str] = frozenset(
    {
        "execute_command",
        "run_shell",
        "modify_security_group",
        "change_iam_policy",
        "create_user",
        "rotate_credentials",
    }
)
