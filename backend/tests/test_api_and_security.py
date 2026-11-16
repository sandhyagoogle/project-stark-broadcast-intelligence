from __future__ import annotations

import secrets
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _ephemeral_access_password(monkeypatch: pytest.MonkeyPatch) -> str:
    pw = f"ephemeral-{secrets.token_hex(12)}"
    monkeypatch.setenv("COURTVISION_ACCESS_PASSWORD", pw)
    return pw


def _login_test_client(client: TestClient, password: str) -> str:
    status_res = client.get("/api/auth/status")
    assert status_res.status_code == 200
    pre_csrf = status_res.json()["csrf_token"]
    login_res = client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": pre_csrf},
        json={"password": password},
    )
    assert login_res.status_code == 200
    return login_res.json()["csrf_token"]


def test_password_gate_blocks_unauthenticated_and_unlocks_on_login(
    _ephemeral_access_password: str,
) -> None:
    with TestClient(app) as client:
        # Unauthenticated API requests must fail closed with 401
        assert client.get("/api/videos").status_code == 401
        assert client.get("/api/knowledge-base/rules").status_code == 401

        status_res = client.get("/api/auth/status")
        assert status_res.status_code == 200
        assert status_res.json()["authenticated"] is False
        assert status_res.headers["X-Frame-Options"] == "DENY"
        assert status_res.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in status_res.headers["Content-Security-Policy"]
        pre_csrf = status_res.json()["csrf_token"]

        # Login without CSRF must return 403
        assert (
            client.post("/api/auth/login", json={"password": _ephemeral_access_password}).status_code
            == 403
        )

        # Wrong password must return 401
        wrong_res = client.post(
            "/api/auth/login",
            headers={"X-CSRF-Token": pre_csrf},
            json={"password": "wrong-password-attempt"},
        )
        assert wrong_res.status_code == 401

        # Correct password unlocks session and rotates CSRF token
        csrf = _login_test_client(client, _ephemeral_access_password)
        assert client.get("/api/auth/status").json()["authenticated"] is True

        res = client.get("/api/session/init")
        assert res.status_code == 200
        data = res.json()
        assert "csrf_token" in data
        assert data["default_video_model"] == "gemini-3.8-flash"

        # Logout invalidates session immediately
        logout_csrf = data["csrf_token"] or csrf
        out_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": logout_csrf})
        assert out_res.status_code == 200
        assert client.get("/api/videos").status_code == 401


