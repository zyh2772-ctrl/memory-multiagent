#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path


CONTAINER = "codex-openmemory-mcp"
DB_PATH = "/usr/src/openmemory/openmemory.db"


def run_in_container(script: str) -> str:
    cmd = [
        "docker",
        "exec",
        CONTAINER,
        "python",
        "-c",
        script,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "docker exec failed")
    return result.stdout.strip()


def add_memory(user_name: str, app_name: str, content: str, metadata: dict) -> dict:
    payload = json.dumps(
        {
            "memory_id": uuid.uuid4().hex,
            "metadata": metadata,
            "content": content,
            "user_name": user_name,
            "app_name": app_name,
        }
    )
    script = textwrap.dedent(
        f"""
        import sqlite3, json, datetime

        data = json.loads({payload!r})
        conn = sqlite3.connect({DB_PATH!r})
        cur = conn.cursor()

        user = cur.execute(
            "SELECT id, user_id FROM users WHERE user_id = ?",
            (data["user_name"],),
        ).fetchone()
        if not user:
            raise SystemExit("user_not_found")

        app = cur.execute(
            "SELECT id, name FROM apps WHERE owner_id = ? AND name = ?",
            (user[0], data["app_name"]),
        ).fetchone()
        if not app:
            raise SystemExit("app_not_found")

        now = datetime.datetime.utcnow().isoformat(sep=" ")
        cur.execute(
            '''
            INSERT INTO memories
            (id, user_id, app_id, content, vector, metadata, state, created_at, updated_at, archived_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                data["memory_id"],
                user[0],
                app[0],
                data["content"],
                None,
                json.dumps(data["metadata"], ensure_ascii=False),
                "active",
                now,
                now,
                None,
                None,
            ),
        )
        conn.commit()
        print(json.dumps({{"id": data["memory_id"], "user_id": user[1], "app_name": app[1], "content": data["content"], "state": "active"}}, ensure_ascii=False))
        conn.close()
        """
    )
    return json.loads(run_in_container(script))


def list_memories(user_name: str) -> list[dict]:
    payload = json.dumps({"user_name": user_name})
    script = textwrap.dedent(
        f"""
        import sqlite3, json

        data = json.loads({payload!r})
        conn = sqlite3.connect({DB_PATH!r})
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        rows = cur.execute(
            '''
            SELECT m.id, u.user_id AS user_name, a.name AS app_name, m.content, m.metadata, m.state, m.created_at, m.updated_at
            FROM memories m
            JOIN users u ON m.user_id = u.id
            JOIN apps a ON m.app_id = a.id
            WHERE u.user_id = ?
            ORDER BY m.created_at DESC
            LIMIT 50
            ''',
            (data["user_name"],),
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else {{}}
            items.append(item)
        print(json.dumps(items, ensure_ascii=False))
        conn.close()
        """
    )
    return json.loads(run_in_container(script))


def update_memory(
    memory_id: str,
    content: str | None,
    state: str | None,
    metadata: dict | None,
) -> dict:
    payload = json.dumps(
        {
            "memory_id": memory_id,
            "content": content,
            "state": state,
            "metadata": metadata,
        }
    )
    script = textwrap.dedent(
        f"""
        import sqlite3, json, datetime

        data = json.loads({payload!r})
        conn = sqlite3.connect({DB_PATH!r})
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        row = cur.execute("SELECT id, content, metadata, state FROM memories WHERE id = ?", (data["memory_id"],)).fetchone()
        if not row:
            raise SystemExit("memory_not_found")

        new_content = data["content"] if data["content"] is not None else row["content"]
        new_metadata = data["metadata"] if data["metadata"] is not None else (json.loads(row["metadata"]) if row["metadata"] else {{}})
        new_state = data["state"] if data["state"] is not None else row["state"]
        now = datetime.datetime.utcnow().isoformat(sep=" ")
        archived_at = now if new_state == "archived" else None
        deleted_at = now if new_state == "deleted" else None

        cur.execute(
            '''
            UPDATE memories
            SET content = ?, metadata = ?, state = ?, updated_at = ?, archived_at = ?, deleted_at = ?
            WHERE id = ?
            ''',
            (new_content, json.dumps(new_metadata, ensure_ascii=False), new_state, now, archived_at, deleted_at, data["memory_id"]),
        )
        conn.commit()

        updated = cur.execute(
            "SELECT id, content, metadata, state, updated_at FROM memories WHERE id = ?",
            (data["memory_id"],),
        ).fetchone()
        item = dict(updated)
        item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else {{}}
        print(json.dumps(item, ensure_ascii=False))
        conn.close()
        """
    )
    return json.loads(run_in_container(script))


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenMemory SQLite compatibility helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--user", required=True)
    add_parser.add_argument("--app", default="openmemory")
    add_parser.add_argument("--content", required=True)
    add_parser.add_argument("--metadata", default="{}")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--user", required=True)

    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("--id", required=True)
    update_parser.add_argument("--content")
    update_parser.add_argument("--state", choices=["active", "paused", "archived", "deleted"])
    update_parser.add_argument("--metadata")

    args = parser.parse_args()

    if args.command == "add":
        metadata = json.loads(args.metadata)
        print(json.dumps(add_memory(args.user, args.app, args.content, metadata), ensure_ascii=False, indent=2))
        return 0

    if args.command == "list":
        print(json.dumps(list_memories(args.user), ensure_ascii=False, indent=2))
        return 0

    if args.command == "update":
        metadata = json.loads(args.metadata) if args.metadata else None
        print(json.dumps(update_memory(args.id, args.content, args.state, metadata), ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
