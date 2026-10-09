import hashlib
import importlib.util
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_phase0.py"
SPEC = importlib.util.spec_from_file_location("verify_phase0", SCRIPT)
verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verification)


def snapshot(tmp_path, archive=True):
    root = tmp_path / "snapshot"
    source = root / "source"
    source.mkdir(parents=True)
    database = source / "archive.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE imports (archive BLOB)")
        if archive:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as output:
                output.writestr("chat.txt", "Original source evidence")
            conn.execute("INSERT INTO imports VALUES (?)", (stream.getvalue(),))
        conn.commit()
        digest = hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()
    manifest = {
        "files": [{"path": database.name, "sha256": verification.sha(database)}],
        "databases": [{"path": database.name, "content_hash": digest}],
    }
    return root, manifest


def run_restore(root, manifest, destination):
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return verification.restore(root, destination)


@pytest.mark.parametrize("archive", [True, False])
def test_restore_proves_only_archives_actually_checked(tmp_path, archive):
    root, manifest = snapshot(tmp_path, archive)
    report = run_restore(root, manifest, tmp_path / "restored")
    assert report["files_verified"] == 1
    assert report["archive_crc_verified"] is archive
    assert report["archives_verified"] == int(archive)
    assert report["databases_verified"] == ["archive.sqlite3"]


@pytest.mark.parametrize("section", ["files", "databases"])
def test_escaping_manifest_path_rejected_before_copy(tmp_path, section):
    root, manifest = snapshot(tmp_path)
    manifest[section][0]["path"] = "../../outside.sqlite3"
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="escapes"):
        run_restore(root, manifest, destination)
    assert not destination.exists()


@pytest.mark.parametrize("section", ["files", "databases"])
def test_duplicate_manifest_entries_rejected_before_copy(tmp_path, section):
    root, manifest = snapshot(tmp_path)
    manifest[section].append(dict(manifest[section][0]))
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="Duplicate|exactly once"):
        run_restore(root, manifest, destination)
    assert not destination.exists()


def test_unverified_database_rejected_before_copy(tmp_path):
    root, manifest = snapshot(tmp_path)
    manifest["databases"][0]["path"] = "unlisted.sqlite3"
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="verified manifest"):
        run_restore(root, manifest, destination)
    assert not destination.exists()


def test_file_tampering_rejected_before_copy(tmp_path):
    root, manifest = snapshot(tmp_path)
    manifest["files"][0]["sha256"] = "0" * 64
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="checksum"):
        run_restore(root, manifest, destination)
    assert not destination.exists()


def test_logical_database_tampering_fails_restore_verification(tmp_path):
    root, manifest = snapshot(tmp_path)
    manifest["databases"][0]["content_hash"] = "0" * 64
    with pytest.raises(ValueError, match="contents differ"):
        run_restore(root, manifest, tmp_path / "restored")


def test_existing_destination_never_overwritten(tmp_path):
    root, manifest = snapshot(tmp_path)
    destination = tmp_path / "restored"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("Keep existing evidence", encoding="utf-8")
    with pytest.raises(ValueError, match="no overwrite"):
        run_restore(root, manifest, destination)
    assert marker.read_text(encoding="utf-8") == "Keep existing evidence"