def test_seeded_videos_and_knowledge_base(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        _login_test_client(client, _ephemeral_access_password)
        videos_res = client.get("/api/videos")
        assert videos_res.status_code == 200
        videos = videos_res.json()["videos"]
        assert len(videos) >= 2
        video_id = videos[0]["id"]

        detail_res = client.get(f"/api/videos/{video_id}")
        assert detail_res.status_code == 200
        assert len(detail_res.json()["events"]) > 0

        kb_res = client.get("/api/knowledge-base/rules")
        assert kb_res.status_code == 200
        kb_data = kb_res.json()
        assert kb_data["total_count"] >= 8


def test_csrf_protection_and_agent_simulation(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        token = _login_test_client(client, _ephemeral_access_password)
        # Missing CSRF token on state-changing POST should return 403
        bad_res = client.post(
            "/api/agents/simulate",
            json={
                "scenario_name": "Duke vs UNC Crunch Time",
                "game_clock": "01:48",
                "period": "2ND",
                "shot_clock": 22,
                "home_team": "DUKE",
                "away_team": "UNC",
                "home_score": 74,
                "away_score": 71,
                "play_stream_description": "Duke drives baseline for an and-one dunk (+2) and foul whistle.",
            },
        )
        assert bad_res.status_code == 403

        sim_res = client.post(
            "/api/agents/simulate",
            headers={"X-CSRF-Token": token},
            json={
                "scenario_name": "Duke vs UNC Crunch Time",
                "game_clock": "01:48",
                "period": "2ND",
                "shot_clock": 22,
                "home_team": "DUKE",
                "away_team": "UNC",
                "home_score": 74,
                "away_score": 71,
                "play_stream_description": "Duke drives baseline for an and-one dunk (+2) and foul whistle.",
            },
        )
        assert sim_res.status_code == 200
        edl = sim_res.json()
        assert len(edl["edl_steps"]) >= 4
        agents_seen = {step["invoked_agent"] for step in edl["edl_steps"]}
        assert "director" in agents_seen
        assert "replay" in agents_seen
        assert "graphics_scorebug" in agents_seen


def test_malicious_upload_rejected_by_magic_bytes(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        token = _login_test_client(client, _ephemeral_access_password)
        fake_mp4 = b"#!/bin/sh\necho pwned\n"
        res = client.post(
            "/api/videos/upload",
            headers={"X-CSRF-Token": token},
            data={"title": "Malicious Upload", "processing_mode": "agentic"},
            files={"file": ("exploit.mp4", fake_mp4, "video/mp4")},
        )
        assert res.status_code == 400
        assert "magic-byte" in res.json()["detail"].lower()


def test_skills_export_for_four_agents(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        _login_test_client(client, _ephemeral_access_password)
        res = client.get("/api/skills")
        assert res.status_code == 200
        bundle = res.json()
        assert len(bundle["packages"]) == 4
        roles = {p["agent_role"] for p in bundle["packages"]}
        assert roles == {"orchestrator", "director", "replay", "graphics_scorebug"}
        assert "LocalAgentConfig" in bundle["antigravity_runner_code"]


def test_project_stark_and_shadow_mode_evolution(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        token = _login_test_client(client, _ephemeral_access_password)
        ref_res = client.get("/api/project-stark/reference")
        assert ref_res.status_code == 200
        ref_data = ref_res.json()
        assert ref_data["metadata"]["doc_id"] == "go/project-stark-prd"
        assert len(ref_data["backlog"]) >= 10

        evolve_res = client.post(
            "/api/learning/shadow-evolve",
            headers={"X-CSRF-Token": token},
        )
        assert evolve_res.status_code == 200
        evolved = evolve_res.json()
        assert evolved["shadow_agreement_after"] > evolved["shadow_agreement_before"]
        codes = {r["rule_code"] for r in evolved["evolved_rules_added"]}
        assert {"DIR-04", "GFX-03", "RPL-03"}.issubset(codes)


def test_engineer_ask_agent_with_youtube_clips(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        token = _login_test_client(client, _ephemeral_access_password)
        ask_res = client.post(
            "/api/agents/ask",
            headers={"X-CSRF-Token": token},
            json={
                "question": "When a star player hits a 3rd three-pointer in a row on a scoring run, what should the agent do?"
            },
        )
        assert ask_res.status_code == 200
        answer = ask_res.json()
        assert answer["matched_rule_code"]
        assert answer["what_agent_should_do"]
        assert len(answer["youtube_examples"]) >= 1
        first_clip = answer["youtube_examples"][0]
        expected_start = max(0, first_clip["timestamp_seconds"] - 2)
        assert f"&t={expected_start}s" in first_clip["youtube_watch_url"]
        assert f"?start={expected_start}&" in first_clip["youtube_embed_url"]


def test_rule_review_persistence_and_comments(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        token = _login_test_client(client, _ephemeral_access_password)
        rev_res = client.post(
            "/api/knowledge-base/rules/STORY-01/review",
            headers={"X-CSRF-Token": token},
            json={
                "review_status": "partially_agree",
                "reviewer_comment": "Keep CAM-1 even higher (~75%) during full-court press games.",
                "reviewer_name": "Lead Broadcast Director",
            },
        )
        assert rev_res.status_code == 200
        data = rev_res.json()
        assert data["rule"]["rule_code"] == "STORY-01"
        assert data["rule"]["review_status"] == "partially_agree"
        assert "75%" in data["rule"]["reviewer_comment"]
        assert data["rule"]["reviewer_name"] == "Lead Broadcast Director"
        assert data["review_summary"]["partially_agree"] >= 1
        assert data["review_summary"]["with_comments"] >= 1

        # Verify persisted across subsequent GET /api/knowledge-base/rules
        kb_res = client.get("/api/knowledge-base/rules").json()
        story_01 = next(r for r in kb_res["rules"] if r["rule_code"] == "STORY-01")
        assert story_01["review_status"] == "partially_agree"
        assert "75%" in story_01["reviewer_comment"]

        # Reset back to unreviewed after test
        reset_res = client.post(
            "/api/knowledge-base/rules/STORY-01/review",
            headers={"X-CSRF-Token": token},
            json={
                "review_status": "unreviewed",
                "reviewer_comment": "",
                "reviewer_name": "Lead Broadcast Director",
            },
        )
        assert reset_res.status_code == 200
        assert reset_res.json()["rule"]["review_status"] == "unreviewed"


def test_six_gate_rule_quality_audit_and_generation_engine(_ephemeral_access_password: str) -> None:
    from app.services.rule_engine import merge_window_rules, sanitize_and_enrich_rule

    with TestClient(app) as client:
        _login_test_client(client, _ephemeral_access_password)
        audit_res = client.get("/api/knowledge-base/audit")
        assert audit_res.status_code == 200
        audit = audit_res.json()
        assert audit["total_rules"] >= 346
        assert audit["overall_quality_score"] == 100.0
        assert audit["all_gates_passed"] is True
        for gate_name, gate_info in audit["gates"].items():
            assert gate_info["passed"] is True, f"Failed {gate_name}: {gate_info}"

    # Verify NCAA domain sanitizer catches LLM NBA hallucinations & em dashes automatically
    noisy_llm_rule = {
        "rule_code": "DIR-99",
        "agent_role": "director",
        "title": "fourth-quarter buzzer — 24-second shot clock & 6th foul check",
        "trigger_condition": "In the fourth quarter when the 24-second shot clock hits 0.0 — or a star gets their 6th personal foul during an 8-second count.",
        "editor_action": "Cut immediately to `CAM_1_WIDE` — then check `CAM_2_HERO_ISO`.",
        "timing_constraint": "Never miss live play.",
        "priority": 9,
        "confidence": 0.93,
        "observed_count": 4,
        "example_timestamps": [],
    }
    cleaned = sanitize_and_enrich_rule(noisy_llm_rule)
    blob = f"{cleaned['title']} {cleaned['trigger_condition']} {cleaned['editor_action']} {cleaned['timing_constraint']}"
    assert "—" not in blob
    assert "CAM_1_WIDE" not in blob
    assert "24-second" not in blob.lower()
    assert "fourth quarter" not in blob.lower()
    assert "6th personal foul" not in blob.lower()
    assert "30-second shot clock" in blob.lower()
    assert "5th personal foul" in blob.lower()
    assert "10-second backcourt" in blob.lower()
    assert len(cleaned["example_timestamps"]) >= 1

    # Verify cross-window rule deduplication merges observed_count and timestamps while keeping distinct rules
    win_rules = [
        {
            "rule_code": "DIR-01",
            "agent_role": "director",
            "title": "Fast Inbound Celebration Cutback",
            "trigger_condition": "Opponent inbounds the ball quickly within 1.5s after a made three-pointer to push a fast break.",
            "editor_action": "Snap back from CAM-3 to CAM-1 Wide within 0.8s.",
            "timing_constraint": "Return to CAM-1 within <= 0.8s.",
            "priority": 10,
            "confidence": 0.91,
            "observed_count": 3,
            "example_timestamps": ["03:42"],
        },
        {
            "rule_code": "DIR-01",
            "agent_role": "director",
            "title": "Fast-Inbound Celebration Cutback",
            "trigger_condition": "Opponent quickly inbounds within 1.5s after a made three-pointer to push a transition fast break.",
            "editor_action": "Snap back from CAM-3 (Player Close-Up) to CAM-1 (Main Wide) within 0.8s so viewers never miss the press break.",
            "timing_constraint": "Return to CAM-1 within <= 0.8s.",
            "priority": 10,
            "confidence": 0.94,
            "observed_count": 5,
            "example_timestamps": ["14:22"],
        },
        {
            "rule_code": "RPL-01",
            "agent_role": "replay",
            "title": "Overhead Rim Angle on Goaltending Review",
            "trigger_condition": "Referees stop play to review potential basket interference or goaltending at the rim.",
            "editor_action": "Roll CAM-5 Above-Rim slow-motion angle showing ball cylinder position.",
            "timing_constraint": "Loop at 50% speed during monitor review.",
            "priority": 9,
            "confidence": 0.95,
            "observed_count": 2,
            "example_timestamps": ["29:12"],
        },
    ]
    merged = merge_window_rules(win_rules)
    assert len(merged) == 2
    assert merged[0]["observed_count"] == 8
    assert merged[0]["example_timestamps"] == ["03:42", "14:22"]


def test_healthz_spa_and_hsts_headers(_ephemeral_access_password: str) -> None:
    with TestClient(app) as client:
        health = client.get("/healthz", headers={"X-Forwarded-Proto": "https"})
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert "max-age=31536000" in health.headers["Strict-Transport-Security"]

        _login_test_client(client, _ephemeral_access_password)
        missing_api = client.get("/api/nonexistent-endpoint")
        assert missing_api.status_code == 404

        spa = client.get("/")
        assert spa.status_code == 200
        assert '<div id="root"></div>' in spa.text
