"""The retroactive name cleanup's planning stage.

Name cleaning runs at write time, so every fix to it only helps entities
extracted afterwards. This script applies the current rules to what is already
in the graph. It deletes and merges nodes, which cannot be undone, so the
planning is separated from the applying and tested on its own.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "clean_entity_names", Path(__file__).resolve().parents[1] / "scripts" / "clean_entity_names.py"
)
cen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cen)


def node(name, label="Organization", project="p1", id=None, created="2026-01-01"):
    return {"id": id or f"{label}:{name}", "name": name, "label": label,
            "project": project, "created": created}


class TestPlanning:
    def test_a_link_span_is_renamed_not_dropped(self):
        renames, drops, merges = cen.plan([node("Europe]")])
        assert [r["cleaned"] for r in renames] == ["Europe"]
        assert drops == []

    def test_pure_markup_is_dropped(self):
        _, drops, _ = cen.plan([node("###", label="Financial")])
        assert len(drops) == 1

    def test_a_clean_name_needs_no_work(self):
        renames, drops, merges = cen.plan([node("Yi Peng 3")])
        assert (renames, drops, merges) == ([], [], [])

    def test_cleaning_is_what_creates_the_duplicate(self):
        """The point of the script: "Germany]" cannot resolve against the
        "Germany" the fixed pipeline now writes, so the duplicate is permanent
        until the old name is rewritten."""
        _, _, merges = cen.plan([node("Germany]", id="a"), node("Germany", id="b")])
        assert len(merges) == 1 and len(merges[0]) == 2

    def test_case_and_whitespace_differences_merge(self):
        _, _, merges = cen.plan([node(" Kaliningrad ", id="a"), node("kaliningrad", id="b")])
        assert len(merges) == 1

    def test_different_projects_never_merge(self):
        _, _, merges = cen.plan([node("Arelion", project="p1"), node("Arelion", project="p2")])
        assert merges == []

    def test_different_labels_never_merge(self):
        """"Eastern Light" exists as both an Organization and a Location on a
        live graph. Whether that is a typing error is a separate question — a
        name-cleanup script must not answer it by fusing the two."""
        _, _, merges = cen.plan([
            node("Eastern Light", label="Organization"),
            node("Eastern Light", label="Location"),
        ])
        assert merges == []

    def test_documents_are_never_merged_by_name(self):
        """Caught by the dry run against a live graph: dozens of separate
        uploads carry the placeholder name `text_input`. Merging by name would
        have collapsed unrelated documents into one."""
        _, _, merges = cen.plan([
            node("text_input", label="Document", id="d1"),
            node("text_input", label="Document", id="d2"),
        ])
        assert merges == []

    def test_documents_are_still_normalised(self):
        """Excluded from merging, not from cleaning."""
        renames, _, _ = cen.plan([node("Chinese)](https://bbc.com/zhongwen", label="Document")])
        assert [r["cleaned"] for r in renames] == ["Chinese"]

    def test_junk_is_dropped_rather_than_merged(self):
        renames, drops, merges = cen.plan([node("##", label="Financial"), node("###", label="Financial")])
        assert len(drops) == 2 and merges == [] and renames == []


class TestSurvivorChoice:
    def test_the_oldest_node_is_kept(self):
        """Other data is likeliest to already point at it."""
        group = [node("A", id="new", created="2026-06-01"), node("A", id="old", created="2026-01-01")]
        assert cen._survivor(group)["id"] == "old"

    def test_a_missing_timestamp_does_not_crash_the_choice(self):
        group = [{"id": "b", "name": "A", "label": "Organization", "project": "p", "created": None},
                 {"id": "a", "name": "A", "label": "Organization", "project": "p", "created": None}]
        assert cen._survivor(group)["id"] == "a"  # deterministic: falls back to id


class TestSafety:
    def test_applying_is_not_the_default(self, monkeypatch, capsys):
        """Deleting and merging graph nodes cannot be undone, so a bare
        invocation must report and change nothing."""
        writes = []

        class _Session:
            def run(self, query, **params):
                if not query.lstrip().startswith("MATCH (n)\n    WHERE"):
                    writes.append(query)
                return []

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        class _Driver:
            def session(self):
                return _Session()

            def close(self):
                pass

        monkeypatch.setattr(cen.GraphDatabase, "driver", lambda *a, **kw: _Driver())
        monkeypatch.setattr(cen, "_scan", lambda *_: [node("Europe]"), node("###", label="Financial")])
        monkeypatch.setattr(cen.sys, "argv", ["clean_entity_names.py"])

        assert cen.main() == 0
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert writes == [], f"a dry run wrote to the graph: {writes}"

    @pytest.mark.parametrize("label", sorted(cen.NEVER_MERGE))
    def test_never_merge_labels_are_excluded_from_the_key(self, label):
        _, _, merges = cen.plan([node("same", label=label, id="1"), node("same", label=label, id="2")])
        assert merges == []
