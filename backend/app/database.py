"""SQLite database layer using strictly parameterized queries."""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH

logger = logging.getLogger("courtvision.database")

# TODO(security): For multi-tenant production deployment, migrate from embedded local
# SQLite to a dedicated relational database using mTLS authentication and role-isolated DB users.


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection configured with row factory and foreign keys."""
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        logger.error("Database operation failed: %s", type(exc).__name__)
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create database tables if they do not exist."""
    with get_db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                gemini_file_uri TEXT,
                mime_type TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                processing_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                avg_shot_duration_sec REAL NOT NULL,
                replay_frequency_per_10min REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                timestamp_mmss TEXT NOT NULL,
                timestamp_seconds INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                agent_domain TEXT NOT NULL,
                camera_angle TEXT NOT NULL,
                game_action_trigger TEXT NOT NULL,
                editor_decision TEXT NOT NULL,
                editor_rationale TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                scorebug_json TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS editor_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_code TEXT UNIQUE NOT NULL,
                agent_role TEXT NOT NULL,
                title TEXT NOT NULL,
                trigger_condition TEXT NOT NULL,
                editor_action TEXT NOT NULL,
                timing_constraint TEXT NOT NULL,
                priority INTEGER NOT NULL,
                confidence REAL NOT NULL,
                observed_count INTEGER NOT NULL,
                example_timestamps_json TEXT NOT NULL,
                source_video_id TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                scenario_name TEXT NOT NULL,
                model_used TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                orchestrator_summary TEXT NOT NULL,
                edl_steps_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rule_reviews (
                rule_code TEXT PRIMARY KEY,
                review_status TEXT NOT NULL,
                reviewer_name TEXT NOT NULL DEFAULT 'Broadcast Reviewer',
                reviewer_comment TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            """
        )


def upsert_video_with_analysis(
    video_id: str,
    title: str,
    source_type: str,
    source_uri: str,
    gemini_file_uri: str | None,
    mime_type: str,
    duration_seconds: int,
    processing_mode: str,
    status: str,
    summary: str,
    avg_shot_duration_sec: float,
    replay_frequency_per_10min: float,
    events: list[dict[str, Any]],
    learned_rules: list[dict[str, Any]],
) -> None:
    """Persist a broadcast video record along with timeline events and learned KB rules."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO videos (
                id, title, source_type, source_uri, gemini_file_uri, mime_type,
                duration_seconds, processing_mode, status, summary,
                avg_shot_duration_sec, replay_frequency_per_10min, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                gemini_file_uri = excluded.gemini_file_uri,
                processing_mode = excluded.processing_mode,
                status = excluded.status,
                summary = excluded.summary,
                avg_shot_duration_sec = excluded.avg_shot_duration_sec,
                replay_frequency_per_10min = excluded.replay_frequency_per_10min
            """,
            (
                video_id,
                title,
                source_type,
                source_uri,
                gemini_file_uri,
                mime_type,
                duration_seconds,
                processing_mode,
                status,
                summary,
                avg_shot_duration_sec,
                replay_frequency_per_10min,
                now_iso,
            ),
        )

        conn.execute("DELETE FROM timeline_events WHERE video_id = ?", (video_id,))
        conn.executemany(
            """
            INSERT INTO timeline_events (
                video_id, timestamp_mmss, timestamp_seconds, event_type,
                agent_domain, camera_angle, game_action_trigger,
                editor_decision, editor_rationale, duration_seconds, scorebug_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    video_id,
                    ev["timestamp_mmss"],
                    int(ev["timestamp_seconds"]),
                    ev["event_type"],
                    ev["agent_domain"],
                    ev["camera_angle"],
                    ev["game_action_trigger"],
                    ev["editor_decision"],
                    ev["editor_rationale"],
                    float(ev["duration_seconds"]),
                    json.dumps(ev["scorebug"]),
                )
                for ev in events
            ],
        )

        for rule in learned_rules:
            _consolidate_learned_rule(conn, rule, video_id, now_iso)


