"""Project membership rows (``project_members``) and the Postgres lookups the
access check needs.

Reads: ``memberships`` (how many members each project has, and the caller's
role in it) and ``owning_projects`` (which project a plan, source, catalog
entry or PIR belongs to). Writes: ``put_member``, ``remove_member`` and
``claim_open_project``, which enforce the membership rules — the first member
of a project is an owner, a project never loses its last owner, and only an
open project can be claimed — under a per-project lock, so two concurrent
changes cannot each see an owner the other is removing, or each claim the same
open project.

What a role allows is decided in ``api/access.py``; this module only reads and
writes rows. Every function opens its own session from ``get_session_factory``
and lets database errors propagate: the caller decides what an outage means.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from intel_platform.db.models import (
    CollectionPlan,
    CollectionSource,
    DataCatalog,
    Pir,
    ProjectMember,
)

OWNER = "owner"

# Two-key advisory lock namespace for membership writes, so they serialise per
# project without touching the migration lock (db.engine.MIGRATION_LOCK_KEY).
# Arbitrary but fixed (the bytes of "mbr").
_MEMBERSHIP_LOCK_CLASS = 0x6D6272

FIRST_MEMBER_MUST_BE_OWNER = "The first member of a project must be an owner"
LAST_OWNER = "A project must keep at least one owner"
CONCURRENT_CHANGE = "The project's members changed while this was being saved; try again"
ALREADY_RESTRICTED = "This project already has members, so it cannot be claimed"


class MembershipRuleError(Exception):
    """A membership change refused by a rule. ``str(exc)`` is safe to show."""


class NotAMemberError(Exception):
    """The user named is not a member of the project."""


@dataclass(frozen=True)
class Membership:
    """One project's membership as one caller sees it."""
    members: int          # how many members the project has (0 = open)
    role: str | None      # the caller's role, or None when not a member


def _session_factory():
    # Read through the module each call, so a test that installs its own
    # engine (or a fake factory) on db.engine is honoured.
    from intel_platform.db import engine

    return engine.get_session_factory()


async def memberships(project_ids: Iterable[str] | None, username: str) -> dict[str, Membership]:
    """Membership of each project that has any members; a project absent from
    the result has none. ``project_ids=None`` reads every project."""
    stmt = (
        select(
            ProjectMember.project_id,
            func.count(),
            func.max(case((ProjectMember.username == username, ProjectMember.role))),
        )
        .group_by(ProjectMember.project_id)
    )
    if project_ids is not None:
        ids = sorted({p for p in project_ids if p})
        if not ids:
            return {}
        stmt = stmt.where(ProjectMember.project_id.in_(ids))
    async with _session_factory()() as db:
        rows = (await db.execute(stmt)).all()
    return {pid: Membership(members=int(n), role=role) for pid, n, role in rows}


