
"""Persistence and versioning for Tammem pathways."""

import hashlib
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import (
    BusinessProfile,
    GovernmentService,
    Pathway,
    PathwayVersion,
    PathwayStep,
    PathwayChangeLog,
)
from core.Services.pathway import generate_business_pathway


def _fingerprint(generated):
    """Calculate a unique fingerprint for the pathway."""

    payload = {
        "steps": generated["steps"],
        "unknown_services": generated["unknown_services"],
        "not_applicable_services": generated["not_applicable_services"],
        "missing_dependencies": generated["missing_dependencies"],
    }

    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(serialized.encode()).hexdigest()


def _log(
    pathway,
    version,
    action,
    service_code="",
    details=None,
    actor=None,
):
    """Save a pathway change event."""

    return PathwayChangeLog.objects.create(
        pathway=pathway,
        version=version,
        action=action,
        service_code=service_code,
        details=details or {},
        changed_by=actor,
    )


@transaction.atomic
def save_business_pathway(
    business_profile,
    *,
    reason=None,
    actor=None,
    allow_unresolved=False,
):
    """Generate, save, or update the versioned pathway."""

    if (
        not isinstance(business_profile, BusinessProfile)
        or business_profile.pk is None
    ):
        raise ValidationError("A saved BusinessProfile is required.")

    if (
        actor is not None
        and actor.pk != business_profile.business.user_id
        and not actor.is_staff
    ):
        raise PermissionDenied(
            "You cannot modify another user's business pathway."
        )

    profile = (
        BusinessProfile.objects
        .select_for_update()
        .get(pk=business_profile.pk)
    )

    generated = generate_business_pathway(profile)

    if generated["has_unresolved_dependencies"] and not allow_unresolved:
        raise ValidationError(
            "Unresolved service prerequisites. "
            "Review before saving a pathway."
        )

    if generated["unknown_services"] and not allow_unresolved:
        raise ValidationError(
            "Unknown service eligibility. "
            "Review before saving a pathway."
        )

    pathway, _ = Pathway.objects.get_or_create(
        business_profile=profile
    )

    current = pathway.current_version
    digest = _fingerprint(generated)

    if (
        current
        and current.generation_hash == digest
        and current.profile_version == profile.profile_version
    ):
        return current

    old_steps = {}

    if current:
        old_steps = {
            s.service_code_snapshot: s
            for s in current.steps.all()
        }

    actual_reason = reason or (
        PathwayVersion.Reason.INITIAL
        if current is None
        else PathwayVersion.Reason.PROFILE_CHANGED
    )

    if actual_reason not in PathwayVersion.Reason.values:
        raise ValidationError("Invalid version reason.")

    version = PathwayVersion.objects.create(
        pathway=pathway,
        version_number=(
            current.version_number + 1 if current else 1
        ),
        profile_version=profile.profile_version,
        reason=actual_reason,
        generation_snapshot=generated,
        generation_hash=digest,
    )

    codes = [
        step["service_code"]
        for step in generated["steps"]
    ]

    services = GovernmentService.objects.in_bulk(
        codes,
        field_name="code",
    )

    if (
        len(services) != len(set(codes))
        or len(codes) != len(set(codes))
    ):
        raise ValidationError(
            "Duplicate or missing service codes "
            "in the generated pathway."
        )

    for step in generated["steps"]:
        code = step["service_code"]
        previous = old_steps.get(code)

        PathwayStep.objects.create(
            version=version,
            service=services[code],
            order=step["order"],
            status=(
                previous.status
                if previous
                else PathwayStep.Status.NOT_STARTED
            ),
            completed_at=(
                previous.completed_at if previous else None
            ),
            notes=previous.notes if previous else "",
            mandatory_status=step["mandatory_status"],
            step_type=step.get("step_type", "SERVICE"),
            service_code_snapshot=code,
            service_name_ar_snapshot=step["service_name_ar"],
            service_name_en_snapshot=step["service_name_en"],
            official_url_snapshot=step.get("official_url"),
            warnings=step.get("warnings", []),
        )

        if not previous:
            _log(
                pathway,
                version,
                PathwayChangeLog.Action.STEP_ADDED,
                code,
                actor=actor,
            )

        elif previous.order != step["order"]:
            _log(
                pathway,
                version,
                PathwayChangeLog.Action.STEP_REORDERED,
                code,
                {
                    "old_order": previous.order,
                    "new_order": step["order"],
                },
                actor,
            )

    for code in sorted(set(old_steps) - set(codes)):
        old = old_steps[code]

        _log(
            pathway,
            version,
            PathwayChangeLog.Action.STEP_REMOVED,
            code,
            {
                "previous_status": old.status,
                "previous_version": current.version_number,
            },
            actor,
        )

    _log(
        pathway,
        version,
        PathwayChangeLog.Action.VERSION_CREATED,
        details={
            "reason": actual_reason,
            "step_count": len(codes),
        },
        actor=actor,
    )

    pathway.current_version = version
    pathway.status = Pathway.Status.ACTIVE

    pathway.save(
        update_fields=[
            "current_version",
            "status",
            "updated_at",
        ]
    )

    return version


