"""Interface and behavioral tests for v0.2.0 team workspace CRUD endpoints.

Tests team creation, listing, member management, and role changes.
"""

from __future__ import annotations

from inspect import signature

import pytest

# Mark as quick (unit tests)
pytestmark = pytest.mark.quick


# ── Interface Tests (must PASS) ───────────────────────────────────────────────


class TestTeamsInterface:
    """Verify team route module with correct contracts."""

    def test_teams_module_importable(self):
        from meeting_notes_ai.routes.teams import router

        assert router is not None
        assert router.prefix == "/api/v1/teams"

    def test_teams_router_has_tags(self):
        from meeting_notes_ai.routes.teams import router

        assert "teams" in router.tags

    # ── Schemas ───────────────────────────────────────────────────────────────

    def test_team_create_request_importable(self):
        from meeting_notes_ai.routes.teams import TeamCreateRequest

        assert TeamCreateRequest is not None

    def test_team_create_request_fields(self):
        from meeting_notes_ai.routes.teams import TeamCreateRequest

        fields = TeamCreateRequest.model_fields
        assert "name" in fields
        assert "description" in fields

    def test_team_response_importable(self):
        from meeting_notes_ai.routes.teams import TeamResponse

        assert TeamResponse is not None

    def test_team_response_fields(self):
        from meeting_notes_ai.routes.teams import TeamResponse

        fields = TeamResponse.model_fields
        assert "id" in fields
        assert "name" in fields
        assert "owner_id" in fields
        assert "member_count" in fields
        assert "created_at" in fields

    def test_invite_member_request_importable(self):
        from meeting_notes_ai.routes.teams import InviteMemberRequest

        assert InviteMemberRequest is not None

    def test_invite_member_request_fields(self):
        from meeting_notes_ai.routes.teams import InviteMemberRequest

        fields = InviteMemberRequest.model_fields
        assert "email" in fields
        assert "role" in fields

    def test_change_role_request_importable(self):
        from meeting_notes_ai.routes.teams import ChangeRoleRequest

        assert ChangeRoleRequest is not None

    def test_change_role_request_fields(self):
        from meeting_notes_ai.routes.teams import ChangeRoleRequest

        fields = ChangeRoleRequest.model_fields
        assert "role" in fields

    def test_member_response_importable(self):
        from meeting_notes_ai.routes.teams import MemberResponse

        assert MemberResponse is not None

    def test_member_response_fields(self):
        from meeting_notes_ai.routes.teams import MemberResponse

        fields = MemberResponse.model_fields
        assert "user_id" in fields
        assert "role" in fields
        assert "email" in fields

    def test_team_list_response_importable(self):
        from meeting_notes_ai.routes.teams import TeamListResponse

        assert TeamListResponse is not None

    def test_team_list_response_has_teams(self):
        from meeting_notes_ai.routes.teams import TeamListResponse

        fields = TeamListResponse.model_fields
        assert "teams" in fields

    # ── Route registration ────────────────────────────────────────────────────

    def test_create_team_route_registered(self):
        from meeting_notes_ai.routes.teams import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        create_routes = [r for r in routes if "POST" in (getattr(r, "methods", set()))]
        assert len(create_routes) >= 1

    def test_list_teams_route_registered(self):
        from meeting_notes_ai.routes.teams import router

        routes = [r for r in router.routes if hasattr(r, "methods") and "GET" in r.methods]
        assert len(routes) >= 1

    def test_invite_member_route_registered(self):
        from meeting_notes_ai.routes.teams import router

        routes = [r for r in router.routes if hasattr(r, "path")]
        assert any("members" in r.path for r in routes)

    def test_team_handler_signatures(self):
        from meeting_notes_ai.routes.teams import (
            change_member_role,
            create_team,
            get_team,
            invite_member,
            list_teams,
            remove_member,
        )

        assert callable(create_team)
        assert callable(list_teams)
        assert callable(get_team)
        assert callable(invite_member)
        assert callable(change_member_role)
        assert callable(remove_member)

    def test_all_team_handlers_are_async(self):
        import inspect

        from meeting_notes_ai.routes.teams import (
            change_member_role,
            create_team,
            get_team,
            invite_member,
            list_teams,
            remove_member,
        )

        for handler in [create_team, list_teams, get_team, invite_member, change_member_role, remove_member]:
            assert inspect.iscoroutinefunction(handler), f"{handler.__name__} is not async"

    def test_create_team_accepts_user_depends(self):
        from meeting_notes_ai.routes.teams import create_team

        sig = signature(create_team)
        assert "user" in sig.parameters or "request" in sig.parameters


# ── Behavioral Tests (schema/model tests) ────────────────────────────────────


class TestTeamsBehavioral:
    """Verify team schemas and responses work correctly."""

    def test_team_create_request_basic(self):
        """TeamCreateRequest works with basic fields."""
        from meeting_notes_ai.routes.teams import TeamCreateRequest

        req = TeamCreateRequest(name="My Team")
        assert req.name == "My Team"
        assert req.description is None

    def test_team_create_request_with_description(self):
        """TeamCreateRequest works with description."""
        from meeting_notes_ai.routes.teams import TeamCreateRequest

        req = TeamCreateRequest(name="My Team", description="A test team")
        assert req.description == "A test team"

    def test_invite_member_request_default_role(self):
        """InviteMemberRequest defaults to MEMBER role."""
        from meeting_notes_ai.routes.teams import InviteMemberRequest

        req = InviteMemberRequest(email="test@example.com")
        assert req.email == "test@example.com"
        assert req.role.value == "member"

    def test_member_response_construct(self):
        """MemberResponse constructs correctly."""
        from meeting_notes_ai.db.models import TeamRole

        from meeting_notes_ai.routes.teams import MemberResponse

        resp = MemberResponse(
            user_id="u-1",
            email="user@example.com",
            role=TeamRole.ADMIN,
        )
        assert resp.user_id == "u-1"
        assert resp.email == "user@example.com"
        assert resp.role == TeamRole.ADMIN