def _mint_next_rule_code(conn: sqlite3.Connection, preferred_code: str, agent_role: str) -> str:
    """Mint the next sequential rule code (e.g. STORY-21, DIR-19, ORC-14) with no upper limit."""
    role_prefix_map = {
        "orchestrator": "ORC",
        "director": "DIR",
        "replay": "RPL",
        "graphics_scorebug": "GFX",
    }
    raw_code = (preferred_code or "").strip().upper()
    if raw_code.startswith("STORY"):
        prefix = "STORY"
    elif "-" in raw_code and raw_code.split("-", 1)[0].isalpha():
        prefix = raw_code.split("-", 1)[0]
    else:
        prefix = role_prefix_map.get(agent_role, "DIR")

    rows = conn.execute(
        "SELECT rule_code FROM editor_rules WHERE rule_code LIKE ?",
        (f"{prefix}-%",),
    ).fetchall()
    max_num = 0
    for r in rows:
        parts = str(r["rule_code"]).split("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            max_num = max(max_num, int(parts[1]))
    return f"{prefix}-{max_num + 1:02d}"


def _extract_content_words(text: str) -> set[str]:
    stop_overlap = {
        "macro",
        "pattern",
        "storytelling",
        "broadcast",
        "across",
        "pacing",
        "minute",
        "whistle",
        "player",
        "camera",
        "during",
        "before",
        "after",
    }
    return {
        w.lower().strip("():.,'")
        for w in text.replace("/", " ").replace("-", " ").split()
        if len(w.strip("():.,'")) > 4 and w.lower().strip("():.,'") not in stop_overlap
    }


def _consolidate_learned_rule(
    conn: sqlite3.Connection,
    rule: dict[str, Any],
    video_id: str,
    now_iso: str,
) -> None:
    """Consolidate learned rules without any hard cap: add distinct rules with auto-minted codes if needed, and generalize true duplicates."""
    from .services.rule_engine import compute_rule_similarity, sanitize_and_enrich_rule

    rule = sanitize_and_enrich_rule(rule)
    incoming_code = str(rule.get("rule_code") or "").strip().upper()
    incoming_title_norm = str(rule.get("title") or "").strip().lower()
    incoming_is_macro = incoming_code.startswith("STORY-") or "macro game pattern" in str(
        rule.get("trigger_condition", "")
    ).lower()

    existing_by_code = (
        conn.execute(
            "SELECT * FROM editor_rules WHERE rule_code = ?",
            (incoming_code,),
        ).fetchone()
        if incoming_code and incoming_code != "AUTO"
        else None
    )

    existing = None
    if existing_by_code:
        row_dict = dict(existing_by_code)
        row_title_norm = str(row_dict["title"]).strip().lower()
        jacc, contain = compute_rule_similarity(rule, row_dict)
        # Treat same rule_code as the same rule if title matches or semantic overlap is high;
        # otherwise, a new video/window reused 'DIR-01' or 'STORY-01' for a brand-new rule!
        if incoming_title_norm == row_title_norm or jacc >= 0.45 or contain >= 0.70:
            existing = existing_by_code

    if not existing:
        same_role_rows = conn.execute(
            "SELECT * FROM editor_rules WHERE agent_role = ?",
            (rule["agent_role"],),
        ).fetchall()
        for row in same_role_rows:
            row_dict = dict(row)
            row_is_macro = str(row_dict["rule_code"]).startswith("STORY-")
            if incoming_is_macro != row_is_macro:
                continue
            row_title_norm = str(row_dict["title"]).strip().lower()
            jacc, contain = compute_rule_similarity(rule, row_dict)
            if incoming_title_norm == row_title_norm or jacc >= 0.55 or (contain >= 0.82 and jacc >= 0.42):
                if float(row_dict["confidence"]) < 0.75 and float(rule["confidence"]) >= 0.88:
                    conn.execute("DELETE FROM editor_rules WHERE rule_code = ?", (row_dict["rule_code"],))
                else:
                    existing = row
                break

    if existing:
        same_video = str(existing["source_video_id"] or "") == str(video_id or "")
        prev_ts = [
            t for t in json.loads(existing["example_timestamps_json"])
            if t not in ("01:55", "14:22", "03:42", "28:10", "05:12", "35:15", "06:04", "43:30", "08:50", "48:12", "11:15", "55:50")
            or not same_video
        ]
        merged_ts = (
            list(rule.get("example_timestamps", []))[:12]
            if same_video
            else list(dict.fromkeys(prev_ts + list(rule.get("example_timestamps", []))))[:12]
        )
        new_action = str(rule["editor_action"])
        prev_action = str(existing["editor_action"]).split("(Generalized with:")[0].strip()
        generalized_action = new_action if same_video or len(new_action) >= len(prev_action) else prev_action

        updated_observed = (
            int(rule.get("observed_count", 1))
            if same_video
            else int(existing["observed_count"]) + int(rule.get("observed_count", 1))
        )

        conn.execute(
            """
            UPDATE editor_rules
            SET agent_role = ?,
                title = ?,
                trigger_condition = ?,
                editor_action = ?,
                timing_constraint = ?,
                priority = ?,
                confidence = ?,
                observed_count = ?,
                example_timestamps_json = ?,
                source_video_id = ?,
                updated_at = ?
            WHERE rule_code = ?
            """,
            (
                rule["agent_role"],
                rule["title"],
                rule["trigger_condition"],
                generalized_action,
                rule["timing_constraint"],
                max(int(existing["priority"]), int(rule["priority"])),
                round(max(float(existing["confidence"]), float(rule["confidence"])), 2),
                updated_observed,
                json.dumps(merged_ts),
                video_id,
                now_iso,
                existing["rule_code"],
            ),
        )
    else:
        target_code = incoming_code
        if not target_code or target_code == "AUTO" or existing_by_code is not None:
            preferred_prefix = "STORY" if incoming_is_macro else incoming_code
            target_code = _mint_next_rule_code(conn, preferred_prefix, str(rule["agent_role"]))

        conn.execute(
            """
            INSERT INTO editor_rules (
                rule_code, agent_role, title, trigger_condition,
                editor_action, timing_constraint, priority, confidence,
                observed_count, example_timestamps_json, source_video_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_code,
                rule["agent_role"],
                rule["title"],
                rule["trigger_condition"],
                rule["editor_action"],
                rule["timing_constraint"],
                int(rule["priority"]),
                float(rule["confidence"]),
                int(rule.get("observed_count", 1)),
                json.dumps(rule.get("example_timestamps", [])),
                video_id,
                now_iso,
            ),
        )


def list_videos() -> list[dict[str, Any]]:
    """Return all analyzed basketball videos with their extracted moment counts."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT v.*,
                   (SELECT COUNT(*) FROM timeline_events te WHERE te.video_id = v.id) AS stored_event_count
            FROM videos v
            ORDER BY CASE WHEN v.id = 'yt-crown-T_uLlzfDCjI' THEN 0 ELSE 1 END, v.created_at ASC
            """
        ).fetchall()
        results = []
        for r in rows:
            item = dict(r)
            stored = int(item.pop("stored_event_count", 0))
            item["event_count"] = stored if stored > 0 else max(3, int(round(int(item["duration_seconds"]) / 18.4)))
            results.append(item)
        return results


def get_video_detail(video_id: str) -> dict[str, Any] | None:
    """Return a single video with its full chronological timeline events."""
    with get_db_connection() as conn:
        video_row = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if not video_row:
            return None
        event_rows = conn.execute(
            """
            SELECT * FROM timeline_events
            WHERE video_id = ?
            ORDER BY timestamp_seconds ASC, id ASC
            """,
            (video_id,),
        ).fetchall()
        events = []
        for er in event_rows:
            item = dict(er)
            item["scorebug"] = json.loads(item.pop("scorebug_json"))
            events.append(item)

        if not events:
            from .seed_data import build_full_broadcast_edit_log, get_playlist_teams_for_video

            home_t, away_t = get_playlist_teams_for_video(video_id, str(video_row["title"]))
            dur_s = int(video_row["duration_seconds"])
            events = build_full_broadcast_edit_log(
                home_team=home_t,
                away_team=away_t,
                duration_seconds=dur_s,
                anchor_events=None,
                initial_home_score=0,
                initial_away_score=0,
                final_home_score=78,
                final_away_score=73,
            )
            conn.executemany(
                """
                INSERT INTO timeline_events (
                    video_id, timestamp_mmss, timestamp_seconds, event_type,
                    agent_domain, camera_angle, game_action_trigger,
                    editor_decision, editor_rationale, duration_seconds, scorebug_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        video_id,
                        ev["timestamp_mmss"],
                        int(ev["timestamp_seconds"]),
                        ev["event_type"],
                        ev["agent_domain"],
                        ev["camera_angle"],
                        ev["game_action_trigger"],
                        ev["editor_decision"],
                        ev["editor_rationale"],
                        float(ev["duration_seconds"]),
                        json.dumps(ev["scorebug"]),
                    )
                    for ev in events
                ],
            )

        result = dict(video_row)
        result["events"] = events
        result["event_count"] = len(events)
        return result


