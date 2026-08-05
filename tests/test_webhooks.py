"""Interface and behavioral tests for v0.2.0 webhook notification service.

Tests webhook registration, listing, deletion, firing with retry, and payload signing.
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as integration (uses TestClient/AsyncClient)
pytestmark = pytest.mark.integration


# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestWebhooksInterface:
    """Verify webhook module exists with correct contracts."""

    # ── Route module ─────────────────────────────────────────────────────────

    def test_webhook_routes_importable(self):
        from meeting_notes_ai.routes.webhooks import router

        assert router is not None
        assert router.prefix == "/api/v1/webhooks"

    def test_webhook_routes_tags(self):
        from meeting_notes_ai.routes.webhooks import router

        assert "webhooks" in router.tags

    def test_webhook_create_route_is_post(self):
        from meeting_notes_ai.routes.webhooks import router

        for r in router.routes:
            methods = getattr(r, "methods", set())
            if "POST" in methods:
                return
        pytest.fail("POST route not found on webhook router")

    def test_webhook_list_route_is_get(self):
        from meeting_notes_ai.routes.webhooks import router

        for r in router.routes:
            methods = getattr(r, "methods", set())
            if "GET" in methods:
                return
        pytest.fail("GET route not found on webhook router")

    def test_webhook_delete_route_is_delete(self):
        from meeting_notes_ai.routes.webhooks import router

        for r in router.routes:
            methods = getattr(r, "methods", set())
            if "DELETE" in methods:
                return
        pytest.fail("DELETE route not found on webhook router")

    def test_webhook_routes_all_async(self):
        import inspect

        from meeting_notes_ai.routes.webhooks import (
            create_webhook,
            delete_webhook,
            list_webhooks,
        )

        assert inspect.iscoroutinefunction(create_webhook)
        assert inspect.iscoroutinefunction(list_webhooks)
        assert inspect.iscoroutinefunction(delete_webhook)

    # ── Service layer ─────────────────────────────────────────────────────────

    def test_webhook_service_importable(self):
        from meeting_notes_ai.services.webhooks import (
            delete_webhook,
            fire_batch_completed_webhooks,
            fire_webhook,
            list_webhooks,
            register_webhook,
            sign_payload,
        )

        assert callable(register_webhook)
        assert callable(list_webhooks)
        assert callable(delete_webhook)
        assert callable(fire_webhook)
        assert callable(fire_batch_completed_webhooks)
        assert callable(sign_payload)

    def test_webhook_subscription_create_schema(self):
        from meeting_notes_ai.services.webhooks import WebhookSubscriptionCreate

        fields = WebhookSubscriptionCreate.model_fields
        assert "url" in fields
        assert "events" in fields
        assert "secret" in fields

    def test_webhook_subscription_response_schema(self):
        from meeting_notes_ai.services.webhooks import WebhookSubscriptionResponse

        fields = WebhookSubscriptionResponse.model_fields
        assert "id" in fields
        assert "team_id" in fields
        assert "url" in fields
        assert "is_active" in fields

    def test_webhook_delivery_result_schema(self):
        from meeting_notes_ai.services.webhooks import WebhookDeliveryResult

        fields = WebhookDeliveryResult.model_fields
        assert "success" in fields
        assert "status_code" in fields
        assert "attempts" in fields

    def test_webhook_event_enum(self):
        from meeting_notes_ai.services.webhooks import WebhookEvent

        assert WebhookEvent.BATCH_COMPLETED.value == "batch.completed"
        assert WebhookEvent.BATCH_FAILED.value == "batch.failed"

    def test_register_webhook_signature(self):
        from meeting_notes_ai.services.webhooks import register_webhook

        sig = signature(register_webhook)
        assert "team_id" in sig.parameters
        assert "url" in sig.parameters
        assert "events" in sig.parameters
        assert "secret" in sig.parameters

    def test_fire_webhook_signature(self):
        from meeting_notes_ai.services.webhooks import fire_webhook

        sig = signature(fire_webhook)
        assert "webhook_id" in sig.parameters
        assert "event" in sig.parameters
        assert "payload" in sig.parameters

    def test_sign_payload_signature(self):
        from meeting_notes_ai.services.webhooks import sign_payload

        sig = signature(sign_payload)
        assert "payload" in sig.parameters
        assert "secret" in sig.parameters

    def test_webhook_service_functions_are_async(self):
        import inspect

        from meeting_notes_ai.services.webhooks import (
            fire_batch_completed_webhooks,
            fire_webhook,
            list_webhooks,
            register_webhook,
        )

        assert inspect.iscoroutinefunction(register_webhook)
        assert inspect.iscoroutinefunction(list_webhooks)
        assert inspect.iscoroutinefunction(fire_webhook)
        assert inspect.iscoroutinefunction(fire_batch_completed_webhooks)

    def test_sign_payload_is_not_async(self):
        import inspect

        from meeting_notes_ai.services.webhooks import sign_payload

        assert not inspect.iscoroutinefunction(sign_payload)

    def test_delete_webhook_is_async(self):
        import inspect

        from meeting_notes_ai.services.webhooks import delete_webhook

        assert inspect.iscoroutinefunction(delete_webhook)


# ── Behavioral Tests (real service behavior) ─────────────────────────────────


class TestWebhooksBehavioral:
    """Verify webhook services work correctly."""

    def test_sign_payload_produces_hmac(self):
        """sign_payload returns hex HMAC-SHA256 string."""
        from meeting_notes_ai.services.webhooks import sign_payload

        sig = sign_payload(payload={"key": "value"}, secret="my-secret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex digest is 64 chars
        assert all(c in "0123456789abcdef" for c in sig)

    def test_sign_payload_different_secrets(self):
        """Different secrets produce different signatures."""
        from meeting_notes_ai.services.webhooks import sign_payload

        sig1 = sign_payload(payload={"key": "value"}, secret="secret-1")
        sig2 = sign_payload(payload={"key": "value"}, secret="secret-2")
        assert sig1 != sig2

    def test_sign_payload_different_payloads(self):
        """Different payloads produce different signatures."""
        from meeting_notes_ai.services.webhooks import sign_payload

        sig1 = sign_payload(payload={"key": "value1"}, secret="secret")
        sig2 = sign_payload(payload={"key": "value2"}, secret="secret")
        assert sig1 != sig2

    def test_sign_payload_deterministic(self):
        """Same payload+secret produces same signature."""
        from meeting_notes_ai.services.webhooks import sign_payload

        sig1 = sign_payload(payload={"key": "value"}, secret="secret")
        sig2 = sign_payload(payload={"key": "value"}, secret="secret")
        assert sig1 == sig2

    def test_webhook_subscription_create_defaults(self):
        """WebhookSubscriptionCreate uses batch.completed as default event."""
        from meeting_notes_ai.services.webhooks import WebhookEvent, WebhookSubscriptionCreate

        req = WebhookSubscriptionCreate(url="https://example.com/hook")
        assert req.url == "https://example.com/hook"
        assert req.events == [WebhookEvent.BATCH_COMPLETED]
        assert req.secret is None

    def test_webhook_delivery_result_defaults(self):
        """WebhookDeliveryResult works with minimal args."""
        from meeting_notes_ai.services.webhooks import WebhookDeliveryResult

        result = WebhookDeliveryResult(success=True)
        assert result.success is True
        assert result.status_code is None
        assert result.attempts == 0