def _uuids(values: Iterable[str]) -> list[uuid.UUID]:
    """The well-formed UUIDs among ``values``. A malformed id owns nothing; the
    route itself answers it (400 or 404)."""
    out = []
    for value in values:
        try:
            out.append(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


async def owning_projects(
    *,
    plan_ids: Iterable[str] = (),
    source_ids: Iterable[str] = (),
    catalog_ids: Iterable[str] = (),
    pir_ids: Iterable[str] = (),
) -> set[str]:
    """The projects the given plans, sources, catalog entries and PIRs belong to.

    An id that matches no row contributes nothing.
    """
    queries = []
    if ids := _uuids(plan_ids):
        queries.append(select(CollectionPlan.project_id).where(CollectionPlan.id.in_(ids)))
    if ids := _uuids(source_ids):
        queries.append(
            select(CollectionPlan.project_id)
            .join(CollectionSource, CollectionSource.plan_id == CollectionPlan.id)
            .where(CollectionSource.id.in_(ids))
        )
    if ids := _uuids(catalog_ids):
        queries.append(
            select(CollectionPlan.project_id)
            .join(DataCatalog, DataCatalog.plan_id == CollectionPlan.id)
            .where(DataCatalog.id.in_(ids))
        )
    if ids := _uuids(pir_ids):
        queries.append(select(Pir.project_id).where(Pir.id.in_(ids)))
    if not queries:
        return set()
    found: set[str] = set()
    async with _session_factory()() as db:
        for query in queries:
            found.update(pid for (pid,) in (await db.execute(query)).all() if pid)
    return found


_ROLE_ORDER = case(
    (ProjectMember.role == "owner", 0), (ProjectMember.role == "editor", 1), else_=2,
)


async def list_members(project_id: str) -> list[ProjectMember]:
    """A project's members, owners first, then by username."""
    stmt = (
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(_ROLE_ORDER, ProjectMember.username)
    )
    async with _session_factory()() as db:
        return list((await db.execute(stmt)).scalars().all())


async def _locked_members(db, project_id: str) -> list[ProjectMember]:
    await db.execute(select(func.pg_advisory_xact_lock(_MEMBERSHIP_LOCK_CLASS, func.hashtext(project_id))))
    stmt = select(ProjectMember).where(ProjectMember.project_id == project_id)
    return list((await db.execute(stmt)).scalars().all())


def _would_lose_last_owner(rows: list[ProjectMember], current: ProjectMember | None, new_role: str | None) -> bool:
    if current is None or current.role != OWNER or new_role == OWNER:
        return False
    return sum(1 for r in rows if r.role == OWNER) <= 1


async def put_member(project_id: str, username: str, role: str, added_by: str) -> ProjectMember:
    """Add ``username`` to the project with ``role``, or change their role.

    Raises MembershipRuleError when the project has no members and ``role`` is
    not owner, or when the change would leave the project without an owner.
    A role change keeps the original ``added_by`` and ``added_at``.
    """
    try:
        async with _session_factory()() as db:
            async with db.begin():
                rows = await _locked_members(db, project_id)
                if not rows and role != OWNER:
                    raise MembershipRuleError(FIRST_MEMBER_MUST_BE_OWNER)
                current = next((r for r in rows if r.username == username), None)
                if _would_lose_last_owner(rows, current, role):
                    raise MembershipRuleError(LAST_OWNER)
                if current is None:
                    current = ProjectMember(
                        project_id=project_id, username=username, role=role,
                        added_by=added_by, added_at=datetime.now(timezone.utc),
                    )
                    db.add(current)
                else:
                    current.role = role
            return current
    except IntegrityError as exc:
        raise MembershipRuleError(CONCURRENT_CHANGE) from exc


async def add_owner(project_id: str, username: str) -> ProjectMember:
    """Make ``username`` the owner of a project that was just created."""
    return await put_member(project_id, username, OWNER, added_by=username)


async def claim_open_project(project_id: str, username: str) -> ProjectMember:
    """Make ``username`` the first owner of an open project, which restricts it.

    The check that the project has no members and the insert are one
    transaction under the project's membership lock, so of two concurrent
    claims exactly one succeeds. Raises MembershipRuleError when the project
    already has members.
    """
    try:
        async with _session_factory()() as db:
            async with db.begin():
                if await _locked_members(db, project_id):
                    raise MembershipRuleError(ALREADY_RESTRICTED)
                owner = ProjectMember(
                    project_id=project_id, username=username, role=OWNER,
                    added_by=username, added_at=datetime.now(timezone.utc),
                )
                db.add(owner)
            return owner
    except IntegrityError as exc:
        raise MembershipRuleError(CONCURRENT_CHANGE) from exc


async def remove_member(project_id: str, username: str) -> None:
    """Remove ``username`` from the project.

    Raises NotAMemberError when they are not a member, and MembershipRuleError
    when they are its last owner.
    """
    async with _session_factory()() as db:
        async with db.begin():
            rows = await _locked_members(db, project_id)
            current = next((r for r in rows if r.username == username), None)
            if current is None:
                raise NotAMemberError(username)
            if _would_lose_last_owner(rows, current, None):
                raise MembershipRuleError(LAST_OWNER)
            await db.delete(current)