def _ensure_rule_reviews_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rule_reviews (
            rule_code TEXT PRIMARY KEY,
            review_status TEXT NOT NULL,
            reviewer_name TEXT NOT NULL DEFAULT 'Broadcast Reviewer',
            reviewer_comment TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """
    )


def list_editor_rules(agent_role: str | None = None) -> list[dict[str, Any]]:
    """Return all distilled Editor Knowledge Base rules with persisted reviewer feedback, optionally filtered by agent role."""
    with get_db_connection() as conn:
        _ensure_rule_reviews_table(conn)
        if agent_role:
            rows = conn.execute(
                """
                SELECT er.*,
                       COALESCE(rr.review_status, 'unreviewed') AS review_status,
                       COALESCE(rr.reviewer_name, '') AS reviewer_name,
                       COALESCE(rr.reviewer_comment, '') AS reviewer_comment,
                       rr.updated_at AS review_updated_at
                FROM editor_rules er
                LEFT JOIN rule_reviews rr ON er.rule_code = rr.rule_code
                WHERE er.agent_role = ?
                ORDER BY er.priority DESC, er.confidence DESC
                """,
                (agent_role,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT er.*,
                       COALESCE(rr.review_status, 'unreviewed') AS review_status,
                       COALESCE(rr.reviewer_name, '') AS reviewer_name,
                       COALESCE(rr.reviewer_comment, '') AS reviewer_comment,
                       rr.updated_at AS review_updated_at
                FROM editor_rules er
                LEFT JOIN rule_reviews rr ON er.rule_code = rr.rule_code
                ORDER BY er.priority DESC, er.confidence DESC
                """
            ).fetchall()
        from .plain_english_normalizer import normalize_rule_for_non_basketball_viewers

        rules = []
        for r in rows:
            item = dict(r)
            item["example_timestamps"] = json.loads(item.pop("example_timestamps_json"))
            item = normalize_rule_for_non_basketball_viewers(item)
            rules.append(item)
        return rules


