"""The verb map says what it does (review, Low → G: duplicate YAML keys).

`relationship_types.yaml` listed `deploy` under USES and again under
DEPLOYED_AT, and `station` under LOCATED_AT and again under DEPLOYED_AT. YAML
keeps the last duplicate silently, so the file read one way and ran another.

The map drives dependency-parse extraction, which links a verb's subject to its
direct object: "APT29 deployed SUNBURST" yields APT29 → SUNBURST. USES reads
correctly there; DEPLOYED_AT ("forces deployed at a location") does not, so
`deploy` keeps USES. For `station` neither reading fits a subject → object
pair, so it keeps the mapping it has run with (DEPLOYED_AT) rather than change
behaviour on no evidence.
"""
from __future__ import annotations

from pathlib import Path

import yaml

import intel_platform.data as data_pkg
from intel_platform.data import get_verb_mappings

YAML_PATH = Path(data_pkg.__file__).parent / "relationship_types.yaml"


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    seen: dict = {}
    for key_node, _value in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise AssertionError(
                f"duplicate key {key!r} at lines {seen[key]} and {key_node.start_mark.line + 1}"
            )
        seen[key] = key_node.start_mark.line + 1
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def test_no_key_appears_twice():
    yaml.load(YAML_PATH.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)


def test_deploy_links_an_actor_to_what_it_uses():
    assert get_verb_mappings()["deploy"] == "USES"


def test_station_keeps_the_mapping_it_ran_with():
    assert get_verb_mappings()["station"] == "DEPLOYED_AT"


def test_every_verb_maps_to_a_declared_relationship_type():
    declared = set(yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["relationship_types"])
    assert set(get_verb_mappings().values()) <= declared
