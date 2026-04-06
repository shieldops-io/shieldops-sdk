#!/usr/bin/env python3
"""Example: Configuring custom allow/deny policies with ShieldOps Interceptor.

This example shows how to extend the default policy rules by adding custom
blocked and high-risk tool patterns to the interceptor. This is useful when
your organization has specific tools that should always be blocked or flagged.

Usage:
    python custom_policies.py
"""

from __future__ import annotations

import os

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor


# ---------------------------------------------------------------------------
# 1. View the default blocked and high-risk patterns
# ---------------------------------------------------------------------------
def show_defaults() -> None:
    print("=" * 60)
    print("DEFAULT POLICY PATTERNS")
    print("=" * 60)

    config = ShieldOpsConfig(api_key="sk-demo", mode=SDKMode.ENFORCE)
    interceptor = ShieldOpsInterceptor(config)

    # The interceptor ships with built-in blocked patterns
    print(f"  Blocked tools:   {sorted(interceptor._blocked_tools)}")
    print(f"  High-risk tools: {sorted(interceptor._high_risk_tools)}\n")


# ---------------------------------------------------------------------------
# 2. Add custom blocked tool patterns
# ---------------------------------------------------------------------------
def demo_custom_blocked_tools() -> None:
    print("=" * 60)
    print("CUSTOM BLOCKED TOOLS -- add organization-specific deny rules")
    print("=" * 60)

    config = ShieldOpsConfig(api_key="sk-demo", mode=SDKMode.ENFORCE)
    interceptor = ShieldOpsInterceptor(config)

    # Add tools that should always be blocked in your environment
    custom_blocked = {
        "export_customer_data",  # PII exfiltration risk
        "send_bulk_email",  # Spam risk
        "modify_billing",  # Financial control
        "disable_audit_log",  # Compliance violation
    }
    interceptor._blocked_tools.update(custom_blocked)

    print(f"  Added {len(custom_blocked)} custom blocked tools")
    print(f"  Total blocked: {len(interceptor._blocked_tools)}\n")

    # Test against the custom rules
    test_tools = [
        ("search_web", {"query": "docs"}),
        ("export_customer_data", {"format": "csv", "scope": "all"}),
        ("send_bulk_email", {"template": "promo", "count": 50000}),
        ("read_file", {"path": "/var/log/app.log"}),
        ("disable_audit_log", {"service": "payments"}),
    ]

    for tool_name, args in test_tools:
        try:
            decision = interceptor.check(tool_name, args)
            print(f"  {tool_name:25s} -> ALLOWED (risk={decision.risk_score})")
        except ShieldOpsDeniedError:
            print(f"  {tool_name:25s} -> BLOCKED")

    print(f"\n  Stats: {interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 3. Add custom high-risk patterns
# ---------------------------------------------------------------------------
def demo_custom_high_risk() -> None:
    print("=" * 60)
    print("CUSTOM HIGH-RISK TOOLS -- flag tools for elevated monitoring")
    print("=" * 60)

    config = ShieldOpsConfig(api_key="sk-demo", mode=SDKMode.AUDIT)
    interceptor = ShieldOpsInterceptor(config)

    # Add tools that should be flagged as high-risk (not blocked, but scored)
    custom_high_risk = {
        "query_database",  # Data access -- audit trail needed
        "deploy_to_staging",  # Deployment action
        "update_dns_record",  # Infrastructure change
        "restart_service",  # Availability impact
    }
    interceptor._high_risk_tools.update(custom_high_risk)

    print(f"  Added {len(custom_high_risk)} custom high-risk tools")
    print(f"  Total high-risk: {len(interceptor._high_risk_tools)}\n")

    # Check each -- all allowed in audit mode, but risk scores are elevated
    test_tools = [
        ("search_web", {}),
        ("query_database", {"sql": "SELECT * FROM users"}),
        ("deploy_to_staging", {"service": "api", "version": "2.1.0"}),
        ("update_dns_record", {"domain": "app.example.com", "type": "A"}),
        ("restart_service", {"service": "worker", "env": "production"}),
    ]

    for tool_name, args in test_tools:
        decision = interceptor.check(tool_name, args)
        risk_label = "LOW" if decision.risk_score < 0.3 else "HIGH"
        print(
            f"  {tool_name:25s} -> risk={decision.risk_score:.1f} [{risk_label}] "
            f"reasons={decision.reasons}"
        )

    print(f"\n  Stats: {interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 4. Build a policy evaluator function
# ---------------------------------------------------------------------------
def demo_policy_evaluator() -> None:
    print("=" * 60)
    print("POLICY EVALUATOR -- reusable function for custom rule checking")
    print("=" * 60)

    # Define a policy as a simple data structure
    policy_rules: dict[str, dict] = {
        "block_data_export": {
            "tools": {"export_customer_data", "dump_database", "download_pii"},
            "reason": "Data export requires manual approval",
        },
        "block_infra_destruction": {
            "tools": {"terminate_cluster", "delete_vpc", "destroy_terraform"},
            "reason": "Infrastructure destruction blocked by policy",
        },
        "block_privilege_escalation": {
            "tools": {"grant_admin", "escalate_privileges", "modify_iam_root"},
            "reason": "Privilege escalation requires security review",
        },
    }

    def evaluate_against_policies(
        tool_name: str,
        rules: dict[str, dict],
    ) -> tuple[bool, list[str]]:
        """Check a tool name against all policy rules.

        Returns:
            Tuple of (allowed: bool, violation_reasons: list[str])
        """
        violations: list[str] = []
        normalized = tool_name.lower().strip()
        for rule_name, rule in rules.items():
            if normalized in rule["tools"]:
                violations.append(f"[{rule_name}] {rule['reason']}")
        return (len(violations) == 0, violations)

    # Test various tools against the policy
    test_tools = [
        "search_web",
        "export_customer_data",
        "terminate_cluster",
        "grant_admin",
        "read_file",
        "dump_database",
    ]

    for tool_name in test_tools:
        allowed, violations = evaluate_against_policies(tool_name, policy_rules)
        if allowed:
            print(f"  {tool_name:25s} -> ALLOWED")
        else:
            print(f"  {tool_name:25s} -> DENIED")
            for v in violations:
                print(f"    {v}")

    print()


# ---------------------------------------------------------------------------
# 5. Combine custom policies with the interceptor
# ---------------------------------------------------------------------------
def demo_combined() -> None:
    print("=" * 60)
    print("COMBINED -- custom rules + interceptor in enforce mode")
    print("=" * 60)

    config = ShieldOpsConfig(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode=SDKMode.ENFORCE,
    )
    interceptor = ShieldOpsInterceptor(config)

    # Extend with organization-specific blocked tools
    interceptor._blocked_tools.update(
        {
            "export_customer_data",
            "terminate_cluster",
            "grant_admin",
        }
    )

    # Run a simulated agent workflow
    agent_plan = [
        ("search_web", {"query": "CVE-2024-1234 details"}),
        ("read_file", {"path": "/var/log/auth.log"}),
        ("execute_command", {"cmd": "netstat -tlnp"}),
        ("export_customer_data", {"format": "json"}),
        ("terminate_cluster", {"cluster": "prod-east"}),
        ("create_user", {"username": "responder", "role": "analyst"}),
    ]

    print("  Simulating agent workflow:\n")
    for tool_name, args in agent_plan:
        try:
            decision = interceptor.check(tool_name, args)
            print(f"  [{decision.risk_score:.1f}] {tool_name:25s} -> ALLOWED")
        except ShieldOpsDeniedError as exc:
            print(f"  [1.0] {tool_name:25s} -> DENIED ({exc.reasons[0]})")

    print(f"\n  Final stats: {interceptor.stats}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    show_defaults()
    demo_custom_blocked_tools()
    demo_custom_high_risk()
    demo_policy_evaluator()
    demo_combined()
