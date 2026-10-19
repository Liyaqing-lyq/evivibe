"""Campus Todo -- demo work for EviVibe.

A small Flask + SQLite todo application used as the reference artifact in
the repository's demo data.  The evaluation itself runs against the recorded
runtime trace (runtime_trace.json) via the replay runner; this file is the
artifact (C in A = {R, P, T, C, E, U}) under static analysis.
"""

import sqlite3

from flask import Flask, jsonify, request

app = Flask(__name__)
DB = "todos.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS todos ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL,"
        " done INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/todos", methods=["GET"])
def list_todos():
    """Return all todos, newest first; supports ?q= fuzzy search."""
    query = request.args.get("q", "").strip()
    conn = get_db()
    if query:
        rows = conn.execute(
            "SELECT * FROM todos WHERE title LIKE ? ORDER BY id DESC",
            (f"%{query}%",)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM todos ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/todos", methods=["POST"])
def add_todo():
    """Add a todo entry. Empty or whitespace-only titles are rejected."""
    title = (request.json or {}).get("title", "").strip()
    if not title:
        return jsonify({"error": "title must not be empty"}), 400
    conn = get_db()
    cur = conn.execute("INSERT INTO todos (title) VALUES (?)", (title,))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id, "title": title}), 201


@app.route("/api/todos/<int:todo_id>", methods=["PUT"])
def update_todo(todo_id):
    title = (request.json or {}).get("title", "").strip()
    if not title:
        return jsonify({"error": "title must not be empty"}), 400
    conn = get_db()
    conn.execute("UPDATE todos SET title = ? WHERE id = ?", (title, todo_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    conn = get_db()
    conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(port=5000)
