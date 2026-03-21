from intel_platform.collection.tasks import CollectionManager, TaskStatus


def test_create_task():
    mgr = CollectionManager()
    task = mgr.create_task(project_id="proj-1", pir="Find info about X")
    assert task.project_id == "proj-1"
    assert task.status == TaskStatus.PENDING


def test_get_task():
    mgr = CollectionManager()
    task = mgr.create_task(project_id="proj-1")
    found = mgr.get_task(task.id)
    assert found is not None
    assert found.id == task.id


def test_update_task():
    mgr = CollectionManager()
    task = mgr.create_task(project_id="proj-1")
    mgr.update_task(task.id, status=TaskStatus.STARTED)
    assert mgr.get_task(task.id).status == TaskStatus.STARTED


def test_list_tasks():
    mgr = CollectionManager()
    mgr.create_task(project_id="proj-1")
    mgr.create_task(project_id="proj-2")
    assert len(mgr.list_tasks()) == 2
    assert len(mgr.list_tasks(project_id="proj-1")) == 1


def test_cancel_task():
    mgr = CollectionManager()
    task = mgr.create_task(project_id="proj-1")
    assert mgr.cancel_task(task.id) is True
    assert mgr.get_task(task.id).status == TaskStatus.REVOKED
