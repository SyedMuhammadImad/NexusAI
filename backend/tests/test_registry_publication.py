"""Storage regression only; inert artifacts and temporary fixture paths."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from core.rebuild.p8_registry import Registry
from test_p8_research import entry


def test_publication_is_inside_cross_connection_write_lock(tmp_path, monkeypatch):
    registry = Registry(tmp_path / 'registry', fixture=True)
    replace = Path.replace
    publications = []

    def checked_replace(path, target):
        if path.parent == registry.root and path.name.startswith('.p8-artifact-'):
            with sqlite3.connect(registry.path, timeout=0) as other:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    other.execute('BEGIN IMMEDIATE')
            publications.append(target)
        return replace(path, target)

    monkeypatch.setattr(Path, 'replace', checked_replace)
    identity = registry.register(entry(), {'prior': .3})
    assert len(publications) == 1
    assert registry.read(identity)[1] == {'prior': .3}


def test_independent_registry_instances_concurrently_publish_once(tmp_path, monkeypatch):
    root = tmp_path / 'registry'
    registries = [Registry(root, fixture=True) for _ in range(4)]
    replace = Path.replace
    publications = []

    def count_replace(path, target):
        if path.parent == root and path.name.startswith('.p8-artifact-'):
            publications.append(target)
        return replace(path, target)

    monkeypatch.setattr(Path, 'replace', count_replace)
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda n: registries[n % 4].register(entry(), {'prior': .3}), range(100)))
    assert len(set(ids)) == 1
    assert len(publications) == 1
    with registries[0].connect() as conn:
        assert conn.execute('SELECT count(*) FROM models').fetchone()[0] == 1
    assert registries[-1].read(ids[0])[1] == {'prior': .3}