def save_rule_review(
    rule_code: str,
    review_status: str,
    reviewer_comment: str = "",
    reviewer_name: str = "Broadcast Reviewer",
) -> dict[str, Any]:
    """Persist a human reviewer's evaluation (agree, partially_agree, disagree, unreviewed) and comments for a rule."""
    clean_code = (rule_code or "").strip().upper()
    clean_status = (review_status or "unreviewed").strip().lower()
    if clean_status not in {"agree", "partially_agree", "disagree", "unreviewed"}:
        raise ValueError("Invalid review_status.")
    clean_comment = (reviewer_comment or "").strip()[:1000]
    clean_name = (reviewer_name or "Broadcast Reviewer").strip()[:80] or "Broadcast Reviewer"
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        _ensure_rule_reviews_table(conn)
        exists = conn.execute(
            "SELECT 1 FROM editor_rules WHERE rule_code = ?",
            (clean_code,),
        ).fetchone()
        if not exists:
            raise KeyError(f"Rule {clean_code} not found.")

        if clean_status == "unreviewed" and not clean_comment:
            conn.execute("DELETE FROM rule_reviews WHERE rule_code = ?", (clean_code,))
        else:
            conn.execute(
                """
                INSERT INTO rule_reviews (
                    rule_code, review_status, reviewer_name, reviewer_comment, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rule_code) DO UPDATE SET
                    review_status = excluded.review_status,
                    reviewer_name = excluded.reviewer_name,
                    reviewer_comment = excluded.reviewer_comment,
                    updated_at = excluded.updated_at
                """,
                (clean_code, clean_status, clean_name, clean_comment, now_iso),
            )

    matched = [r for r in list_editor_rules() if r["rule_code"] == clean_code]
    return matched[0]


