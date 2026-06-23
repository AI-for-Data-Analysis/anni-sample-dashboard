#!/usr/bin/env python3
"""Summarize Codex conversation token usage with clearer turn-level accounting.

This script is intentionally standard-library only so it can run from any
checkout without installing packages.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN_COLUMNS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)

TURN_TOKEN_TOTALS = (
    "token_delta",
    "turn_input_tokens",
    "turn_cached_input_tokens",
    "turn_uncached_input_tokens",
    "turn_output_tokens",
    "turn_reasoning_output_tokens",
)

DEFAULT_REPORT_DIR = "usage_reports"

TOKEN_EVENT_EXPLANATION = (
    "Token fields on turn charts are summed across token_count events inside a user turn. "
    "A user turn can contain many model calls when the agent runs tools and then asks the "
    "model to continue. Therefore a large per-turn input total is not the same thing as "
    "unique context size. Use token_events and the average-per-event columns to distinguish "
    "one large model call from many similarly shaped calls. Cached input tokens are included "
    "inside input tokens; uncached input is input minus cached input."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a recent Codex usage summary from ~/.codex with clearer turn-level accounting."
    )
    parser.add_argument(
        "--codex-dir",
        default="~/.codex",
        help="Codex home directory. Default: ~/.codex",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=2,
        help="Number of recent days to include. Ignored when --session-id is used. Default: 2",
    )
    parser.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Only report on this conversation/session id. May be used multiple times.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"Markdown report path. Default: {DEFAULT_REPORT_DIR}/codex_usage_summary.md",
    )
    parser.add_argument(
        "--html",
        default=None,
        help=f"Interactive HTML report path. Default: {DEFAULT_REPORT_DIR}/codex_usage_report.html",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help=f"Per-session CSV path. Default: {DEFAULT_REPORT_DIR}/codex_usage_sessions.csv",
    )
    parser.add_argument(
        "--turn-csv",
        default=None,
        help=f"Per-turn CSV path for inspected top sessions. Default: {DEFAULT_REPORT_DIR}/codex_usage_turns.csv",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top sessions to show. Default: 10",
    )
    parser.add_argument(
        "--cached-input-multiplier",
        type=float,
        default=0.1,
        help=(
            "Multiplier to use when showing cached input as effective input tokens. "
            "Default: 0.1, equivalent to cached input costing one-tenth of uncached input."
        ),
    )
    return parser.parse_args()


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def from_unix(value: float | int | None) -> dt.datetime | None:
    if value is None:
        return None
    try:
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000
        return dt.datetime.fromtimestamp(raw, tz=dt.timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def fmt_int(value: int | float | None) -> str:
    if value is None:
        return ""
    return f"{int(value):,}"


def fmt_dt(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def avg_int(total: int | float | None, count: int | float | None) -> int:
    try:
        denominator = int(count or 0)
        if denominator <= 0:
            return 0
        return round(int(total or 0) / denominator)
    except (TypeError, ValueError):
        return 0


def report_path(value: str | None, default_name: str) -> Path:
    if value:
        return Path(value).resolve()
    report_dir = Path(DEFAULT_REPORT_DIR).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / default_name


def slugify(value: str, fallback: str = "session") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:80] or fallback


def rel_path(path: Path, start: Path) -> str:
    try:
        return str(path.relative_to(start))
    except ValueError:
        return str(path)


def connect_usage_db(codex_dir: Path) -> sqlite3.Connection:
    db_path = codex_dir / "state_5.sqlite"
    if not db_path.exists():
        raise SystemExit(f"Could not find Codex usage database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def find_usage_table(conn: sqlite3.Connection) -> str:
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    for table in tables:
        cols = table_columns(conn, table)
        if {"session_id", "total_tokens"}.issubset(cols):
            return table
    raise SystemExit("Could not find a usage table with session_id and total_tokens.")


def has_thread_usage(conn: sqlite3.Connection) -> bool:
    try:
        cols = table_columns(conn, "threads")
    except sqlite3.OperationalError:
        return False
    return {"id", "tokens_used"}.issubset(cols)


def read_thread_sessions(
    conn: sqlite3.Connection, since: dt.datetime
) -> dict[str, dict[str, Any]]:
    cols = table_columns(conn, "threads")
    wanted = [
        c
        for c in (
            "id",
            "title",
            "source",
            "thread_source",
            "model",
            "model_provider",
            "cwd",
            "created_at",
            "updated_at",
            "created_at_ms",
            "updated_at_ms",
            "tokens_used",
            "rollout_path",
            "first_user_message",
            "preview",
        )
        if c in cols
    ]
    sessions: dict[str, dict[str, Any]] = {}
    for row in conn.execute(f"SELECT {', '.join(wanted)} FROM threads"):
        item = dict(row)
        created = from_unix(item.get("created_at_ms") or item.get("created_at"))
        updated = from_unix(item.get("updated_at_ms") or item.get("updated_at"))
        if updated is not None and updated < since:
            continue

        session_id = str(item["id"])
        total = int(item.get("tokens_used") or 0)
        sessions[session_id] = {
            "session_id": session_id,
            "turns": 0,
            "first_seen": created,
            "last_seen": updated,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": total,
            "title": item.get("title") or item.get("first_user_message") or item.get("preview"),
            "source": item.get("source") or item.get("thread_source"),
            "model": item.get("model") or item.get("model_provider"),
            "cwd": item.get("cwd"),
            "jsonl_path": item.get("rollout_path"),
        }
    return sessions


def find_sessions_table(conn: sqlite3.Connection) -> str | None:
    for name in ("sessions", "conversation_sessions"):
        try:
            cols = table_columns(conn, name)
        except sqlite3.OperationalError:
            continue
        if "id" in cols or "session_id" in cols:
            return name
    return None


def read_usage_rows(
    conn: sqlite3.Connection, usage_table: str, since: dt.datetime
) -> list[dict[str, Any]]:
    cols = table_columns(conn, usage_table)
    created_col = next(
        (c for c in ("created_at", "timestamp", "ts", "time") if c in cols), None
    )

    select_cols = ["session_id"] + [c for c in TOKEN_COLUMNS if c in cols]
    if created_col:
        select_cols.append(created_col)

    rows = []
    for row in conn.execute(f"SELECT {', '.join(select_cols)} FROM {usage_table}"):
        item = dict(row)
        created = from_unix(item.get(created_col)) if created_col else None
        if created is not None and created < since:
            continue
        item["_created"] = created
        rows.append(item)
    return rows


def read_session_metadata(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    table = find_sessions_table(conn)
    if table is None:
        return {}

    cols = table_columns(conn, table)
    id_col = "id" if "id" in cols else "session_id"
    wanted = [
        id_col,
        *[
            c
            for c in (
                "title",
                "source",
                "model",
                "created_at",
                "updated_at",
                "cwd",
                "current_dir",
            )
            if c in cols
        ],
    ]
    meta: dict[str, dict[str, Any]] = {}
    for row in conn.execute(f"SELECT {', '.join(wanted)} FROM {table}"):
        item = dict(row)
        session_id = str(item.pop(id_col))
        meta[session_id] = item
    return meta


def aggregate_usage(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sessions: dict[str, dict[str, Any]] = {}
    for row in rows:
        session_id = str(row["session_id"])
        item = sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "turns": 0,
                "first_seen": None,
                "last_seen": None,
                **{col: 0 for col in TOKEN_COLUMNS},
            },
        )
        item["turns"] += 1
        created = row.get("_created")
        if created is not None:
            if item["first_seen"] is None or created < item["first_seen"]:
                item["first_seen"] = created
            if item["last_seen"] is None or created > item["last_seen"]:
                item["last_seen"] = created
        for col in TOKEN_COLUMNS:
            item[col] += int(row.get(col) or 0)
    return sessions


def session_files(codex_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return files
    for path in sessions_dir.rglob("*.jsonl"):
        files[path.stem] = path
        match = re.search(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            path.stem,
        )
        if match:
            files[match.group(1)] = path
    return files


def inspect_jsonl(path: Path, max_lines: int = 20000) -> dict[str, Any]:
    counts = Counter()
    previews: list[str] = []
    first_text: str | None = None
    last_text: str | None = None

    turn_breakdown = extract_turn_breakdown(path, max_lines=max_lines)

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            if line_number > max_lines:
                counts["truncated"] += 1
                break
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                counts["bad_json"] += 1
                continue

            item_type = str(item.get("type") or item.get("event") or "unknown")
            counts[item_type] += 1

            payload = item.get("payload") if isinstance(item, dict) else None
            payload_type = None
            if isinstance(payload, dict):
                payload_type = payload.get("type")
                if payload_type:
                    counts[str(payload_type)] += 1
                role = payload.get("role")
                if role:
                    counts[f"role:{role}"] += 1

            text = None
            if isinstance(payload, dict) and payload_type in {"user_message", "agent_message"}:
                text = payload.get("message")
            elif isinstance(payload, dict) and payload.get("role") in {"user", "assistant"}:
                text = extract_text(payload.get("content"))
            elif item_type not in {"session_meta", "turn_context"}:
                text = extract_text(item)
            if text:
                text = text.strip()
            if text and is_infrastructure_text(text):
                text = None
            if text:
                if first_text is None:
                    first_text = text
                last_text = text
                if len(previews) < 3:
                    previews.append(text[:180].replace("\n", " "))

            name = extract_tool_name(item)
            if name:
                counts[f"tool:{name}"] += 1

    return {
        "event_counts": dict(counts),
        "first_text": first_text,
        "last_text": last_text,
        "previews": previews,
        "turn_breakdown": turn_breakdown,
    }


def extract_turn_breakdown(path: Path, max_lines: int = 20000) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_total = 0

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            if line_number > max_lines:
                break
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            item_type = item.get("type")
            payload = item.get("payload") if isinstance(item, dict) else None
            if not isinstance(payload, dict):
                continue

            payload_type = payload.get("type")
            if item_type == "event_msg" and payload_type == "user_message":
                if current is not None:
                    current["token_delta"] = current["end_total_tokens"] - current["start_total_tokens"]
                    turns.append(current)
                current = {
                    "turn_index": len(turns) + 1,
                    "message": str(payload.get("message") or "").replace("\n", " ").strip(),
                    "start_total_tokens": last_total,
                    "end_total_tokens": last_total,
                    "token_delta": 0,
                    "token_events": 0,
                    "turn_input_tokens": 0,
                    "turn_cached_input_tokens": 0,
                    "turn_uncached_input_tokens": 0,
                    "turn_output_tokens": 0,
                    "turn_reasoning_output_tokens": 0,
                    "tool_calls": Counter(),
                    "last_input_tokens": 0,
                    "last_cached_input_tokens": 0,
                    "last_output_tokens": 0,
                    "last_reasoning_output_tokens": 0,
                    "actions": [
                        {
                            "kind": "user_message",
                            "summary": str(payload.get("message") or "").strip(),
                        }
                    ],
                }
                continue

            if current is None:
                continue

            if item_type == "response_item" and payload.get("type") == "function_call":
                current["tool_calls"][payload.get("name") or "unknown"] += 1
                current["actions"].append(
                    {
                        "kind": "tool_call",
                        "summary": payload.get("name") or "unknown",
                        "detail": payload.get("arguments") or "",
                    }
                )

            if item_type == "response_item" and payload.get("type") == "function_call_output":
                current["actions"].append(
                    {
                        "kind": "tool_output",
                        "summary": payload.get("call_id") or "function_call_output",
                        "detail": payload.get("output") or "",
                    }
                )

            if item_type == "response_item" and payload.get("type") in {
                "custom_tool_call",
                "custom_tool_call_output",
            }:
                current["actions"].append(
                    {
                        "kind": payload.get("type"),
                        "summary": payload.get("name") or payload.get("call_id") or payload.get("type"),
                        "detail": payload.get("input") or payload.get("output") or "",
                    }
                )

            if item_type == "event_msg" and payload_type == "agent_message":
                current["actions"].append(
                    {
                        "kind": "agent_message",
                        "summary": payload.get("message") or "",
                    }
                )

            if item_type == "event_msg" and payload_type == "token_count":
                info = payload.get("info") or {}
                total_usage = info.get("total_token_usage") or {}
                last_usage = info.get("last_token_usage") or {}
                total_tokens = total_usage.get("total_tokens")
                if total_tokens is None:
                    continue
                last_total = int(total_tokens)
                current["end_total_tokens"] = last_total
                current["token_events"] += 1
                input_tokens = int(last_usage.get("input_tokens") or 0)
                cached_input_tokens = int(last_usage.get("cached_input_tokens") or 0)
                output_tokens = int(last_usage.get("output_tokens") or 0)
                reasoning_output_tokens = int(last_usage.get("reasoning_output_tokens") or 0)
                current["turn_input_tokens"] += input_tokens
                current["turn_cached_input_tokens"] += cached_input_tokens
                current["turn_uncached_input_tokens"] += max(input_tokens - cached_input_tokens, 0)
                current["turn_output_tokens"] += output_tokens
                current["turn_reasoning_output_tokens"] += reasoning_output_tokens
                current["last_input_tokens"] = input_tokens
                current["last_cached_input_tokens"] = cached_input_tokens
                current["last_output_tokens"] = output_tokens
                current["last_reasoning_output_tokens"] = reasoning_output_tokens
                current["actions"].append(
                    {
                        "kind": "token_count",
                        "summary": f"last total {fmt_int(last_usage.get('total_tokens'))}; cumulative {fmt_int(total_usage.get('total_tokens'))}",
                        "detail": json.dumps(
                            {
                                "last_token_usage": last_usage,
                                "total_token_usage": total_usage,
                                "model_context_window": info.get("model_context_window"),
                            },
                            indent=2,
                        ),
                    }
                )

    if current is not None:
        current["token_delta"] = current["end_total_tokens"] - current["start_total_tokens"]
        turns.append(current)

    for turn in turns:
        tool_calls = turn.get("tool_calls")
        if isinstance(tool_calls, Counter):
            turn["tool_call_summary"] = ", ".join(
                f"{name}:{count}" for name, count in tool_calls.most_common()
            )
            turn["tool_call_count"] = sum(tool_calls.values())
        else:
            turn["tool_call_summary"] = ""
            turn["tool_call_count"] = 0
        token_events = int(turn.get("token_events") or 0)
        turn["avg_input_tokens_per_event"] = avg_int(
            turn.get("turn_input_tokens"), token_events
        )
        turn["avg_cached_input_tokens_per_event"] = avg_int(
            turn.get("turn_cached_input_tokens"), token_events
        )
        turn["avg_uncached_input_tokens_per_event"] = avg_int(
            turn.get("turn_uncached_input_tokens"), token_events
        )
        turn["avg_output_tokens_per_event"] = avg_int(
            turn.get("turn_output_tokens"), token_events
        )
    return turns


def extract_text(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, list):
        parts = [extract_text(part) for part in item]
        return "\n".join(part for part in parts if part) or None
    if not isinstance(item, dict):
        return None

    for key in ("text", "content", "message", "input"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (dict, list)):
            nested = extract_text(value)
            if nested:
                return nested

    payload = item.get("payload") or item.get("data")
    if isinstance(payload, (dict, list)):
        return extract_text(payload)
    return None


def is_infrastructure_text(text: str) -> bool:
    prefixes = (
        "<permissions instructions>",
        "<collaboration_mode>",
        "<apps_instructions>",
        "<skills_instructions>",
        "<plugins_instructions>",
        "<environment_context>",
        "# AGENTS.md instructions",
    )
    return text.startswith(prefixes)


def extract_tool_name(item: dict[str, Any]) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in ("name", "tool_name", "callable", "recipient"):
        value = item.get(key)
        if isinstance(value, str) and value:
            if any(word in value.lower() for word in ("exec", "mcp", "tool", "read", "write")):
                return value
    payload = item.get("payload") or item.get("data")
    if isinstance(payload, dict):
        return extract_tool_name(payload)
    return None


def merge_metadata(
    sessions: dict[str, dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
    files: dict[str, Path],
    inspect_top: int,
) -> list[dict[str, Any]]:
    items = list(sessions.values())
    for item in items:
        if item["session_id"] in metadata:
            item.update(metadata[item["session_id"]])
        if item.get("created_at") and item["first_seen"] is None:
            item["first_seen"] = from_unix(item["created_at"])
        if item.get("updated_at") and item["last_seen"] is None:
            item["last_seen"] = from_unix(item["updated_at"])
        path = files.get(item["session_id"])
        if path:
            item["jsonl_path"] = str(path)

    items.sort(key=lambda row: row.get("total_tokens", 0), reverse=True)

    for item in items[:inspect_top]:
        path_text = item.get("jsonl_path")
        if path_text:
            try:
                item["jsonl"] = inspect_jsonl(Path(path_text))
                if not item.get("turns"):
                    counts = item["jsonl"].get("event_counts") or {}
                    item["turns"] = (
                        counts.get("user_message", 0)
                        or counts.get("role:user", 0)
                        or counts.get("message", 0)
                    )
            except OSError as exc:
                item["jsonl_error"] = str(exc)

    return items


def write_csv(path: Path, sessions: list[dict[str, Any]]) -> None:
    fields = [
        "session_id",
        "title",
        "source",
        "turns",
        "first_seen",
        "last_seen",
        *TOKEN_COLUMNS,
        "jsonl_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in sessions:
            row = {field: item.get(field, "") for field in fields}
            row["first_seen"] = fmt_dt(item.get("first_seen"))
            row["last_seen"] = fmt_dt(item.get("last_seen"))
            writer.writerow(row)


def write_turn_csv(
    path: Path,
    sessions: list[dict[str, Any]],
    cached_input_multiplier: float,
) -> None:
    fields = [
        "session_id",
        "session_title",
        "turn_index",
        "token_delta",
        "end_total_tokens",
        "token_events",
        "turn_input_tokens",
        "turn_cached_input_tokens",
        "turn_uncached_input_tokens",
        f"turn_effective_input_tokens_at_{cached_input_multiplier:g}x_cached",
        "turn_output_tokens",
        "turn_reasoning_output_tokens",
        "avg_input_tokens_per_token_event",
        "avg_cached_input_tokens_per_token_event",
        "avg_uncached_input_tokens_per_token_event",
        "avg_output_tokens_per_token_event",
        "tool_call_count",
        "tool_call_summary",
        "last_input_tokens",
        "last_cached_input_tokens",
        "last_output_tokens",
        "last_reasoning_output_tokens",
        "message",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for session in sessions:
            jsonl = session.get("jsonl") or {}
            for turn in jsonl.get("turn_breakdown") or []:
                effective_input = (
                    int(turn.get("turn_uncached_input_tokens") or 0)
                    + int(turn.get("turn_cached_input_tokens") or 0)
                    * cached_input_multiplier
                )
                writer.writerow(
                    {
                        "session_id": session.get("session_id", ""),
                        "session_title": session.get("title", ""),
                        "turn_index": turn.get("turn_index", ""),
                        "token_delta": turn.get("token_delta", ""),
                        "end_total_tokens": turn.get("end_total_tokens", ""),
                        "token_events": turn.get("token_events", ""),
                        "turn_input_tokens": turn.get("turn_input_tokens", ""),
                        "turn_cached_input_tokens": turn.get("turn_cached_input_tokens", ""),
                        "turn_uncached_input_tokens": turn.get("turn_uncached_input_tokens", ""),
                        f"turn_effective_input_tokens_at_{cached_input_multiplier:g}x_cached": round(
                            effective_input
                        ),
                        "turn_output_tokens": turn.get("turn_output_tokens", ""),
                        "turn_reasoning_output_tokens": turn.get("turn_reasoning_output_tokens", ""),
                        "avg_input_tokens_per_token_event": turn.get(
                            "avg_input_tokens_per_event", ""
                        ),
                        "avg_cached_input_tokens_per_token_event": turn.get(
                            "avg_cached_input_tokens_per_event", ""
                        ),
                        "avg_uncached_input_tokens_per_token_event": turn.get(
                            "avg_uncached_input_tokens_per_event", ""
                        ),
                        "avg_output_tokens_per_token_event": turn.get(
                            "avg_output_tokens_per_event", ""
                        ),
                        "tool_call_count": turn.get("tool_call_count", ""),
                        "tool_call_summary": turn.get("tool_call_summary", ""),
                        "last_input_tokens": turn.get("last_input_tokens", ""),
                        "last_cached_input_tokens": turn.get("last_cached_input_tokens", ""),
                        "last_output_tokens": turn.get("last_output_tokens", ""),
                        "last_reasoning_output_tokens": turn.get("last_reasoning_output_tokens", ""),
                        "message": turn.get("message", ""),
                    }
                )


def svg_polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def write_turn_plot(path: Path, session: dict[str, Any]) -> bool:
    turns = ((session.get("jsonl") or {}).get("turn_breakdown") or [])
    turns = [turn for turn in turns if int(turn.get("end_total_tokens") or 0) > 0]
    if not turns:
        return False

    width = 900
    height = 360
    left = 70
    right = 24
    top = 36
    bottom = 56
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_turn = max(int(turn.get("turn_index") or 0) for turn in turns) or 1
    max_total = max(int(turn.get("end_total_tokens") or 0) for turn in turns) or 1
    max_delta = max(int(turn.get("token_delta") or 0) for turn in turns) or 1
    max_cached_input = max(int(turn.get("turn_cached_input_tokens") or 0) for turn in turns) or 1
    max_activity = max(max_delta, max_cached_input)

    def x_for(turn_index: int) -> float:
        if max_turn == 1:
            return left + plot_width / 2
        return left + ((turn_index - 1) / (max_turn - 1)) * plot_width

    def y_total(total: int) -> float:
        return top + plot_height - (total / max_total) * plot_height

    def y_delta(delta: int) -> float:
        return top + plot_height - (delta / max_activity) * (plot_height * 0.55)

    line_points = [
        (x_for(int(turn.get("turn_index") or 0)), y_total(int(turn.get("end_total_tokens") or 0)))
        for turn in turns
    ]
    bar_width = max(3, min(18, plot_width / max_turn * 0.6))
    grouped_bar_width = bar_width * 0.45
    rects = []
    cached_rects = []
    for turn in turns:
        turn_index = int(turn.get("turn_index") or 0)
        delta = int(turn.get("token_delta") or 0)
        cached_input = int(turn.get("turn_cached_input_tokens") or 0)
        x = x_for(turn_index) - grouped_bar_width - 1
        y = y_delta(delta)
        h = top + plot_height - y
        rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{grouped_bar_width:.1f}" height="{h:.1f}" fill="#7aa6c2" opacity="0.55" />'
        )
        cached_x = x_for(turn_index) + 1
        cached_y = y_delta(cached_input)
        cached_h = top + plot_height - cached_y
        cached_rects.append(
            f'<rect x="{cached_x:.1f}" y="{cached_y:.1f}" width="{grouped_bar_width:.1f}" height="{cached_h:.1f}" fill="#805ad5" opacity="0.55" />'
        )

    title = escape_xml(str(session.get("title") or session.get("session_id") or "Session"))
    max_total_label = fmt_int(max_total)
    max_delta_label = fmt_int(max_delta)
    max_cached_input_label = fmt_int(max_cached_input)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Token usage by turn">
  <style>
    text {{ font-family: Arial, sans-serif; fill: #222; }}
    .axis {{ stroke: #555; stroke-width: 1; }}
    .grid {{ stroke: #ddd; stroke-width: 1; }}
  </style>
  <rect width="100%" height="100%" fill="#fff" />
  <text x="{left}" y="20" font-size="14" font-weight="700">{title[:95]}</text>
  <line class="axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" />
  <line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" />
  <line class="grid" x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}" />
  <line class="grid" x1="{left}" y1="{top + plot_height / 2}" x2="{left + plot_width}" y2="{top + plot_height / 2}" />
  <text x="8" y="{top + 4}" font-size="11">{max_total_label} cumulative</text>
  <text x="8" y="{top + plot_height / 2 + 4}" font-size="11">midpoint</text>
  <text x="{left}" y="{height - 18}" font-size="11">Turn 1</text>
  <text x="{left + plot_width - 58}" y="{height - 18}" font-size="11">Turn {max_turn}</text>
  {''.join(rects)}
  {''.join(cached_rects)}
  <polyline points="{svg_polyline(line_points)}" fill="none" stroke="#17324d" stroke-width="2.4" />
  <circle cx="{line_points[-1][0]:.1f}" cy="{line_points[-1][1]:.1f}" r="3.5" fill="#17324d" />
  <rect x="{left}" y="{height - 45}" width="12" height="8" fill="#7aa6c2" opacity="0.45" />
  <text x="{left + 18}" y="{height - 38}" font-size="11">per-turn token delta, max {max_delta_label}</text>
  <rect x="{left + 250}" y="{height - 45}" width="12" height="8" fill="#805ad5" opacity="0.55" />
  <text x="{left + 268}" y="{height - 38}" font-size="11">cached input, max {max_cached_input_label}</text>
  <line x1="{left + 650}" y1="{height - 41}" x2="{left + 678}" y2="{height - 41}" stroke="#17324d" stroke-width="2.4" />
  <text x="{left + 685}" y="{height - 38}" font-size="11">cumulative total</text>
</svg>
'''
    path.write_text(svg, encoding="utf-8")
    return True


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_turn_plots(report_dir: Path, sessions: list[dict[str, Any]], top: int) -> dict[str, Path]:
    plot_dir = report_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for rank, session in enumerate(sessions[:top], start=1):
        title = str(session.get("title") or session.get("session_id") or "session")
        filename = f"{rank:02d}-{slugify(title)}.svg"
        path = plot_dir / filename
        if write_turn_plot(path, session):
            paths[str(session["session_id"])] = path
    return paths


def jsonl_token_totals_for_session(session: dict[str, Any]) -> dict[str, int]:
    totals = {key: 0 for key in TURN_TOKEN_TOTALS}
    turns = ((session.get("jsonl") or {}).get("turn_breakdown") or [])
    for turn in turns:
        for key in TURN_TOKEN_TOTALS:
            totals[key] += int(turn.get(key) or 0)
    return totals


def jsonl_token_totals(sessions: list[dict[str, Any]]) -> dict[str, int]:
    totals = {key: 0 for key in TURN_TOKEN_TOTALS}
    for session in sessions:
        session_totals = jsonl_token_totals_for_session(session)
        for key in TURN_TOKEN_TOTALS:
            totals[key] += session_totals[key]
    return totals


def has_jsonl_breakdown(totals: dict[str, int]) -> bool:
    return any(totals[key] for key in TURN_TOKEN_TOTALS if key != "token_delta")


def token_metric_rows(
    db_totals: dict[str, int],
    logged_totals: dict[str, int],
    cached_input_multiplier: float,
) -> tuple[list[tuple[str, str]], str | None]:
    db_breakdown_available = any(db_totals[col] for col in TOKEN_COLUMNS[:-1])
    if db_breakdown_available:
        return [(col, fmt_int(db_totals[col])) for col in TOKEN_COLUMNS], None

    if has_jsonl_breakdown(logged_totals):
        effective_input = (
            logged_totals["turn_uncached_input_tokens"]
            + logged_totals["turn_cached_input_tokens"] * cached_input_multiplier
        )
        rows = [
            ("total_tokens", fmt_int(db_totals["total_tokens"] or logged_totals["token_delta"])),
            ("input_tokens_logged", fmt_int(logged_totals["turn_input_tokens"])),
            ("cached_input_tokens_logged", fmt_int(logged_totals["turn_cached_input_tokens"])),
            ("uncached_input_tokens_logged", fmt_int(logged_totals["turn_uncached_input_tokens"])),
            (
                f"effective_input_tokens_at_{cached_input_multiplier:g}x_cached",
                fmt_int(round(effective_input)),
            ),
            ("output_tokens_logged", fmt_int(logged_totals["turn_output_tokens"])),
            (
                "reasoning_output_tokens_logged",
                fmt_int(logged_totals["turn_reasoning_output_tokens"]),
            ),
        ]
        note = (
            "The Codex database has only total tokens for these conversations, "
            "so input/output rows are summed from token-count events in the JSONL logs. "
            f"{TOKEN_EVENT_EXPLANATION} "
            f"The effective input row counts cached input at {cached_input_multiplier:g}x."
        )
        return rows, note

    rows = [
        (col, "n/a" if col != "total_tokens" else fmt_int(db_totals[col]))
        for col in TOKEN_COLUMNS
    ]
    note = (
        "This Codex database records total tokens per session, but this report did not "
        "find JSONL token-count events with input/output breakdowns for the included conversations."
    )
    return rows, note


def write_report(
    path: Path,
    sessions: list[dict[str, Any]],
    codex_dir: Path,
    since: dt.datetime,
    csv_path: Path,
    turn_csv_path: Path,
    plot_paths: dict[str, Path],
    top: int,
    cached_input_multiplier: float,
) -> None:
    totals = {col: sum(int(item.get(col) or 0) for item in sessions) for col in TOKEN_COLUMNS}
    metric_rows, metric_note = token_metric_rows(
        totals,
        jsonl_token_totals(sessions),
        cached_input_multiplier,
    )

    lines = [
        "# Codex Usage Summary",
        "",
        f"- Codex directory: `{codex_dir}`",
        f"- Window starts: `{fmt_dt(since)}`",
        f"- Sessions included: `{len(sessions)}`",
        f"- CSV detail: `{csv_path}`",
        f"- Turn-level CSV for top sessions: `{turn_csv_path}`",
        "",
        "## Token Totals",
        "",
        "| Metric | Tokens |",
        "|---|---:|",
    ]
    for col, value in metric_rows:
        lines.append(f"| {col} | {value} |")
    if metric_note:
        lines.extend(
            [
                "",
                metric_note,
            ]
        )

    lines.extend(
        [
            "",
            "## Top Sessions",
            "",
            "| Rank | Tokens | Turns | Started | Title |",
            "|---:|---:|---:|---|---|",
        ]
    )
    for rank, item in enumerate(sessions[:top], start=1):
        title = str(item.get("title") or item.get("session_id") or "").replace("|", "\\|")
        lines.append(
            f"| {rank} | {fmt_int(item.get('total_tokens'))} | {item.get('turns', '')} | "
            f"{fmt_dt(item.get('first_seen'))} | {title[:90]} |"
        )

    lines.extend(
        [
            "",
            "## What To Look For",
            "",
            "- Large sessions usually reflect accumulated conversation history, tool outputs, file contents, generated artifacts, or repeated inspection.",
            "- A short prompt can still be expensive when it is sent near the end of a long session.",
            "- Cumulative token plots show how much the session has spent so far; they do not show how much context was sent on a specific turn.",
            "- Turn-level input-token fields are a closer proxy for how much context was sent to the model during that turn, when Codex logs expose those fields.",
            "",
            "## Inspecting The Biggest Sessions",
            "",
        ]
    )

    for item in sessions[:top]:
        lines.append(f"### {fmt_int(item.get('total_tokens'))} tokens: {item.get('title') or item['session_id']}")
        lines.append("")
        lines.append(f"- Session id: `{item['session_id']}`")
        lines.append(f"- Turns: `{item.get('turns', '')}`")
        session_token_totals = jsonl_token_totals_for_session(item)
        if has_jsonl_breakdown(session_token_totals):
            effective_input = (
                session_token_totals["turn_uncached_input_tokens"]
                + session_token_totals["turn_cached_input_tokens"] * cached_input_multiplier
            )
            lines.extend(
                [
                    "- Logged token split:",
                    f"  - input tokens: `{fmt_int(session_token_totals['turn_input_tokens'])}`",
                    f"  - cached input tokens: `{fmt_int(session_token_totals['turn_cached_input_tokens'])}`",
                    f"  - uncached input tokens: `{fmt_int(session_token_totals['turn_uncached_input_tokens'])}`",
                    f"  - effective input tokens at `{cached_input_multiplier:g}x` cached: `{fmt_int(round(effective_input))}`",
                    f"  - output tokens: `{fmt_int(session_token_totals['turn_output_tokens'])}`",
                    f"  - reasoning output tokens: `{fmt_int(session_token_totals['turn_reasoning_output_tokens'])}`",
                ]
            )
        if item.get("jsonl_path"):
            lines.append(f"- JSONL: `{item['jsonl_path']}`")
        plot_path = plot_paths.get(str(item["session_id"]))
        if plot_path:
            plot_rel = rel_path(plot_path, path.parent)
            lines.append(f"- Turn plot: [{plot_path.name}]({plot_rel})")
            lines.extend(["", f"![Token usage by turn for this session]({plot_rel})"])
        jsonl = item.get("jsonl") or {}
        event_counts = jsonl.get("event_counts") or {}
        tool_counts = {
            key.removeprefix("tool:"): value
            for key, value in event_counts.items()
            if key.startswith("tool:")
        }
        if tool_counts:
            common = ", ".join(
                f"{name} ({count})" for name, count in Counter(tool_counts).most_common(5)
            )
            lines.append(f"- Common tools/events: {common}")
        previews = jsonl.get("previews") or []
        if previews:
            lines.append("- Text preview:")
            for preview in previews:
                lines.append(f"  - {preview}")

        turns = jsonl.get("turn_breakdown") or []
        turns_with_tokens = [turn for turn in turns if int(turn.get("token_delta") or 0) > 0]
        if turns_with_tokens:
            lines.extend(
                [
                    "",
                    "- Largest token jumps inside this session:",
                    "",
                    "  | Turn | Tokens | Tool calls | Prompt preview |",
                    "  |---:|---:|---:|---|",
                ]
            )
            for turn in sorted(
                turns_with_tokens,
                key=lambda row: int(row.get("token_delta") or 0),
                reverse=True,
            )[:8]:
                message = str(turn.get("message") or "").replace("|", "\\|")
                lines.append(
                    "  | "
                    f"{turn.get('turn_index', '')} | "
                    f"{fmt_int(turn.get('token_delta'))} | "
                    f"{turn.get('tool_call_count', '')} | "
                    f"{message[:95]} |"
                )
            lines.extend(
                [
                    "",
                    "  The turn-level CSV has the full prompt text, cumulative token totals, input-token fields when available, token-event counts, and tool-call summaries.",
                ]
            )
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html_report(
    path: Path,
    sessions: list[dict[str, Any]],
    codex_dir: Path,
    since: dt.datetime,
    csv_path: Path,
    turn_csv_path: Path,
    turn_page_paths: dict[tuple[str, int], Path],
    top: int,
    cached_input_multiplier: float,
) -> None:
    totals = {col: sum(int(item.get(col) or 0) for item in sessions) for col in TOKEN_COLUMNS}
    metric_data, metric_note = token_metric_rows(
        totals,
        jsonl_token_totals(sessions),
        cached_input_multiplier,
    )

    session_rows = []
    chart_specs = []
    for rank, item in enumerate(sessions[:top], start=1):
        title = str(item.get("title") or item.get("session_id") or "")
        session_rows.append(
            "<tr>"
            f"<td>{rank}</td>"
            f"<td>{fmt_int(item.get('total_tokens'))}</td>"
            f"<td>{item.get('turns', '')}</td>"
            f"<td>{escape_html(fmt_dt(item.get('first_seen')))}</td>"
            f"<td>{escape_html(title[:140])}</td>"
            "</tr>"
        )

        turns = ((item.get("jsonl") or {}).get("turn_breakdown") or [])
        turns = [turn for turn in turns if int(turn.get("end_total_tokens") or 0) > 0]
        if not turns:
            continue
        session_id = str(item.get("session_id") or "")
        chart_specs.append(
            {
                "rank": rank,
                "div_id": f"chart-{rank}",
                "title": title,
                "session_id": session_id,
                "turns": [
                    {
                        "turn": int(turn.get("turn_index") or 0),
                        "delta": int(turn.get("token_delta") or 0),
                        "cumulative": int(turn.get("end_total_tokens") or 0),
                        "input": int(turn.get("turn_input_tokens") or 0),
                        "cached_input": int(turn.get("turn_cached_input_tokens") or 0),
                        "uncached_input": int(turn.get("turn_uncached_input_tokens") or 0),
                        "token_events": int(turn.get("token_events") or 0),
                        "avg_input": int(turn.get("avg_input_tokens_per_event") or 0),
                        "avg_cached_input": int(
                            turn.get("avg_cached_input_tokens_per_event") or 0
                        ),
                        "avg_uncached_input": int(
                            turn.get("avg_uncached_input_tokens_per_event") or 0
                        ),
                        "effective_input": round(
                            int(turn.get("turn_uncached_input_tokens") or 0)
                            + int(turn.get("turn_cached_input_tokens") or 0)
                            * cached_input_multiplier
                        ),
                        "tool_calls": int(turn.get("tool_call_count") or 0),
                        "tools": str(turn.get("tool_call_summary") or ""),
                        "prompt": str(turn.get("message") or ""),
                        "page": rel_path(
                            turn_page_paths.get((session_id, int(turn.get("turn_index") or 0)), Path()),
                            path.parent,
                        )
                        if (session_id, int(turn.get("turn_index") or 0)) in turn_page_paths
                        else "",
                    }
                    for turn in turns
                ],
            }
        )

    metric_rows = []
    for col, value in metric_data:
        metric_rows.append(f"<tr><td>{escape_html(col)}</td><td>{value}</td></tr>")

    data_json = json.dumps(chart_specs)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Usage Report</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
      margin: 2rem;
      color: #1f2933;
      background: #ffffff;
    }}
    h1, h2, h3 {{ color: #102a43; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 1rem 0 2rem;
      font-size: 0.95rem;
    }}
    th, td {{
      border: 1px solid #d9e2ec;
      padding: 0.45rem 0.55rem;
      vertical-align: top;
    }}
    th {{ background: #f0f4f8; text-align: left; }}
    .note {{
      background: #f0f4f8;
      border-left: 4px solid #486581;
      padding: 0.75rem 1rem;
      margin: 1rem 0;
    }}
    .chart {{
      width: 100%;
      height: 480px;
      margin: 1rem 0 2.5rem;
    }}
    .meta {{ color: #52606d; font-size: 0.95rem; }}
    code {{ background: #f0f4f8; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Codex Usage Report</h1>
  <p class="meta">Codex directory: <code>{escape_html(str(codex_dir))}</code></p>
  <p class="meta">Window starts: <code>{escape_html(fmt_dt(since))}</code></p>
  <p class="meta">Sessions included: <code>{len(sessions)}</code></p>
  <p class="meta">Session CSV: <code>{escape_html(rel_path(csv_path, path.parent))}</code></p>
  <p class="meta">Turn CSV: <code>{escape_html(rel_path(turn_csv_path, path.parent))}</code></p>

  <h2>Token Totals</h2>
  <table>
    <thead><tr><th>Metric</th><th>Tokens</th></tr></thead>
    <tbody>{''.join(metric_rows)}</tbody>
  </table>
  {f'<p class="note">{escape_html(metric_note)}</p>' if metric_note else ''}

  <h2>Top Sessions</h2>
  <table>
    <thead><tr><th>Rank</th><th>Tokens</th><th>Turns</th><th>Started</th><th>Title</th></tr></thead>
    <tbody>{''.join(session_rows)}</tbody>
  </table>

  <div class="note">
    <p><strong>How to read the charts:</strong> blue bars show summed token use added by each user turn. Purple bars show summed cached input tokens for that turn. Cached input is included in input tokens and is counted at <code>{cached_input_multiplier:g}x</code> in effective-input rows. The dark line shows cumulative session tokens: total usage so far, not the amount sent on that turn.</p>
    <p>{escape_html(TOKEN_EVENT_EXPLANATION)}</p>
    <p>Long conversations often grow because later turns may carry more conversation history, file contents, tool outputs, and prior decisions. The chart is not expected to be smooth: compaction, caching, tool outputs, and multi-step tool loops can create dips or sudden jumps in per-turn cost. Hover text includes token-event counts and average input per event to distinguish repeated tool-loop calls from a single large model call.</p>
    <p>Click-through turn pages show logged actions in order. They do not assign token usage to individual actions.</p>
  </div>

  <h2>Interactive Turn Charts</h2>
  <div id="charts"></div>

  <script>
    const chartSpecs = {data_json};
    const container = document.getElementById("charts");

    function shortText(text, limit) {{
      if (!text) return "";
      return text.length > limit ? text.slice(0, limit - 1) + "…" : text;
    }}

    for (const spec of chartSpecs) {{
      const section = document.createElement("section");
      const title = document.createElement("h3");
      title.textContent = `${{spec.rank}}. ${{spec.title}}`;
      const meta = document.createElement("p");
      meta.className = "meta";
      meta.textContent = spec.session_id;
      const chart = document.createElement("div");
      chart.id = spec.div_id;
      chart.className = "chart";
      section.appendChild(title);
      section.appendChild(meta);
      section.appendChild(chart);
      container.appendChild(section);

      const turns = spec.turns.map(row => row.turn);
      const deltas = spec.turns.map(row => row.delta);
      const cumulative = spec.turns.map(row => row.cumulative);
      const inputs = spec.turns.map(row => row.input || 0);
      const cachedInputs = spec.turns.map(row => row.cached_input || 0);
      const uncachedInputs = spec.turns.map(row => row.uncached_input || 0);
      const tokenEvents = spec.turns.map(row => row.token_events || 0);
      const avgInputs = spec.turns.map(row => row.avg_input || 0);
      const avgCachedInputs = spec.turns.map(row => row.avg_cached_input || 0);
      const avgUncachedInputs = spec.turns.map(row => row.avg_uncached_input || 0);
      const effectiveInputs = spec.turns.map(row => row.effective_input || 0);
      const prompts = spec.turns.map(row => shortText(row.prompt, 120));
      const toolCalls = spec.turns.map(row => row.tool_calls);
      const tools = spec.turns.map(row => row.tools || "none");
      const pages = spec.turns.map(row => row.page || "");
      const barTrace = {{
        type: "bar",
        name: "Per-turn token delta",
        x: turns,
        y: deltas,
        marker: {{ color: "rgba(69, 123, 157, 0.55)" }},
        customdata: prompts.map((prompt, i) => [prompt, toolCalls[i], tools[i], pages[i], inputs[i], cachedInputs[i], uncachedInputs[i], effectiveInputs[i], tokenEvents[i], avgInputs[i], avgCachedInputs[i], avgUncachedInputs[i]]),
        hovertemplate:
          "<b>Turn %{{x}}</b><br>" +
          "Added tokens: %{{y:,}}<br>" +
          "Token events in turn: %{{customdata[8]:,}}<br>" +
          "Summed input tokens: %{{customdata[4]:,}}<br>" +
          "Summed cached input: %{{customdata[5]:,}}<br>" +
          "Summed uncached input: %{{customdata[6]:,}}<br>" +
          "Avg input per token event: %{{customdata[9]:,}}<br>" +
          "Avg cached per token event: %{{customdata[10]:,}}<br>" +
          "Avg uncached per token event: %{{customdata[11]:,}}<br>" +
          "Effective input tokens: %{{customdata[7]:,}}<br>" +
          "Tool calls: %{{customdata[1]}}<br>" +
          "<br><b>Prompt preview</b><br>%{{customdata[0]}}<extra></extra>"
      }};

      const cachedInputTrace = {{
        type: "bar",
        name: "Cached input tokens in turn",
        x: turns,
        y: cachedInputs,
        marker: {{ color: "rgba(128, 90, 213, 0.55)" }},
        customdata: prompts.map((prompt, i) => [prompt, inputs[i], uncachedInputs[i], deltas[i], pages[i], effectiveInputs[i], tokenEvents[i], avgInputs[i], avgCachedInputs[i], avgUncachedInputs[i]]),
        hovertemplate:
          "<b>Turn %{{x}}</b><br>" +
          "Summed cached input tokens: %{{y:,}}<br>" +
          "Token events in turn: %{{customdata[6]:,}}<br>" +
          "Summed total input tokens: %{{customdata[1]:,}}<br>" +
          "Summed uncached input tokens: %{{customdata[2]:,}}<br>" +
          "Avg input per token event: %{{customdata[7]:,}}<br>" +
          "Avg cached per token event: %{{customdata[8]:,}}<br>" +
          "Avg uncached per token event: %{{customdata[9]:,}}<br>" +
          "Effective input tokens: %{{customdata[5]:,}}<br>" +
          "Added tokens: %{{customdata[3]:,}}<br>" +
          "<br><b>Prompt preview</b><br>%{{customdata[0]}}<extra></extra>"
      }};

      const lineTrace = {{
        type: "scatter",
        mode: "lines+markers",
        name: "Cumulative total tokens",
        x: turns,
        y: cumulative,
        yaxis: "y2",
        line: {{ color: "#102a43", width: 3 }},
        marker: {{ color: "#102a43", size: 6 }},
        customdata: prompts.map((prompt, i) => [prompt, toolCalls[i], tools[i], deltas[i], pages[i]]),
        hovertemplate:
          "<b>Turn %{{x}}</b><br>" +
          "Cumulative tokens: %{{y:,}}<br>" +
          "Added this turn: %{{customdata[3]:,}}<br>" +
          "Tool calls: %{{customdata[1]}}<br>" +
          "<br><b>Prompt preview</b><br>%{{customdata[0]}}<extra></extra>"
      }};

      const layout = {{
        margin: {{ l: 70, r: 80, t: 48, b: 55 }},
        barmode: "group",
        hovermode: "closest",
        hoverlabel: {{
          align: "left",
          namelength: 24
        }},
        xaxis: {{ title: "Turn" }},
        yaxis: {{ title: "Turn token counts", rangemode: "tozero" }},
        yaxis2: {{
          title: "Cumulative total tokens",
          overlaying: "y",
          side: "right",
          rangemode: "tozero",
          showgrid: false
        }},
        legend: {{ orientation: "h", y: 1.12 }},
      }};

      Plotly.newPlot(chart.id, [barTrace, cachedInputTrace, lineTrace], layout, {{ responsive: true }});
      chart.on("plotly_click", function(event) {{
        if (!event.points || !event.points.length) return;
        const point = event.points[0];
        const page = pages[point.pointIndex] || "";
        if (page) window.open(page, "_blank");
      }});
    }}
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def escape_html(value: str) -> str:
    return escape_xml(value).replace("'", "&#39;")


def truncate_text(value: Any, limit: int = 6000) -> tuple[str, bool]:
    text = str(value or "")
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n\n[truncated]", True


def write_turn_pages(report_dir: Path, sessions: list[dict[str, Any]], top: int) -> dict[tuple[str, int], Path]:
    page_dir = report_dir / "turn_pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    page_paths: dict[tuple[str, int], Path] = {}
    for rank, session in enumerate(sessions[:top], start=1):
        session_id = str(session.get("session_id") or "")
        title = str(session.get("title") or session_id)
        turns = ((session.get("jsonl") or {}).get("turn_breakdown") or [])
        for turn in turns:
            turn_index = int(turn.get("turn_index") or 0)
            if not turn_index:
                continue
            filename = f"{rank:02d}-turn-{turn_index:03d}-{slugify(title)}.html"
            path = page_dir / filename
            write_turn_page(path, session, turn)
            page_paths[(session_id, turn_index)] = path
    return page_paths


def write_turn_page(path: Path, session: dict[str, Any], turn: dict[str, Any]) -> None:
    title = str(session.get("title") or session.get("session_id") or "Session")
    actions = turn.get("actions") or []
    action_blocks = []
    for index, action in enumerate(actions, start=1):
        summary, summary_truncated = truncate_text(action.get("summary"), 1200)
        detail, detail_truncated = truncate_text(action.get("detail"), 8000)
        action_blocks.append(
            "<section class=\"action\">"
            f"<h3>{index}. {escape_html(str(action.get('kind') or 'event'))}</h3>"
            f"<pre>{escape_html(summary)}</pre>"
            f"{'<p class=\"meta\">Summary truncated.</p>' if summary_truncated else ''}"
            f"{f'<details><summary>Details</summary><pre>{escape_html(detail)}</pre></details>' if detail else ''}"
            f"{'<p class=\"meta\">Details truncated.</p>' if detail_truncated else ''}"
            "</section>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Turn {turn.get('turn_index')} - Codex Usage</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
      margin: 2rem;
      color: #1f2933;
    }}
    h1, h2, h3 {{ color: #102a43; }}
    table {{ border-collapse: collapse; margin: 1rem 0 2rem; width: 100%; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 0.45rem 0.55rem; text-align: left; }}
    th {{ background: #f0f4f8; }}
    pre {{
      white-space: pre-wrap;
      overflow-x: auto;
      background: #f8fafc;
      border: 1px solid #d9e2ec;
      padding: 0.75rem;
    }}
    .meta {{ color: #52606d; font-size: 0.95rem; }}
    .action {{ border-top: 1px solid #d9e2ec; padding-top: 1rem; margin-top: 1rem; }}
  </style>
</head>
<body>
  <p><a href="../codex_usage_report.html">&larr; Back to usage report</a></p>
  <h1>Turn {turn.get('turn_index')} Actions</h1>
  <p class="meta">{escape_html(title)}</p>
  <table>
    <tbody>
      <tr><th>Session id</th><td>{escape_html(str(session.get('session_id') or ''))}</td></tr>
      <tr><th>Token delta</th><td>{fmt_int(turn.get('token_delta'))}</td></tr>
      <tr><th>Cumulative tokens after turn</th><td>{fmt_int(turn.get('end_total_tokens'))}</td></tr>
      <tr><th>Input tokens logged in turn</th><td>{fmt_int(turn.get('turn_input_tokens'))}</td></tr>
      <tr><th>Cached input tokens logged in turn</th><td>{fmt_int(turn.get('turn_cached_input_tokens'))}</td></tr>
      <tr><th>Uncached input tokens logged in turn</th><td>{fmt_int(turn.get('turn_uncached_input_tokens'))}</td></tr>
      <tr><th>Output tokens logged in turn</th><td>{fmt_int(turn.get('turn_output_tokens'))}</td></tr>
      <tr><th>Reasoning output tokens logged in turn</th><td>{fmt_int(turn.get('turn_reasoning_output_tokens'))}</td></tr>
      <tr><th>Token events</th><td>{turn.get('token_events', '')}</td></tr>
      <tr><th>Average input tokens per token event</th><td>{fmt_int(turn.get('avg_input_tokens_per_event'))}</td></tr>
      <tr><th>Average cached input per token event</th><td>{fmt_int(turn.get('avg_cached_input_tokens_per_event'))}</td></tr>
      <tr><th>Average uncached input per token event</th><td>{fmt_int(turn.get('avg_uncached_input_tokens_per_event'))}</td></tr>
      <tr><th>Tool calls</th><td>{turn.get('tool_call_count', '')}</td></tr>
      <tr><th>Tool summary</th><td>{escape_html(str(turn.get('tool_call_summary') or ''))}</td></tr>
    </tbody>
  </table>
  <p class="meta">{escape_html(TOKEN_EVENT_EXPLANATION)}</p>
  <h2>User Prompt</h2>
  <pre>{escape_html(str(turn.get('message') or ''))}</pre>
  <h2>Logged Actions In This Turn</h2>
  <p class="meta">Actions are shown in log order. Token events are shown exactly as recorded nearby in the log; this page does not try to attribute those tokens to individual actions.</p>
  {''.join(action_blocks)}
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    codex_dir = Path(os.path.expanduser(args.codex_dir)).resolve()
    session_ids = {str(value) for value in args.session_id}
    since = (
        dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
        if session_ids
        else now_utc() - dt.timedelta(days=args.days)
    )

    conn = connect_usage_db(codex_dir)
    if has_thread_usage(conn):
        sessions = read_thread_sessions(conn, since)
        metadata = {}
    else:
        usage_table = find_usage_table(conn)
        usage_rows = read_usage_rows(conn, usage_table, since)
        sessions = aggregate_usage(usage_rows)
        metadata = read_session_metadata(conn)
    if session_ids:
        sessions = {
            session_id: session
            for session_id, session in sessions.items()
            if str(session_id) in session_ids
        }
        missing = sorted(session_ids - {str(session_id) for session_id in sessions})
        if missing:
            raise SystemExit(f"Could not find requested session id(s): {', '.join(missing)}")
    files = session_files(codex_dir)
    merged = merge_metadata(sessions, metadata, files, inspect_top=max(args.top, 20))

    out_path = report_path(args.out, "codex_usage_summary.md")
    html_path = report_path(args.html, "codex_usage_report.html")
    csv_path = report_path(args.csv, "codex_usage_sessions.csv")
    turn_csv_path = report_path(args.turn_csv, "codex_usage_turns.csv")
    for output_path in (out_path, html_path, csv_path, turn_csv_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
    report_dir = out_path.parent
    write_csv(csv_path, merged)
    write_turn_csv(
        turn_csv_path,
        merged[: max(args.top, 20)],
        args.cached_input_multiplier,
    )
    plot_paths = write_turn_plots(report_dir, merged, args.top)
    turn_page_paths = write_turn_pages(report_dir, merged, args.top)
    write_report(
        out_path,
        merged,
        codex_dir,
        since,
        csv_path,
        turn_csv_path,
        plot_paths,
        args.top,
        args.cached_input_multiplier,
    )
    write_html_report(
        html_path,
        merged,
        codex_dir,
        since,
        csv_path,
        turn_csv_path,
        turn_page_paths,
        args.top,
        args.cached_input_multiplier,
    )

    total = sum(int(item.get("total_tokens") or 0) for item in merged)
    print(f"Wrote {out_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {turn_csv_path}")
    if plot_paths:
        print(f"Wrote {len(plot_paths)} SVG plot(s) in {report_dir / 'plots'}")
    if turn_page_paths:
        print(f"Wrote {len(turn_page_paths)} turn detail page(s) in {report_dir / 'turn_pages'}")
    print(f"Included {len(merged)} sessions and {fmt_int(total)} total tokens.")


if __name__ == "__main__":
    main()
