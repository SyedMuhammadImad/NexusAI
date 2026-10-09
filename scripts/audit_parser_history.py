"""Read-only historical parser comparison; never changes archived corrections."""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from services.chat_import_service import parser_differences
from services.signal_parser import PARSER_VERSION


def audit(path):
    path = Path(path).resolve()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    changes = []
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT id,import_id,payload FROM messages ORDER BY import_id,ordinal").fetchall()
        groups = {r[0]: json.loads(r[1])["group"] for r in conn.execute("SELECT id,metadata FROM imports")}
        for message_id, import_id, payload in rows:
            row = json.loads(payload)
            if row["kind"] != "signal":
                continue
            differences = parser_differences(row, groups[import_id])
            if differences:
                changes.append({"message_id": message_id, "import_id": import_id,
                                "review_required": True, "has_corrections": bool(row.get("review_history")),
                                "original_status": row["review_status"], "differences": differences})
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()
    return {"source_sha256": before, "parser_version": PARSER_VERSION, "messages_checked": len(rows),
            "changed_signals": len(changes), "changes": changes, "source_unchanged": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "changes"}))
