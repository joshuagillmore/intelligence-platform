from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_create_project():
    response = client.post(
        "/api/projects",
        json={"name": "Test Route Project", "description": "Testing"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Route Project"
    assert data["status"] == "active"
    client.delete(f"/api/projects/{data['id']}", headers=headers)


def test_list_projects():
    response = client.get("/api/projects", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unauthorized():
    response = client.get("/api/projects", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


class TestProjectListCounts:
    """The per-project counts on the landing page.

    They came from one Cypher statement whose `OPTIONAL MATCH (n {project_id:
    p.id})` was unlabeled, so there was no index to use and Neo4j scanned every
    node once per project — an N+1 moved into the planner rather than removed.
    5.44s for 178 projects on a real graph, paid by every session before
    anything rendered. Now one grouped aggregate per count: 0.19s.

    These pin the numbers, which is what the rewrite could plausibly break.
    """

    def _project(self, graph_store, name: str) -> str:
        """A Project node shaped as the app writes them.

        `project_id` is set deliberately: real Project nodes carry it (177 of
        177 on the live graph), so it is the `NOT n:Project` guard that stops
        every project counting itself as one of its own entities. Creating a
        bare node here would leave that guard untested.
        """
        pid = f"test-counts-{name}"
        with graph_store._driver.session() as session:
            session.run(
                "CREATE (p:Project {id: $id, project_id: $id, name: $name, "
                "created_at: '2026-01-01T00:00:00Z'})",
                id=pid, name=name,
            )
        return pid

    def _fetch(self, pid: str) -> dict:
        rows = client.get("/api/projects", headers=headers).json()
        return next(p for p in rows if p["id"] == pid)

    def test_an_empty_project_reports_zeroes_not_nulls(self, graph_store):
        """A project absent from every count map is a zero, not a missing key —
        the UI reads these numbers directly."""
        pid = self._project(graph_store, "empty")
        got = self._fetch(pid)
        assert got["entity_count"] == 0
        assert got["document_count"] == 0
        assert got["relationship_count"] == 0
        assert got["collection_count"] == 0

    def test_entities_documents_and_relationships_are_counted(self, graph_store):
        from intel_platform.models.entities import Document, Organization, Person
        from intel_platform.models.relationships import Relationship

        pid = self._project(graph_store, "populated")
        person = Person(name="Marek Ilyas", project_id=pid)
        org = Organization(name="Kolvane Holdings", project_id=pid)
        doc = Document(name="Ledger", project_id=pid, content="x")
        for e in (person, org, doc):
            graph_store.create_entity(e)
        graph_store.create_relationship(Relationship(
            source_id=person.id, target_id=org.id, rel_type="ASSOCIATED_WITH",
            confidence=1.0, source="test", method="test",
        ))

        got = self._fetch(pid)
        assert got["entity_count"] == 3, "documents are entities too, as before"
        assert got["document_count"] == 1
        assert got["relationship_count"] == 1

    def test_another_projects_data_is_not_counted(self, graph_store):
        """The counts are grouped in one pass over the whole graph now, so
        leaking across projects is the failure mode to guard."""
        from intel_platform.models.entities import Person

        mine = self._project(graph_store, "mine")
        theirs = self._project(graph_store, "theirs")
        graph_store.create_entity(Person(name="A", project_id=mine))
        graph_store.create_entity(Person(name="B", project_id=theirs))
        graph_store.create_entity(Person(name="C", project_id=theirs))

        assert self._fetch(mine)["entity_count"] == 1
        assert self._fetch(theirs)["entity_count"] == 2

    def test_a_cross_project_edge_counts_for_neither(self, graph_store):
        from intel_platform.models.entities import Person
        from intel_platform.models.relationships import Relationship

        a_pid = self._project(graph_store, "left")
        b_pid = self._project(graph_store, "right")
        a = Person(name="A", project_id=a_pid)
        b = Person(name="B", project_id=b_pid)
        graph_store.create_entity(a)
        graph_store.create_entity(b)
        graph_store.create_relationship(Relationship(
            source_id=a.id, target_id=b.id, rel_type="ASSOCIATED_WITH",
            confidence=1.0, source="test", method="test",
        ))

        assert self._fetch(a_pid)["relationship_count"] == 0
        assert self._fetch(b_pid)["relationship_count"] == 0

    def test_the_project_node_is_not_counted_as_its_own_entity(self, graph_store):
        pid = self._project(graph_store, "selfcount")
        assert self._fetch(pid)["entity_count"] == 0
