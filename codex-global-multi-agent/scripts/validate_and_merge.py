#!/usr/bin/env python3
"""Validate subagent outputs, check v1.1 protocol assertions, and build writeback approvals."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = [
    "goal",
    "scope",
    "allowed_tools",
    "summary",
    "evidence",
    "state_delta",
    "risks",
    "fallback_suggestion",
    "next_steps",
    "confidence",
]

REQUIRED_STATE_KEYS = ["facts", "preferences", "decisions", "risks"]
VALID_EVIDENCE_TYPES = {"file", "web", "command", "memory", "inference"}
VALID_FALLBACKS = {
    "retry_same_tool",
    "switch_tool",
    "reduce_scope",
    "request_human_input",
    "escalate_to_main_agent",
    None,
}
VALID_ROLES = {
    "Planner",
    "Retriever",
    "Verifier",
    "Synthesizer",
    "Compactor",
    "Architect",
    "Implementer",
    "Reviewer",
    "Tester",
    "Browser Operator",
    "Extractor",
    "Validator",
    "Recorder",
}
VALID_CONTEXT_BLOCKS = {
    "Relevant Preferences",
    "Workspace Facts",
    "Prior Decisions",
    "Task Continuation State",
    "Known Risks",
    "Retrieved Facts",
}
ROLE_ALLOWED_BLOCKS = {
    "Planner": {
        "Relevant Preferences",
        "Workspace Facts",
        "Prior Decisions",
        "Task Continuation State",
        "Known Risks",
    },
    "Retriever": {
        "Workspace Facts",
        "Retrieved Facts",
    },
    "Verifier": {
        "Prior Decisions",
        "Known Risks",
        "Retrieved Facts",
    },
    "Synthesizer": VALID_CONTEXT_BLOCKS,
    "Compactor": {
        "Workspace Facts",
        "Prior Decisions",
        "Known Risks",
        "Retrieved Facts",
    },
}
VALID_SCOPES = {"task", "workspace", "user_global"}
VALID_SOURCES = {
    "observed_fact",
    "tool_output",
    "user_claim",
    "approved_decision",
    "model_inference",
}
VALID_FACT_PROPOSAL_TYPES = {"update", "invalidate"}
VALID_PROPOSAL_TYPES = {"append", "update", "invalidate"}
VALID_IMPACT_LEVELS = {"low", "medium", "high"}
VALID_TRIGGER_VALUES = {
    "task_start",
    "before_task_start",
    "after_failure",
    "on_workspace_switch",
    "before_subagent_spawn",
}
VALID_COMPRESSION_PROPOSAL_KIND = "compression_proposal"
RECALL_PACKAGE_SCHEMA_VERSION = "recall_package_v1"
COMPRESSION_PROPOSAL_SCHEMA_VERSION = "compression_proposal_v1"
FALLBACK_ACTIONS = {
    "retry_same_tool": "Retry once, then escalate if it fails again.",
    "switch_tool": "Re-route to a different tool or implementation path.",
    "reduce_scope": "Shrink task scope and re-dispatch.",
    "request_human_input": "Stop automation and ask the user for a decision.",
    "escalate_to_main_agent": "Return control to the main agent for replanning.",
    None: "No fallback required.",
}
PACKAGED_CONTEXT_ONLY = "main_agent_packaged_context_only"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def uniq_json(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            merged.append(value)
    return merged


def validate_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_evidence_item(item: Any, source: Path, index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return [f"{source.name}: evidence[{index}] must be an object"]
    if item.get("type") not in VALID_EVIDENCE_TYPES:
        errors.append(f"{source.name}: evidence[{index}].type is invalid")
    if not validate_string(item.get("value")):
        errors.append(f"{source.name}: evidence[{index}].value must be a string")
    for optional_key in ("id", "ref", "source", "timestamp"):
        if optional_key in item and not validate_string(item.get(optional_key)):
            errors.append(f"{source.name}: evidence[{index}].{optional_key} must be a string")
    return errors


def validate_evidence_ids(value: Any, source: Path, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(validate_string(item) for item in value):
        return [f"{source.name}: {label}.evidence_ids must be a string array"]
    return []


def validate_fact_like(item: Any, source: Path, label: str) -> list[str]:
    errors: list[str] = []
    if isinstance(item, str):
        return []
    if not isinstance(item, dict):
        return [f"{source.name}: {label} item must be a string or object"]
    for key in ("key", "value", "scope", "source"):
        if key not in item:
            errors.append(f"{source.name}: {label} item missing '{key}'")
    if "key" in item and not validate_string(item["key"]):
        errors.append(f"{source.name}: {label}.key must be a string")
    if "value" in item and not validate_string(item["value"]):
        errors.append(f"{source.name}: {label}.value must be a string")
    if "scope" in item and item["scope"] not in VALID_SCOPES:
        errors.append(f"{source.name}: {label}.scope is invalid")
    if "source" in item and item["source"] not in VALID_SOURCES:
        errors.append(f"{source.name}: {label}.source is invalid")
    if "proposal_type" in item and item["proposal_type"] not in VALID_FACT_PROPOSAL_TYPES:
        errors.append(f"{source.name}: {label}.proposal_type is invalid")
    errors.extend(validate_evidence_ids(item.get("evidence_ids"), source, label))
    if item.get("proposal_type") in {"update", "invalidate"} and not item.get("evidence_ids"):
        errors.append(f"{source.name}: {label}.evidence_ids are required for update/invalidate")
    return errors


def validate_decision_item(item: Any, source: Path) -> list[str]:
    errors: list[str] = []
    if isinstance(item, str):
        return []
    if not isinstance(item, dict):
        return [f"{source.name}: decisions item must be a string or object"]
    for key in ("topic", "decision", "scope", "proposal_type", "source"):
        if key not in item:
            errors.append(f"{source.name}: decisions item missing '{key}'")
    if "topic" in item and not validate_string(item["topic"]):
        errors.append(f"{source.name}: decisions.topic must be a string")
    if "decision" in item and not validate_string(item["decision"]):
        errors.append(f"{source.name}: decisions.decision must be a string")
    if "rationale" in item and not validate_string(item["rationale"]):
        errors.append(f"{source.name}: decisions.rationale must be a string")
    if "scope" in item and item["scope"] not in VALID_SCOPES:
        errors.append(f"{source.name}: decisions.scope is invalid")
    if "proposal_type" in item and item["proposal_type"] not in VALID_PROPOSAL_TYPES:
        errors.append(f"{source.name}: decisions.proposal_type is invalid")
    if "source" in item and item["source"] not in VALID_SOURCES:
        errors.append(f"{source.name}: decisions.source is invalid")
    errors.extend(validate_evidence_ids(item.get("evidence_ids"), source, "decisions"))
    if item.get("proposal_type") in {"update", "invalidate"} and not item.get("evidence_ids"):
        errors.append(f"{source.name}: decisions.evidence_ids are required for update/invalidate")
    return errors


def validate_risk_item(item: Any, source: Path) -> list[str]:
    errors: list[str] = []
    if isinstance(item, str):
        return []
    if not isinstance(item, dict):
        return [f"{source.name}: risks item must be a string or object"]
    for key in ("risk", "scope", "source"):
        if key not in item:
            errors.append(f"{source.name}: risks item missing '{key}'")
    if "risk" in item and not validate_string(item["risk"]):
        errors.append(f"{source.name}: risks.risk must be a string")
    if "scope" in item and item["scope"] not in VALID_SCOPES:
        errors.append(f"{source.name}: risks.scope is invalid")
    if "source" in item and item["source"] not in VALID_SOURCES:
        errors.append(f"{source.name}: risks.source is invalid")
    if "impact" in item and item["impact"] not in VALID_IMPACT_LEVELS:
        errors.append(f"{source.name}: risks.impact is invalid")
    if "likelihood" in item and item["likelihood"] not in VALID_IMPACT_LEVELS:
        errors.append(f"{source.name}: risks.likelihood is invalid")
    errors.extend(validate_evidence_ids(item.get("evidence_ids"), source, "risks"))
    return errors


def validate_payload(payload: Any, source: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{source.name}: top-level JSON must be an object"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in payload:
            errors.append(f"{source.name}: missing field '{key}'")

    if errors:
        return errors

    if "role" in payload and payload["role"] not in VALID_ROLES:
        errors.append(f"{source.name}: invalid role")

    if "memory_access_mode" in payload and payload["memory_access_mode"] != PACKAGED_CONTEXT_ONLY:
        errors.append(f"{source.name}: invalid memory_access_mode")

    if "context_snapshot_id" in payload and not validate_string(payload.get("context_snapshot_id")):
        errors.append(f"{source.name}: context_snapshot_id must be a string")

    if "run_revision" in payload:
        run_revision = payload["run_revision"]
        if not isinstance(run_revision, int) or run_revision < 1:
            errors.append(f"{source.name}: run_revision must be a positive integer")

    if "context_blocks" in payload:
        context_blocks = payload["context_blocks"]
        if not isinstance(context_blocks, list) or not all(
            block in VALID_CONTEXT_BLOCKS for block in context_blocks
        ):
            errors.append(f"{source.name}: context_blocks must be an array of valid block names")
        role = payload.get("role")
        if role in ROLE_ALLOWED_BLOCKS and isinstance(context_blocks, list):
            if not set(context_blocks).issubset(ROLE_ALLOWED_BLOCKS[role]):
                errors.append(f"{source.name}: context_blocks exceed allowed blocks for role {role}")

    if "source_context_blocks" in payload:
        source_context_blocks = payload["source_context_blocks"]
        if not isinstance(source_context_blocks, list) or not all(
            block in VALID_CONTEXT_BLOCKS for block in source_context_blocks
        ):
            errors.append(f"{source.name}: source_context_blocks must be an array of valid block names")

    if "context_token_estimate" in payload:
        estimate = payload["context_token_estimate"]
        if not isinstance(estimate, (int, float)) or float(estimate) < 0:
            errors.append(f"{source.name}: context_token_estimate must be a non-negative number")

    if not isinstance(payload["allowed_tools"], list) or not all(
        validate_string(item) for item in payload["allowed_tools"]
    ):
        errors.append(f"{source.name}: 'allowed_tools' must be a string array")

    if not isinstance(payload["evidence"], list):
        errors.append(f"{source.name}: 'evidence' must be an array")
    else:
        for index, item in enumerate(payload["evidence"]):
            errors.extend(validate_evidence_item(item, source, index))

    if not isinstance(payload["state_delta"], dict):
        errors.append(f"{source.name}: 'state_delta' must be an object")
    else:
        for key in REQUIRED_STATE_KEYS:
            if key not in payload["state_delta"]:
                errors.append(f"{source.name}: state_delta missing '{key}'")
                continue
            value = payload["state_delta"][key]
            if not isinstance(value, list):
                errors.append(f"{source.name}: state_delta.{key} must be an array")
                continue
            for item in value:
                if key in {"facts", "preferences"}:
                    errors.extend(validate_fact_like(item, source, f"state_delta.{key}"))
                elif key == "decisions":
                    errors.extend(validate_decision_item(item, source))
                elif key == "risks":
                    errors.extend(validate_risk_item(item, source))

    if not isinstance(payload["risks"], list) or not all(
        validate_string(item) for item in payload["risks"]
    ):
        errors.append(f"{source.name}: 'risks' must be a string array")

    if payload["fallback_suggestion"] not in VALID_FALLBACKS:
        errors.append(f"{source.name}: invalid fallback_suggestion")

    if not isinstance(payload["next_steps"], list) or not all(
        validate_string(item) for item in payload["next_steps"]
    ):
        errors.append(f"{source.name}: 'next_steps' must be a string array")

    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        errors.append(f"{source.name}: 'confidence' must be a number between 0 and 1")

    errors.extend(validate_compression_proposal_extras(payload, source))

    return errors


def validate_string_array(value: Any, source: Path, label: str) -> list[str]:
    if not isinstance(value, list) or not all(validate_string(item) for item in value):
        return [f"{source.name}: {label} must be a string array"]
    return []


def validate_context_block_entry(item: Any, source: Path, label: str) -> list[str]:
    errors: list[str] = []
    if isinstance(item, str):
        return []
    if not isinstance(item, dict):
        return [f"{source.name}: {label} item must be a string or object"]
    if "key" in item and not validate_string(item["key"]):
        errors.append(f"{source.name}: {label}.key must be a string")
    if "value" in item and not validate_string(item["value"]):
        errors.append(f"{source.name}: {label}.value must be a string")
    if "scope" in item and item["scope"] not in VALID_SCOPES:
        errors.append(f"{source.name}: {label}.scope is invalid")
    if "confidence_score" in item and not isinstance(item["confidence_score"], (int, float)):
        errors.append(f"{source.name}: {label}.confidence_score must be numeric")
    if "source_memory_ids" in item:
        errors.extend(validate_string_array(item["source_memory_ids"], source, f"{label}.source_memory_ids"))
    if "evidence_ids" in item:
        errors.extend(validate_string_array(item["evidence_ids"], source, f"{label}.evidence_ids"))
    return errors


def validate_recall_package(payload: Any, source: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{source.name}: recall package must be a JSON object"]

    if payload.get("schema_version") != RECALL_PACKAGE_SCHEMA_VERSION:
        errors.append(f"{source.name}: schema_version must be {RECALL_PACKAGE_SCHEMA_VERSION}")

    for key in (
        "workspace_id",
        "context_snapshot_id",
        "role",
        "trigger",
        "query",
        "context_text",
    ):
        if not validate_string(payload.get(key)):
            errors.append(f"{source.name}: {key} must be a string")

    if payload.get("role") not in VALID_ROLES:
        errors.append(f"{source.name}: role is invalid")

    if payload.get("trigger") not in VALID_TRIGGER_VALUES:
        errors.append(f"{source.name}: trigger is invalid")

    run_revision = payload.get("run_revision")
    if not isinstance(run_revision, int) or run_revision < 1:
        errors.append(f"{source.name}: run_revision must be a positive integer")

    context_blocks = payload.get("context_blocks")
    if not isinstance(context_blocks, dict):
        errors.append(f"{source.name}: context_blocks must be an object")
    else:
        unknown_blocks = set(context_blocks) - VALID_CONTEXT_BLOCKS
        if unknown_blocks:
            errors.append(f"{source.name}: context_blocks contains invalid block names")
        for block_name, items in context_blocks.items():
            if not isinstance(items, list):
                errors.append(f"{source.name}: context_blocks.{block_name} must be an array")
                continue
            for item in items:
                errors.extend(validate_context_block_entry(item, source, f"context_blocks.{block_name}"))

    if "source_context_blocks" not in payload:
        errors.append(f"{source.name}: source_context_blocks is required")
    else:
        errors.extend(validate_string_array(payload["source_context_blocks"], source, "source_context_blocks"))
        if isinstance(payload["source_context_blocks"], list) and not all(
            item in VALID_CONTEXT_BLOCKS for item in payload["source_context_blocks"]
        ):
            errors.append(f"{source.name}: source_context_blocks contains invalid block names")
        if isinstance(context_blocks, dict) and isinstance(payload["source_context_blocks"], list):
            missing_from_context_blocks = set(payload["source_context_blocks"]) - set(context_blocks)
            if missing_from_context_blocks:
                errors.append(
                    f"{source.name}: source_context_blocks must be a subset of context_blocks keys"
                )

    if "stale_or_superseded" in payload:
        stale_items = payload["stale_or_superseded"]
        if not isinstance(stale_items, list):
            errors.append(f"{source.name}: stale_or_superseded must be an array")
        else:
            for index, item in enumerate(stale_items):
                if not isinstance(item, dict):
                    errors.append(f"{source.name}: stale_or_superseded[{index}] must be an object")
                    continue
                if not validate_string(item.get("reason")):
                    errors.append(f"{source.name}: stale_or_superseded[{index}].reason must be a string")
                if not (validate_string(item.get("memory_id")) or validate_string(item.get("identity"))):
                    errors.append(
                        f"{source.name}: stale_or_superseded[{index}] requires memory_id or identity"
                    )

    context_token_estimate = payload.get("context_token_estimate")
    if not isinstance(context_token_estimate, (int, float)) or float(context_token_estimate) < 0:
        errors.append(f"{source.name}: context_token_estimate must be a non-negative number")

    budget_profile = payload.get("budget_profile")
    if not isinstance(budget_profile, dict):
        errors.append(f"{source.name}: budget_profile must be an object")
    else:
        for key in ("role_multiplier", "model_multiplier", "max_tokens"):
            value = budget_profile.get(key)
            if not isinstance(value, (int, float)) or float(value) < 0:
                errors.append(f"{source.name}: budget_profile.{key} must be a non-negative number")

    return errors


def validate_compression_proposal_extras(payload: dict[str, Any], source: Path) -> list[str]:
    errors: list[str] = []
    schema_version = payload.get("schema_version")
    proposal_kind = payload.get("proposal_kind")
    is_compression = schema_version == COMPRESSION_PROPOSAL_SCHEMA_VERSION or proposal_kind == VALID_COMPRESSION_PROPOSAL_KIND
    if not is_compression:
        return errors

    if schema_version != COMPRESSION_PROPOSAL_SCHEMA_VERSION:
        errors.append(f"{source.name}: schema_version must be {COMPRESSION_PROPOSAL_SCHEMA_VERSION}")
    if proposal_kind != VALID_COMPRESSION_PROPOSAL_KIND:
        errors.append(f"{source.name}: proposal_kind must be {VALID_COMPRESSION_PROPOSAL_KIND}")

    manifest = payload.get("compression_manifest")
    if not isinstance(manifest, dict):
        return errors + [f"{source.name}: compression_manifest must be an object"]

    for key in ("target_workspace_id", "target_scope", "rollback_basis", "source_evidence_hash"):
        if not validate_string(manifest.get(key)):
            errors.append(f"{source.name}: compression_manifest.{key} must be a string")
    if manifest.get("target_scope") not in VALID_SCOPES:
        errors.append(f"{source.name}: compression_manifest.target_scope is invalid")

    for key in ("source_memory_ids", "source_identities", "raw_audit_trail_hashes"):
        if key not in manifest:
            errors.append(f"{source.name}: compression_manifest.{key} is required")
        else:
            errors.extend(validate_string_array(manifest[key], source, f"compression_manifest.{key}"))

    if "risk_resolution_mode" in manifest and not validate_string(manifest["risk_resolution_mode"]):
        errors.append(f"{source.name}: compression_manifest.risk_resolution_mode must be a string")

    if "conflict_class" in manifest and not validate_string(manifest["conflict_class"]):
        errors.append(f"{source.name}: compression_manifest.conflict_class must be a string")

    state_delta = payload.get("state_delta", {})
    if state_delta.get("preferences"):
        errors.append(f"{source.name}: compression proposals must not write state_delta.preferences")
    if state_delta.get("decisions"):
        errors.append(f"{source.name}: compression proposals must not write state_delta.decisions")

    target_scope = manifest.get("target_scope")
    for block_name in REQUIRED_STATE_KEYS:
        for item in state_delta.get(block_name, []):
            if not isinstance(item, dict):
                continue
            item_scope = item.get("scope")
            if item_scope in VALID_SCOPES and target_scope in VALID_SCOPES and item_scope != target_scope:
                errors.append(
                    f"{source.name}: compression proposal {block_name} scope must match compression_manifest.target_scope"
                )

    for item in state_delta.get("facts", []):
        if not isinstance(item, dict):
            continue
        value = item.get("value", "")
        if isinstance(value, str) and not (
            value.startswith("[Compressed]") or value.startswith("[Derived]")
        ):
            errors.append(f"{source.name}: compression facts must start with [Compressed] or [Derived]")

    return errors


def detect_schema_kind(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    if payload.get("schema_version") == RECALL_PACKAGE_SCHEMA_VERSION:
        return "recall_package"
    if (
        payload.get("schema_version") == COMPRESSION_PROPOSAL_SCHEMA_VERSION
        or payload.get("proposal_kind") == VALID_COMPRESSION_PROPOSAL_KIND
    ):
        return "compression_proposal"
    return "proposal"


def normalize_state_entry(
    kind: str,
    item: Any,
    source_file: Path,
    *,
    payload_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(item, str):
        return {
            "kind": kind,
            "scope": "task",
            "source": "legacy_string",
            "legacy_text": item,
            "identity": item,
            "value_signature": item,
            "evidence_ids": [],
            "source_file": str(source_file),
            **(payload_meta or {}),
        }

    normalized = dict(item)
    if payload_meta:
        normalized.update(payload_meta)
    normalized["kind"] = kind
    normalized["source_file"] = str(source_file)
    normalized.setdefault("evidence_ids", [])
    normalized["identity"] = build_identity(kind, normalized)
    normalized["value_signature"] = build_value_signature(kind, normalized)
    return normalized


def build_identity(kind: str, item: dict[str, Any]) -> str:
    scope = item.get("scope", "task")
    if kind in {"facts", "preferences"}:
        key = item.get("key", item.get("legacy_text", ""))
    elif kind == "decisions":
        key = item.get("topic", item.get("legacy_text", ""))
    else:
        key = item.get("risk", item.get("legacy_text", ""))
    return f"{kind}:{scope}:{key}"


def build_value_signature(kind: str, item: dict[str, Any]) -> str:
    if kind in {"facts", "preferences"}:
        value = {
            "key": item.get("key"),
            "value": item.get("value"),
            "proposal_type": item.get("proposal_type"),
        }
    elif kind == "decisions":
        value = {
            "topic": item.get("topic"),
            "decision": item.get("decision"),
            "proposal_type": item.get("proposal_type"),
        }
    else:
        value = {
            "risk": item.get("risk"),
            "impact": item.get("impact"),
            "likelihood": item.get("likelihood"),
        }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def merge_payloads(payloads: list[dict[str, Any]], files: list[Path]) -> dict[str, list[Any]]:
    merged: dict[str, list[Any]] = {key: [] for key in REQUIRED_STATE_KEYS}
    for payload, file_path in zip(payloads, files, strict=False):
        state_delta = payload["state_delta"]
        payload_meta: dict[str, Any] = {}
        if detect_schema_kind(payload) == "compression_proposal":
            payload_meta = {
                "schema_version": payload.get("schema_version"),
                "proposal_kind": payload.get("proposal_kind"),
                "compression_manifest": payload.get("compression_manifest"),
            }
        for key in REQUIRED_STATE_KEYS:
            merged[key].extend(
                normalize_state_entry(key, item, file_path, payload_meta=payload_meta)
                for item in state_delta.get(key, [])
            )
    return {key: uniq_json(values) for key, values in merged.items()}


def build_role_context_report(payloads: list[dict[str, Any]], files: list[Path]) -> dict[str, Any]:
    per_file: list[dict[str, Any]] = []
    for payload, file_path in zip(payloads, files, strict=False):
        role = payload.get("role")
        if not role:
            continue
        context_blocks = payload.get("context_blocks", [])
        allowed = sorted(ROLE_ALLOWED_BLOCKS.get(role, VALID_CONTEXT_BLOCKS))
        ok = set(context_blocks).issubset(set(allowed))
        per_file.append(
            {
                "file": str(file_path),
                "role": role,
                "context_blocks": context_blocks,
                "allowed_blocks": allowed,
                "memory_access_mode": payload.get("memory_access_mode"),
                "ok": ok and payload.get("memory_access_mode") == PACKAGED_CONTEXT_ONLY,
            }
        )
    return {
        "ok": all(item["ok"] for item in per_file),
        "per_file": per_file,
    }


def build_snapshot_consistency_report(payloads: list[dict[str, Any]], files: list[Path]) -> dict[str, Any]:
    per_file: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    role_payloads = 0
    snapshot_groups: dict[tuple[str, int], list[str]] = defaultdict(list)

    for payload, file_path in zip(payloads, files, strict=False):
        role = payload.get("role")
        if not role:
            continue
        role_payloads += 1
        snapshot_id = payload.get("context_snapshot_id")
        run_revision = payload.get("run_revision")
        missing_fields: list[str] = []
        if not validate_string(snapshot_id):
            missing_fields.append("context_snapshot_id")
        if not isinstance(run_revision, int) or run_revision < 1:
            missing_fields.append("run_revision")

        item = {
            "file": str(file_path),
            "role": role,
            "context_snapshot_id": snapshot_id,
            "run_revision": run_revision,
            "ok": not missing_fields,
        }
        if missing_fields:
            item["missing_fields"] = missing_fields
            violations.append(
                {
                    "file": str(file_path),
                    "role": role,
                    "reason": "missing_snapshot_fields",
                    "missing_fields": missing_fields,
                }
            )
        else:
            snapshot_groups[(str(snapshot_id), int(run_revision))].append(str(file_path))
        per_file.append(item)

    if len(snapshot_groups) > 1:
        violations.append(
            {
                "reason": "cross_snapshot_merge_forbidden",
                "snapshot_groups": [
                    {
                        "context_snapshot_id": snapshot_id,
                        "run_revision": run_revision,
                        "files": sorted(group_files),
                    }
                    for (snapshot_id, run_revision), group_files in sorted(snapshot_groups.items())
                ],
            }
        )

    return {
        "ok": role_payloads == 0 or (not violations and len(snapshot_groups) <= 1),
        "role_payloads": role_payloads,
        "snapshot_group_count": len(snapshot_groups),
        "per_file": per_file,
        "violations": violations,
    }


def build_budget_report(
    payloads: list[dict[str, Any]], files: list[Path], max_stage_context_tokens: float, max_long_term_tokens: float
) -> dict[str, Any]:
    per_file: list[dict[str, Any]] = []
    total_tokens = 0.0
    for payload, file_path in zip(payloads, files, strict=False):
        estimate = float(payload.get("context_token_estimate", 0.0))
        total_tokens += estimate
        per_file.append(
            {
                "file": str(file_path),
                "role": payload.get("role"),
                "context_token_estimate": estimate,
            }
        )
    violations: list[str] = []
    if total_tokens > max_stage_context_tokens:
        violations.append("stage_context_budget_exceeded")
    if total_tokens > max_long_term_tokens:
        violations.append("long_term_context_budget_exceeded")
    return {
        "ok": not violations,
        "total_context_tokens": total_tokens,
        "max_stage_context_tokens": max_stage_context_tokens,
        "max_long_term_tokens": max_long_term_tokens,
        "violations": violations,
        "per_file": per_file,
    }


def choose_best_candidate(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    for item in items:
        score = 0
        if item.get("source") != "model_inference":
            score += 2
        if item.get("evidence_ids"):
            score += 2
        if item.get("scope") == "task":
            score += 1
        if item.get("source") == "approved_decision":
            score += 1
        if score > best_score:
            best = item
            best_score = score
    return best


def build_approval_report(merged_state: dict[str, list[Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in REQUIRED_STATE_KEYS:
        for item in merged_state[key]:
            grouped[item["identity"]].append(item)

    approved: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []

    for identity, items in grouped.items():
        value_signatures = {item["value_signature"] for item in items}
        best = choose_best_candidate(items)
        if best is None:
            continue

        scope = best.get("scope", "task")
        source = best.get("source")
        evidence_ids = best.get("evidence_ids", [])
        compression_manifest = best.get("compression_manifest")
        reason = ""
        action = "approved"

        if source == "legacy_string":
            action = "deferred"
            reason = "legacy_state_delta_requires_manual_review"
        elif len(value_signatures) > 1:
            action = "deferred"
            reason = "conflicting_candidates_require_review"
        elif source == "model_inference" and scope in {"workspace", "user_global"}:
            action = "rejected"
            reason = "model_inference_cannot_write_long_term_memory"
        elif (
            best["kind"] in {"facts", "preferences", "decisions"}
            and best.get("proposal_type") in {"update", "invalidate"}
            and not evidence_ids
        ):
            action = "deferred"
            reason = "update_or_invalidate_requires_evidence"
        elif scope in {"workspace", "user_global"} and not evidence_ids:
            action = "deferred"
            reason = "long_term_memory_requires_evidence"
        elif isinstance(compression_manifest, dict) and compression_manifest.get("conflict_class") not in {None, "none"}:
            action = "deferred"
            reason = "compression_manifest_conflict_requires_review"
        else:
            action = "approved"
            reason = "meets_scope_and_evidence_requirements"

        report_item = {
            "identity": identity,
            "kind": best["kind"],
            "scope": scope,
            "source": source,
            "proposal_type": best.get("proposal_type"),
            "source_files": sorted({item["source_file"] for item in items}),
            "evidence_ids": evidence_ids,
            "reason": reason,
        }

        if action == "approved":
            approved.append(report_item)
            audit_records.append(
                {
                    **report_item,
                    "approved_by": "main_agent",
                    "status": "approved",
                }
            )
        elif action == "deferred":
            deferred.append(report_item)
        else:
            rejected.append(report_item)

    return {
        "approved": approved,
        "deferred": deferred,
        "rejected": rejected,
        "audit_records": audit_records,
        "ok": not rejected,
    }


def build_fallback_report(payloads: list[dict[str, Any]], files: list[Path]) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    for payload, file_path in zip(payloads, files, strict=False):
        suggestion = payload.get("fallback_suggestion")
        if suggestion is None:
            continue
        routes.append(
            {
                "file": str(file_path),
                "role": payload.get("role"),
                "fallback_suggestion": suggestion,
                "action": FALLBACK_ACTIONS[suggestion],
                "summary": payload.get("summary"),
            }
        )
    return {
        "ok": all(route["fallback_suggestion"] in FALLBACK_ACTIONS for route in routes),
        "routes": routes,
    }


def build_contract_assertions(
    payloads: list[dict[str, Any]],
    role_context_report: dict[str, Any],
    snapshot_consistency_report: dict[str, Any],
    budget_report: dict[str, Any],
    approval_report: dict[str, Any],
    fallback_report: dict[str, Any],
) -> dict[str, bool]:
    has_structured_entries = False
    for payload in payloads:
        for key in REQUIRED_STATE_KEYS:
            if any(isinstance(item, dict) for item in payload["state_delta"].get(key, [])):
                has_structured_entries = True
                break
        if has_structured_entries:
            break

    role_payloads = [payload for payload in payloads if payload.get("role")]
    unique_memory_entry_ok = all(
        payload.get("memory_access_mode") == PACKAGED_CONTEXT_ONLY for payload in role_payloads
    )

    return {
        "unique_memory_entry_ok": unique_memory_entry_ok,
        "role_distribution_ok": role_context_report["ok"],
        "snapshot_consistency_ok": snapshot_consistency_report["ok"],
        "structured_proposals_ok": has_structured_entries,
        "approval_writeback_ready": approval_report["ok"] and len(approval_report["approved"]) > 0,
        "budget_fuse_ok": budget_report["ok"],
        "fallback_routing_ok": fallback_report["ok"],
    }


def build_report(
    files: list[Path], max_stage_context_tokens: float, max_long_term_tokens: float
) -> dict[str, Any]:
    validation_errors: list[str] = []
    payloads: list[dict[str, Any]] = []
    valid_files: list[Path] = []
    file_reports: list[dict[str, Any]] = []
    recall_package_reports: list[dict[str, Any]] = []

    for file_path in files:
        payload = load_json(file_path)
        schema_kind = detect_schema_kind(payload)
        if schema_kind == "recall_package":
            errors = validate_recall_package(payload, file_path)
        else:
            errors = validate_payload(payload, file_path)
        file_reports.append(
            {
                "file": str(file_path),
                "schema_kind": schema_kind,
                "valid": not errors,
                "role": payload.get("role"),
                "fallback_suggestion": payload.get("fallback_suggestion"),
                "confidence": payload.get("confidence"),
                "errors": errors,
            }
        )
        if schema_kind == "recall_package":
            recall_package_reports.append(
                {
                    "file": str(file_path),
                    "valid": not errors,
                    "workspace_id": payload.get("workspace_id"),
                    "context_snapshot_id": payload.get("context_snapshot_id"),
                    "run_revision": payload.get("run_revision"),
                    "role": payload.get("role"),
                    "source_context_blocks": payload.get("source_context_blocks"),
                    "errors": errors,
                }
            )
        validation_errors.extend(errors)
        if not errors and schema_kind != "recall_package":
            payloads.append(payload)
            valid_files.append(file_path)

    merged_state = merge_payloads(payloads, valid_files) if payloads else {key: [] for key in REQUIRED_STATE_KEYS}
    role_context_report = build_role_context_report(payloads, valid_files)
    snapshot_consistency_report = build_snapshot_consistency_report(payloads, valid_files)
    budget_report = build_budget_report(
        payloads, valid_files, max_stage_context_tokens=max_stage_context_tokens, max_long_term_tokens=max_long_term_tokens
    )
    approval_report = build_approval_report(merged_state)
    fallback_report = build_fallback_report(payloads, valid_files)
    contract_assertions = build_contract_assertions(
        payloads,
        role_context_report=role_context_report,
        snapshot_consistency_report=snapshot_consistency_report,
        budget_report=budget_report,
        approval_report=approval_report,
        fallback_report=fallback_report,
    )

    ok = not validation_errors and (all(contract_assertions.values()) if payloads else True)

    return {
        "ok": ok,
        "files_checked": len(files),
        "valid_files": len(payloads),
        "validation_errors": validation_errors,
        "file_reports": file_reports,
        "recall_package_reports": recall_package_reports,
        "role_context_report": role_context_report,
        "snapshot_consistency_report": snapshot_consistency_report,
        "budget_report": budget_report,
        "merged_state": merged_state,
        "approval_report": approval_report,
        "fallback_report": fallback_report,
        "contract_assertions": contract_assertions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSON files to validate and merge")
    parser.add_argument(
        "--max-stage-context-tokens",
        type=float,
        default=1200,
        help="Budget limit for the full stage context window",
    )
    parser.add_argument(
        "--max-long-term-tokens",
        type=float,
        default=1200,
        help="Budget limit for the sum of long-term context assigned to all subagents in this stage",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the merged validation report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = [Path(item) for item in args.inputs]
    report = build_report(
        files,
        max_stage_context_tokens=args.max_stage_context_tokens,
        max_long_term_tokens=args.max_long_term_tokens,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