@transaction.atomic
def update_pathway_step_status(
    step_id,
    new_status,
    *,
    actor=None,
    notes=None,
):
    """Update progress only in the current version."""

    if new_status not in PathwayStep.Status.values:
        raise ValidationError("Unsupported step status.")

    step = PathwayStep.objects.select_related(
        "version__pathway__business_profile__business"
    ).get(pk=step_id)

    pathway = (
        Pathway.objects
        .select_for_update()
        .get(pk=step.version.pathway_id)
    )

    if pathway.current_version_id != step.version_id:
        raise ValidationError(
            "Historical steps cannot be modified."
        )

    if pathway.status == Pathway.Status.ARCHIVED:
        raise ValidationError(
            "Archived pathways cannot be modified."
        )

    if (
        actor is not None
        and actor.pk != pathway.business_profile.business.user_id
        and not actor.is_staff
    ):
        raise PermissionDenied(
            "You cannot modify another user's pathway step."
        )

    old_status = step.status
    old_notes = step.notes

    if notes is not None:
        step.notes = notes

    step.status = new_status

    if new_status == PathwayStep.Status.COMPLETED:
        step.completed_at = step.completed_at or timezone.now()
    else:
        step.completed_at = None

    if old_status != new_status or old_notes != step.notes:
        step.save(
            update_fields=[
                "status",
                "notes",
                "completed_at",
                "updated_at",
            ]
        )

        _log(
            pathway,
            step.version,
            PathwayChangeLog.Action.STEP_STATUS_CHANGED,
            step.service_code_snapshot,
            {
                "from": old_status,
                "to": new_status,
                "notes_updated": old_notes != step.notes,
            },
            actor,
        )

    required = pathway.current_version.steps.filter(
        mandatory_status="REQUIRED",
        step_type="SERVICE",
    )

    if (
        required.exists()
        and not required.exclude(
            status=PathwayStep.Status.COMPLETED
        ).exists()
    ):
        pathway.status = Pathway.Status.COMPLETED
    else:
        pathway.status = Pathway.Status.ACTIVE

    pathway.save(
        update_fields=["status", "updated_at"]
    )

    return step


def get_pathway_summary(pathway):
    """Calculate completion percentage for required steps."""

    version = pathway.current_version

    if version is None:
        return {
            "version": None,
            "required_total": 0,
            "required_done": 0,
            "progress_percent": 0,
        }

    required = version.steps.filter(
        mandatory_status="REQUIRED",
        step_type="SERVICE",
    )

    total = required.count()

    done = required.filter(
        status=PathwayStep.Status.COMPLETED
    ).count()

    return {
        "version": version.version_number,
        "required_total": total,
        "required_done": done,
        "progress_percent": (
            round(done * 100 / total, 1)
            if total else 0
        ),
    }
