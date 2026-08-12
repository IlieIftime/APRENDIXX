"""Transactional learning-access policy shared by curriculum repositories."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Connection
from uuid import UUID

from aprendix.application.contracts import LearningAccessDTO, LearningAccessReason


def valid_completed_ids(connection: Connection, user_id: UUID) -> frozenset[str]:
    """Return only progress whose prerequisites and project evidence are valid.

    This is intentionally derived from immutable timestamps instead of rewriting
    legacy rows. It lets migrations retain audit history without letting an old,
    prematurely credited row unlock later curriculum.
    """

    rows = connection.execute(
        """SELECT p.unit_id,p.completed_at,u.kind,u.exercise_id,t.slug track_slug
           FROM learning_unit_progress p
           JOIN learning_units u ON u.id=p.unit_id
           JOIN learning_chapters c ON c.id=u.chapter_id
           JOIN learning_tracks t ON t.id=c.track_id
           WHERE p.user_id=? ORDER BY p.completed_at,p.unit_id""",
        (str(user_id),),
    ).fetchall()
    progress = {str(row["unit_id"]): row for row in rows}
    practice_evidence = {
        str(row["unit_id"])
        for row in connection.execute(
            """SELECT DISTINCT u.id unit_id FROM learning_unit_progress p
               JOIN learning_units u ON u.id=p.unit_id AND u.kind='practice'
               JOIN attempts a ON a.user_id=p.user_id
                              AND a.exercise_id=u.exercise_id
                              AND a.status='passed'
               WHERE p.user_id=?
                 AND COALESCE(a.submitted_at,a.created_at)<=p.completed_at""",
            (str(user_id),),
        ).fetchall()
    }
    assessment_evidence = {
        str(row["unit_id"])
        for row in connection.execute(
            """SELECT DISTINCT u.id unit_id FROM learning_unit_progress p
               JOIN learning_units u ON u.id=p.unit_id
                                    AND u.kind IN ('quiz','hybrid')
               JOIN assessment_items item ON item.unit_id=u.id
               JOIN assessment_attempts attempt
                 ON attempt.item_id=item.id AND attempt.user_id=p.user_id
                AND attempt.passed=1 AND attempt.created_at<=p.completed_at
               WHERE p.user_id=?""",
            (str(user_id),),
        ).fetchall()
    }
    dependencies: dict[str, frozenset[str]] = {}
    for row in connection.execute(
        "SELECT unit_id,prerequisite_unit_id FROM learning_unit_dependencies"
    ).fetchall():
        dependencies.setdefault(str(row["unit_id"]), set()).add(
            str(row["prerequisite_unit_id"])
        )
    for row in connection.execute(
        """SELECT child.id unit_id,parent.id prerequisite_unit_id
           FROM learning_units child
           JOIN learning_chapters child_chapter
             ON child_chapter.id=child.chapter_id
           JOIN course_prerequisites cp
             ON cp.track_id=child_chapter.track_id
           JOIN learning_chapters parent_chapter
             ON parent_chapter.track_id=cp.prerequisite_track_id
           JOIN learning_units parent
             ON parent.chapter_id=parent_chapter.id AND parent.kind='project'"""
    ).fetchall():
        dependencies.setdefault(str(row["unit_id"]), set()).add(
            str(row["prerequisite_unit_id"])
        )
    dependencies = {
        key: frozenset(value) for key, value in dependencies.items()
    }
    valid_projects = {
        str(row["unit_id"])
        for row in connection.execute(
            """SELECT DISTINCT u.id unit_id
               FROM portfolio_projects pp
               JOIN guided_project_templates g ON g.id=pp.template_id
               JOIN project_evaluations pe ON pe.project_id=pp.project_id
                                      AND pe.passed=1
               JOIN learning_tracks t ON t.slug=g.track_slug
               JOIN learning_chapters c ON c.track_id=t.id
               JOIN learning_units u ON u.chapter_id=c.id AND u.kind='project'
               JOIN learning_unit_progress p ON p.unit_id=u.id
                    AND p.user_id=pp.user_id
               WHERE pp.user_id=? AND g.capstone=1
                 AND pe.evaluated_at<=p.completed_at""",
            (str(user_id),),
        ).fetchall()
    }
    accepted: set[str] = set()
    pending = set(progress)
    changed = True
    while changed:
        changed = False
        for identity in tuple(sorted(pending)):
            row = progress[identity]
            parents = dependencies.get(identity, frozenset())
            if not parents.issubset(accepted):
                continue
            if any(
                progress[parent]["completed_at"] > row["completed_at"]
                for parent in parents if parent in progress
            ):
                pending.remove(identity)
                changed = True
                continue
            if row["kind"] == "practice" and identity not in practice_evidence:
                pending.remove(identity)
                changed = True
                continue
            if row["kind"] in {"quiz", "hybrid"} and identity not in assessment_evidence:
                pending.remove(identity)
                changed = True
                continue
            if row["kind"] == "project" and identity not in valid_projects:
                pending.remove(identity)
                changed = True
                continue
            accepted.add(identity)
            pending.remove(identity)
            changed = True
    return frozenset(accepted)


def access_from_state(
    *, resource_id: str, resource_kind: str, track_slug: str = "",
    completed: bool, prerequisite_ids: Iterable[str],
    completed_ids: Iterable[str],
) -> LearningAccessDTO:
    """Build an access decision without conflating visibility and credit."""

    prerequisites = frozenset(str(item) for item in prerequisite_ids)
    completed_set = frozenset(str(item) for item in completed_ids)
    missing = tuple(sorted(prerequisites - completed_set))
    if completed:
        reason = LearningAccessReason.COMPLETED
        eligible = False
    elif missing:
        reason = LearningAccessReason.PREREQUISITES_INCOMPLETE
        eligible = False
    else:
        reason = LearningAccessReason.ELIGIBLE
        eligible = True
    return LearningAccessDTO(
        resource_id=resource_id,
        resource_kind=resource_kind,
        track_slug=track_slug,
        viewable=True,
        credit_eligible=eligible,
        completed=completed,
        reason_code=reason,
        missing_prerequisite_ids=missing,
    )


def unit_access(
    connection: Connection, user_id: UUID, unit_id: str,
) -> LearningAccessDTO:
    """Read one unit and all of its prerequisites on the caller's connection."""

    row = connection.execute(
        """SELECT u.id,u.kind,t.id track_id,t.slug track_slug,
                  EXISTS(SELECT 1 FROM learning_unit_progress p
                         WHERE p.user_id=? AND p.unit_id=u.id) completed
           FROM learning_units u
           JOIN learning_chapters c ON c.id=u.chapter_id
           JOIN learning_tracks t ON t.id=c.track_id
           WHERE u.id=?""",
        (str(user_id), unit_id),
    ).fetchone()
    if row is None:
        raise KeyError(unit_id)
    prerequisites = tuple(item[0] for item in connection.execute(
        """SELECT prerequisite_unit_id FROM learning_unit_dependencies
           WHERE unit_id=? ORDER BY prerequisite_unit_id""",
        (unit_id,),
    ).fetchall())
    course_prerequisites = tuple(item[0] for item in connection.execute(
        """SELECT parent.id FROM course_prerequisites cp
           JOIN learning_chapters parent_chapter
             ON parent_chapter.track_id=cp.prerequisite_track_id
           JOIN learning_units parent
             ON parent.chapter_id=parent_chapter.id AND parent.kind='project'
           WHERE cp.track_id=? ORDER BY parent.id""",
        (row["track_id"],),
    ).fetchall())
    completed_ids = valid_completed_ids(connection, user_id)
    return access_from_state(
        resource_id=str(row["id"]), resource_kind=str(row["kind"]),
        track_slug=str(row["track_slug"]), completed=str(row["id"]) in completed_ids,
        prerequisite_ids=(*prerequisites, *course_prerequisites),
        completed_ids=completed_ids,
    )