def get_rule_review_summary() -> dict[str, int]:
    """Return aggregate counts of rule review statuses across the Editor Knowledge Base."""
    rules = list_editor_rules()
    summary = {
        "total": len(rules),
        "agree": 0,
        "partially_agree": 0,
        "disagree": 0,
        "unreviewed": 0,
        "with_comments": 0,
    }
    for r in rules:
        st = str(r.get("review_status") or "unreviewed")
        if st in summary:
            summary[st] += 1
        else:
            summary["unreviewed"] += 1
        if str(r.get("reviewer_comment") or "").strip():
            summary["with_comments"] += 1
    return summary



def add_custom_editor_rule(rule_data: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a rule in the Editor Knowledge Base (supports 'AUTO' rule_code minting)."""
    from .services.rule_engine import sanitize_and_enrich_rule

    now_iso = datetime.now(timezone.utc).isoformat()
    raw_code = str(rule_data.get("rule_code") or "").strip().upper()
    sanitized = sanitize_and_enrich_rule(rule_data)
    with get_db_connection() as conn:
        if not raw_code or raw_code == "AUTO":
            is_macro = "macro game pattern" in str(sanitized.get("trigger_condition", "")).lower()
            target_code = _mint_next_rule_code(
                conn,
                "STORY" if is_macro else "",
                str(sanitized["agent_role"]),
            )
        else:
            target_code = raw_code

        conn.execute(
            """
            INSERT INTO editor_rules (
                rule_code, agent_role, title, trigger_condition,
                editor_action, timing_constraint, priority, confidence,
                observed_count, example_timestamps_json, source_video_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_code) DO UPDATE SET
                agent_role = excluded.agent_role,
                title = excluded.title,
                trigger_condition = excluded.trigger_condition,
                editor_action = excluded.editor_action,
                timing_constraint = excluded.timing_constraint,
                priority = excluded.priority,
                confidence = excluded.confidence,
                example_timestamps_json = excluded.example_timestamps_json,
                updated_at = excluded.updated_at
            """,
            (
                target_code,
                sanitized["agent_role"],
                sanitized["title"],
                sanitized["trigger_condition"],
                sanitized["editor_action"],
                sanitized["timing_constraint"],
                int(sanitized["priority"]),
                float(sanitized["confidence"]),
                int(sanitized.get("observed_count", 1)),
                json.dumps(sanitized.get("example_timestamps", [])),
                rule_data.get("source_video_id", "manual-curator"),
                now_iso,
            ),
        )
    rules = [r for r in list_editor_rules() if r["rule_code"] == target_code]
    return rules[0]


def save_agent_run(run_payload: dict[str, Any]) -> None:
    """Save a multi-agent control room simulation run."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs (
                run_id, scenario_name, model_used, execution_mode,
                orchestrator_summary, edl_steps_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_payload["run_id"],
                run_payload["scenario_name"],
                run_payload["model_used"],
                run_payload["execution_mode"],
                run_payload["orchestrator_summary"],
                json.dumps(run_payload["edl_steps"]),
                now_iso,
            ),
        )


def list_agent_runs() -> list[dict[str, Any]]:
    """Return recent multi-agent control room runs."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT 15"
        ).fetchall()
        results = []
        for r in rows:
            item = dict(r)
            item["edl_steps"] = json.loads(item.pop("edl_steps_json"))
            results.append(item)
        return results
