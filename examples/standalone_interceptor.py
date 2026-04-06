#!/usr/bin/env python3
"""Example: Using ShieldOps Interceptor standalone (no AI framework needed).

This example demonstrates how to use the ShieldOpsInterceptor directly to
evaluate tool calls against policy -- without LangChain, CrewAI, or LlamaIndex.
This is useful for custom agent frameworks or any Python application that needs
tool call governance.

Usage:
    python standalone_interceptor.py
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# 1. Import the interceptor and config
# ---------------------------------------------------------------------------
from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor


# ---------------------------------------------------------------------------
# 2. Demo: Audit mode -- observe tool calls without blocking
# ---------------------------------------------------------------------------
def demo_audit_mode() -> None:
    print("=" * 60)
    print("AUDIT MODE -- logs decisions but never blocks tool calls")
    print("=" * 60)

    # Create config in audit mode (the default)
    config = ShieldOpsConfig(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode=SDKMode.AUDIT,
    )
    interceptor = ShieldOpsInterceptor(config)

    # Check a safe tool -- low risk, allowed
    decision = interceptor.check("search_web", {"query": "python security"})
    print(f"  search_web       -> action={decision.action}, risk={decision.risk_score}")

    # Check a high-risk tool -- scored but still allowed in audit mode
    decision = interceptor.check("execute_command", {"cmd": "ls -la /etc"})
    print(f"  execute_command  -> action={decision.action}, risk={decision.risk_score}")

    # Check a blocked-pattern tool -- risk 1.0 but still allowed in audit mode
    decision = interceptor.check("delete_database", {"db": "users"})
    print(f"  delete_database  -> action={decision.action}, risk={decision.risk_score}")

    # Check a tool with production args -- risk bumped by arg heuristics
    decision = interceptor.check("deploy_service", {"env": "production", "service": "api"})
    print(f"  deploy_service   -> action={decision.action}, risk={decision.risk_score}")

    print(f"\n  Stats: {interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 3. Demo: Enforce mode -- block dangerous tool calls
# ---------------------------------------------------------------------------
def demo_enforce_mode() -> None:
    print("=" * 60)
    print("ENFORCE MODE -- blocks tool calls that match dangerous patterns")
    print("=" * 60)

    config = ShieldOpsConfig(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode=SDKMode.ENFORCE,
    )
    interceptor = ShieldOpsInterceptor(config)

    # Safe tool -- passes through
    decision = interceptor.check("search_web", {"query": "docs"})
    print(f"  search_web       -> ALLOWED (risk={decision.risk_score})")

    # High-risk tool -- allowed but flagged (risk 0.7)
    decision = interceptor.check("execute_command", {"cmd": "whoami"})
    print(f"  execute_command  -> ALLOWED (risk={decision.risk_score})")

    # Blocked tool -- raises ShieldOpsDeniedError in enforce mode
    try:
        interceptor.check("delete_database", {"db": "production_users"})
    except ShieldOpsDeniedError as exc:
        print(f"  delete_database  -> DENIED: {exc.message}")
        print(f"                     reasons: {exc.reasons}")
        print(f"                     risk: {exc.risk_score}")

    # Another blocked tool
    try:
        interceptor.check("rm_rf", {"path": "/"})
    except ShieldOpsDeniedError as exc:
        print(f"  rm_rf            -> DENIED: {exc.message}")

    print(f"\n  Stats: {interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 4. Demo: Using the interceptor in a custom agent loop
# ---------------------------------------------------------------------------
def demo_custom_agent() -> None:
    print("=" * 60)
    print("CUSTOM AGENT LOOP -- integrate into any Python workflow")
    print("=" * 60)

    config = ShieldOpsConfig(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode=SDKMode.ENFORCE,
    )
    interceptor = ShieldOpsInterceptor(config)

    # Simulate a sequence of tool calls from an AI agent
    tool_calls = [
        ("search_web", {"query": "latest CVEs"}),
        ("read_file", {"path": "/var/log/syslog"}),
        ("execute_command", {"cmd": "nmap -sV target.local"}),
        ("delete_database", {"db": "audit_logs"}),  # This will be blocked
        ("create_user", {"username": "analyst", "role": "viewer"}),
    ]

    for tool_name, args in tool_calls:
        try:
            decision = interceptor.check(tool_name, args)
            print(f"  {tool_name:25s} -> ALLOWED (risk={decision.risk_score})")
        except ShieldOpsDeniedError:
            print(f"  {tool_name:25s} -> BLOCKED")

    print(f"\n  Stats: {interceptor.stats}")
    print(f"  Denial rate: {interceptor.stats['total_denials']}/{interceptor.stats['total_calls']}")


# ---------------------------------------------------------------------------
# 5. Demo: Argument hashing for audit trails
# ---------------------------------------------------------------------------
def demo_arg_hashing() -> None:
    print("\n" + "=" * 60)
    print("ARGUMENT HASHING -- deterministic hashes for audit logs")
    print("=" * 60)

    # Hash tool arguments for immutable audit trail entries
    args = {"db": "production_users", "action": "truncate"}
    hash_val = ShieldOpsInterceptor.hash_args(args)
    print(f"  Args: {args}")
    print(f"  Hash: {hash_val}")

    # Same args always produce the same hash
    hash_val_2 = ShieldOpsInterceptor.hash_args(args)
    print(f"  Same hash on repeat: {hash_val == hash_val_2}")

    # Different args produce different hashes
    different_args = {"db": "staging_users", "action": "truncate"}
    hash_val_3 = ShieldOpsInterceptor.hash_args(different_args)
    print(f"  Different args hash: {hash_val_3} (differs: {hash_val != hash_val_3})\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    demo_audit_mode()
    demo_enforce_mode()
    demo_custom_agent()
    demo_arg_hashing()