def practice_access(
    connection: Connection, user_id: UUID, exercise_id: UUID,
) -> LearningAccessDTO:
    """Choose the first creditable curricular mapping for an exercise."""

    rows = connection.execute(
        """SELECT u.id FROM learning_units u
           JOIN learning_chapters c ON c.id=u.chapter_id
           JOIN learning_tracks t ON t.id=c.track_id
           WHERE u.exercise_id=? AND u.kind='practice'
           ORDER BY t.position,c.position,u.position,u.id""",
        (str(exercise_id),),
    ).fetchall()
    if not rows:
        return LearningAccessDTO(
            resource_id=str(exercise_id), resource_kind="standalone_practice",
            viewable=True, credit_eligible=True, completed=False,
            reason_code=LearningAccessReason.STANDALONE_PRACTICE,
        )
    decisions = tuple(unit_access(connection, user_id, str(row["id"])) for row in rows)
    for decision in decisions:
        if decision.credit_eligible:
            return decision
    for decision in decisions:
        if decision.completed:
            return decision
    return decisions[0]


def override_access(
    access: LearningAccessDTO, reason: LearningAccessReason, *,
    credit_eligible: bool = False,
) -> LearningAccessDTO:
    """Preserve resource context while explaining a stronger domain rule."""

    return access.model_copy(update={
        "credit_eligible": credit_eligible,
        "reason_code": reason,
    })
