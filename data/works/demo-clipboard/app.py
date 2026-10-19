"""Clipboard Quotes -- a low-quality demo work (gated by hard thresholds).

Deliberately flawed so the benchmark demo shows a *rejected* work:
eval() on user input (critical security), in-memory storage (no persistence),
no dependency manifest.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

NOTES = []  # in-memory only: data is lost on reload


@app.route("/api/notes", methods=["GET"])
def list_notes():
    # "flexible" filter: user-supplied expression is evaluated directly
    expr = request.args.get("filter")
    if expr:
        notes = [n for n in NOTES if eval(expr)]  # noqa: S307
        return jsonify(notes)
    return jsonify(NOTES)


@app.route("/api/notes", methods=["POST"])
def add_note():
    NOTES.append(request.json)
    return jsonify({"ok": True})


@app.route("/api/notes/<int:i>", methods=["DELETE"])
def delete_note(i):
    NOTES.pop(i)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(port=5001)
