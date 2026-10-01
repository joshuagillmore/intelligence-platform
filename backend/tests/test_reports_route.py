from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_save_and_list_reports():
    # Create project first
    proj = client.post("/api/projects", json={"name": "Report Test"}, headers=headers).json()
    pid = proj["id"]

    # Save report
    resp = client.post("/api/reports", json={
        "project_id": pid, "title": "Test Report", "content": "Test content", "report_type": "INTSUM"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["report_id"]

    # List reports
    resp = client.get("/api/reports", params={"project_id": pid}, headers=headers)
    assert resp.status_code == 200

    # Cleanup
    client.delete(f"/api/projects/{pid}", headers=headers)

def test_report_not_found():
    resp = client.get("/api/reports/nonexistent", headers=headers)
    assert resp.status_code == 404


class TestDeleteIsScopedToReports:
    """Low -> R: `DELETE /reports/{id}` deleted any node by id — an entity, a
    Document, another project's report — and answered "deleted" either way."""

    @staticmethod
    def _seed(graph_store):
        import uuid

        from intel_platform.models.entities import Organization
        from intel_platform.services.reports import ReportService

        pid = tp(f"reports-{uuid.uuid4().hex[:8]}")
        report_id = ReportService(graph_store).save_report(
            project_id=pid, title="INTSUM", content="c", report_type="INTSUM",
        )["report_id"]
        org = Organization(name="Not a report", project_id=pid)
        graph_store.create_entity(org)
        return pid, report_id, org.id

    @staticmethod
    def _delete(graph_store, node_id, **params):
        from intel_platform.api.deps import get_graph_store

        app.dependency_overrides[get_graph_store] = lambda: graph_store
        try:
            return client.delete(f"/api/reports/{node_id}", params=params, headers=headers)
        finally:
            app.dependency_overrides.pop(get_graph_store, None)

    def test_a_non_report_node_is_not_deleted(self, graph_store):
        _pid, _report_id, org_id = self._seed(graph_store)
        assert self._delete(graph_store, org_id).status_code == 404
        assert graph_store.get_entity(org_id) is not None

    def test_another_projects_report_is_not_deleted(self, graph_store):
        _pid, report_id, _org = self._seed(graph_store)
        assert self._delete(graph_store, report_id, project_id=tp("someone-else")).status_code == 404
        assert graph_store.get_entity(report_id) is not None

    def test_a_report_in_its_project_is_deleted(self, graph_store):
        pid, report_id, _org = self._seed(graph_store)
        resp = self._delete(graph_store, report_id, project_id=pid)
        assert resp.status_code == 200 and resp.json() == {"status": "deleted"}
        assert graph_store.get_entity(report_id) is None

    def test_an_unknown_id_is_404_not_deleted(self, graph_store):
        assert self._delete(graph_store, "no-such-report").status_code == 404


class TestGetIsScopedToReports:
    """Low -> R: `GET /reports/{id}` returned any node by id — an entity, a
    Document, another project's report. Scoped like DELETE: only a Report, and
    only in `project_id` when given."""

    @staticmethod
    def _get(graph_store, node_id, **params):
        from intel_platform.api.deps import get_graph_store

        app.dependency_overrides[get_graph_store] = lambda: graph_store
        try:
            return client.get(f"/api/reports/{node_id}", params=params, headers=headers)
        finally:
            app.dependency_overrides.pop(get_graph_store, None)

    def test_a_non_report_node_is_404(self, graph_store):
        _pid, _report_id, org_id = TestDeleteIsScopedToReports._seed(graph_store)
        assert self._get(graph_store, org_id).status_code == 404

    def test_another_projects_report_is_404(self, graph_store):
        _pid, report_id, _org = TestDeleteIsScopedToReports._seed(graph_store)
        assert self._get(graph_store, report_id, project_id=tp("someone-else")).status_code == 404

    def test_a_report_in_its_project_is_returned(self, graph_store):
        pid, report_id, _org = TestDeleteIsScopedToReports._seed(graph_store)
        resp = self._get(graph_store, report_id, project_id=pid)
        assert resp.status_code == 200
        assert resp.json()["id"] == report_id
        assert resp.json()["entity_type"] == "Report"

    def test_without_a_project_a_report_is_still_returned(self, graph_store):
        _pid, report_id, _org = TestDeleteIsScopedToReports._seed(graph_store)
        assert self._get(graph_store, report_id).status_code == 200
