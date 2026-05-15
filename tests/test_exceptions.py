"""Tests for ShieldOps SDK exceptions.

Owns the wart #6 canonical denial-payload shape — see
``docs/sdk/dogfood_0_1_2.md`` entry #6. Locking the shape in one place
keeps adapters (Flask, FastAPI, CrewAI, LangChain) from drifting.
"""

from __future__ import annotations

import json

import pytest

from shieldops_sdk.exceptions import ShieldOpsDeniedError


class TestDeniedErrorToDict:
    """``ShieldOpsDeniedError.to_dict()`` returns the canonical denial payload (wart #6)."""

    def test_to_dict_contains_canonical_fields(self) -> None:
        exc = ShieldOpsDeniedError(
            tool_name="drop_table",
            reasons=["matches blocked pattern"],
            risk_score=1.0,
        )
        payload = exc.to_dict()
        assert payload["tool_name"] == "drop_table"
        assert payload["action"] == "deny"
        assert payload["risk_score"] == 1.0
        assert payload["reasons"] == ["matches blocked pattern"]

    def test_to_dict_reasons_is_list_not_tuple(self) -> None:
        # Adapters serialise this straight to JSON; tuples would fall over
        # on json.dumps in some serialisers, lists are universally safe.
        exc = ShieldOpsDeniedError(
            tool_name="x",
            reasons=["a", "b"],
            risk_score=0.5,
        )
        assert isinstance(exc.to_dict()["reasons"], list)

    def test_to_dict_default_construction(self) -> None:
        # Defensive: an exc raised with no args still emits a parseable shape.
        exc = ShieldOpsDeniedError()
        payload = exc.to_dict()
        assert payload["action"] == "deny"
        assert payload["tool_name"] == ""
        assert payload["risk_score"] == 0.0
        assert payload["reasons"] == []

    def test_to_dict_round_trips_through_json(self) -> None:
        # No custom JSONEncoder required — adapters must be able to do
        # `json.dumps(exc.to_dict())` directly. Lock that invariant.
        exc = ShieldOpsDeniedError(
            tool_name="drop_table",
            reasons=["blocked pattern", "production arg"],
            risk_score=1.0,
        )
        raw = json.dumps(exc.to_dict())
        round_tripped = json.loads(raw)
        assert round_tripped == exc.to_dict()

    @pytest.mark.parametrize(
        "field,expected_type",
        [
            ("tool_name", str),
            ("action", str),
            ("risk_score", float),
            ("reasons", list),
        ],
    )
    def test_to_dict_field_types(self, field: str, expected_type: type) -> None:
        exc = ShieldOpsDeniedError(
            tool_name="x",
            reasons=["y"],
            risk_score=0.42,
        )
        assert isinstance(exc.to_dict()[field], expected_type)


class TestDeniedErrorRequestId:
    """``ShieldOpsDeniedError`` carries the Decision's request_id for traceability."""

    def test_request_id_stored_when_passed(self) -> None:
        exc = ShieldOpsDeniedError(
            tool_name="drop_table",
            reasons=["blocked"],
            risk_score=1.0,
            request_id="req-123",
        )
        assert exc.request_id == "req-123"
        assert exc.to_dict()["request_id"] == "req-123"

    def test_request_id_omitted_from_dict_when_unset(self) -> None:
        # Historical raises (no request_id) emit the same 4-field shape as
        # before — adding the field only when the SDK plumbs it through.
        exc = ShieldOpsDeniedError(tool_name="x", reasons=["y"], risk_score=0.5)
        assert exc.request_id == ""
        assert "request_id" not in exc.to_dict()

    def test_check_plumbs_request_id_into_exception(self) -> None:
        # End-to-end: interceptor.check raises a DeniedError whose
        # request_id matches some non-empty value the SDK generated.
        from shieldops_sdk.config import SDKMode, ShieldOpsConfig
        from shieldops_sdk.interceptor import ShieldOpsInterceptor

        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            ix.check("drop_table", {"db": "users"})
        assert exc_info.value.request_id  # non-empty
        assert exc_info.value.to_dict()["request_id"] == exc_info.value.request_id
