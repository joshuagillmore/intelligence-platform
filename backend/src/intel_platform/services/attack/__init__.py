"""MITRE ATT&CK® integration.

Fetch + parse the pinned Enterprise STIX 2.1 bundle, load it into Neo4j as a
global (non-project) reference model, resolve project TTP/ThreatActor entities to
canonical ATT&CK nodes, and drive the matrix / technique-detail / Navigator-layer
API off the graph.

MITRE ATT&CK® is used under the ATT&CK Terms of Use — see
``data/attack/ATTRIBUTION.md``.
"""
