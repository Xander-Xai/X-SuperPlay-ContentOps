#!/usr/bin/env python3
"""Regression tests for the external-policy approval-event HMAC chain."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from record_approval import record
from sign_approval_events import init_policy, sign_events, verify_events
from workflow_gate import _approval_signature_errors


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="approval-signature-") as raw:
        root = Path(raw)
        article = root / "article"
        article.mkdir()
        scoped = article / "review-checks.json"
        scoped.write_text('{"status":"passed"}', encoding="utf-8")
        key = root / "signing.key"
        key.write_bytes(b"test-only-secret-key-" * 3)
        policy = root / "approval-policy.json"
        assert init_policy(str(policy), article, "test-key") == 0
        assert record(article, subject="factual_review", reviewer_type="human", reviewer="editor", signed_by="editor(manual)", scope="review-checks.json", summary="fixture") == 0
        assert sign_events(article, str(policy), str(key), migrate=True) == 0
        assert verify_events(article, str(policy), str(key)) == []
        (article / "content-brief.yaml").write_text("risk_level: high\nhuman_review_required: true\n", encoding="utf-8")
        (article / "capability-profile.json").write_text(json.dumps({"approval_signature_required": True}), encoding="utf-8")
        old_policy = os.environ.get("APPROVAL_SIGNATURE_POLICY_PATH")
        old_key = os.environ.get("APPROVAL_SIGNATURE_KEY_PATH")
        os.environ.pop("APPROVAL_SIGNATURE_POLICY_PATH", None)
        os.environ.pop("APPROVAL_SIGNATURE_KEY_PATH", None)
        assert _approval_signature_errors(article), "required policy/key must fail closed"
        os.environ["APPROVAL_SIGNATURE_POLICY_PATH"] = str(policy)
        os.environ["APPROVAL_SIGNATURE_KEY_PATH"] = str(key)
        assert _approval_signature_errors(article) == []
        if old_policy is None:
            os.environ.pop("APPROVAL_SIGNATURE_POLICY_PATH", None)
        else:
            os.environ["APPROVAL_SIGNATURE_POLICY_PATH"] = old_policy
        if old_key is None:
            os.environ.pop("APPROVAL_SIGNATURE_KEY_PATH", None)
        else:
            os.environ["APPROVAL_SIGNATURE_KEY_PATH"] = old_key
        events_path = article / "approval-events.json"
        events = json.loads(events_path.read_text(encoding="utf-8"))
        events[0]["reviewer"] = "tampered"
        events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        assert verify_events(article, str(policy), str(key)), "tampering must block"
        # Restore from the signed snapshot, then prove deleting the first event
        # cannot pass because the genesis/expected head chain is broken.
        events[0]["reviewer"] = "editor"
        events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        assert verify_events(article, str(policy), str(key)) == []
        events_path.write_text("[]", encoding="utf-8")
        assert verify_events(article, str(policy), str(key)), "truncation must block"
        # Duplicate JSON keys are rejected instead of silently choosing first/last.
        events_path.write_text('{"event_id":"a","event_id":"b"}', encoding="utf-8")
        assert verify_events(article, str(policy), str(key)), "duplicate keys must block"
    print("SIGNATURE EVENT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
