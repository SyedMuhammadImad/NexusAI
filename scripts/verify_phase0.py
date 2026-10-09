"""Local restore drill and known-secret/object-history scan. Never prints secret values."""
import argparse
import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import zipfile
from pathlib import Path

from dotenv import dotenv_values


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def contained_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Manifest path escapes snapshot")
    return path


def restore(snapshot, destination):
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if destination.exists():
        raise ValueError("Restore destination must be new; no overwrite permitted")
    source = (snapshot / "source").resolve()
    file_paths = set()
    for record in manifest["files"]:
        path = contained_path(source, record["path"])
        if path in file_paths:
            raise ValueError("Duplicate file in manifest")
        file_paths.add(path)
        if sha(path) != record["sha256"]:
            raise ValueError("Snapshot checksum mismatch")
    database_paths = set()
    for record in manifest["databases"]:
        path = contained_path(source, record["path"])
        if path not in file_paths or path in database_paths:
            raise ValueError("Database must appear exactly once in the verified manifest")
        database_paths.add(path)
    shutil.copytree(snapshot / "source", destination)
    for record in manifest["files"]:
        if sha(destination / record["path"]) != record["sha256"]:
            raise ValueError("Restored file mismatch")
    databases = []
    archives_verified = 0
    for record in manifest["databases"]:
        path = (destination / record["path"]).resolve()
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Restored database failed integrity check")
            digest = hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()
            if digest != record["content_hash"]:
                raise ValueError("Restored database contents differ")
            if path.name == "archive.sqlite3":
                for (blob,) in conn.execute("SELECT archive FROM imports WHERE archive IS NOT NULL"):
                    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                        if archive.testzip() is not None:
                            raise ValueError("Restored archive CRC failed")
                        archives_verified += 1
        databases.append(path.name)
    return {"snapshot": str(snapshot), "restored_to":str(destination), "files_verified":len(manifest["files"]),
            "databases_verified":databases, "archive_crc_verified":archives_verified > 0,
            "archives_verified":archives_verified}


def scan_repositories(root):
    repos = [p for p in (root, root.parent/'github-files',root.parent/'github-sync-Multi-Agent-Trading-Simulator') if (p/'.git').exists()]
    values = set()
    for repo in repos:
        env = repo/'backend/.env'
        if env.exists():
            for key,value in dotenv_values(env).items():
                if value and len(value)>=6 and any(word in key for word in ('PASSWORD','TOKEN','API_KEY','SECRET','LOGIN')):
                    values.add(value.encode())
    token = root/'backend/private/control_token.txt'
    if token.exists():
        value = token.read_bytes().strip()
        if value:
            values.add(value)
    import re
    key_pattern = re.compile(rb"\bsk-[a-zA-Z0-9_-]{32,}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    results=[]
    for repo in repos:
        command=['git','-c',f'safe.directory={repo.as_posix()}','-C',str(repo)]
        listing=subprocess.check_output(command+['cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype) %(objectsize)']).decode().splitlines()
        findings=[]
        for row in listing:
            object_id,kind,size=row.split()
            if kind not in {'blob','commit','tag'}:
                continue
            body=subprocess.check_output(command+['cat-file',kind,object_id])
            if any(secret in body for secret in values) or key_pattern.search(body):
                findings.append({'object_id':object_id,'type':kind})
        results.append({'repository':str(repo),'objects_inventoried':len(listing),'findings':findings})
    return {'scope':'All locally present Git objects, including unreachable objects; no remote fetch/publication',
            'known_secret_and_private_key_scan':results,'secret_values_emitted':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--restore-to',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    report={'restore':restore(args.snapshot.resolve(),args.restore_to.resolve()),'history_scan':scan_repositories(root)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
