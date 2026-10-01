# Registers collection_jobs on Base.metadata for anything that imports the
# collection package before db.models does. db/models.py carries the canonical
# import (`from intel_platform.db import jobs`); this one is a harmless duplicate.
from intel_platform.db import jobs as _jobs  # noqa: F401
