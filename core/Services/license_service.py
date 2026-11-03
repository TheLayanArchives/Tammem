from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Business,
    GovernmentService,
    LicenseRecord,
    PathwayStep,
)
from core.Services.compliance_service import (
    sync_license_renewal_event,
)


_UNSET = object()


def _owned_business(actor, business_id):
    business = Business.objects.filter(
        pk=business_id,
        user=actor,
    ).first()

    if business is None:
        raise PermissionDenied(
            "You cannot access license records for this business."
        )

    return business


def _owned_license_record(actor, license_record_id):
    record = (
        LicenseRecord.objects
        .select_related("business", "government_service", "pathway_step")
        .filter(
            pk=license_record_id,
            business__user=actor,
        )
        .first()
    )

    if record is None:
        raise PermissionDenied(
            "You cannot access this license record."
        )

    return record


def _validate_dates(issue_date, expiry_date):
    if (
        issue_date is not None
        and expiry_date is not None
        and expiry_date < issue_date
    ):
        raise ValidationError({
            "expiry_date": "Expiry date cannot be before the issue date."
        })


def _validate_expiry_tracking(service, expiry_date):
    if expiry_date is None:
        return

    if service is None:
        raise ValidationError({
            "expiry_date": (
                "Link this record to a government service before adding "
                "an expiry date."
            )
        })

    if not service.expiry_tracking_available:
        raise ValidationError({
            "expiry_date": (
                "Expiry dates are not enabled for this government service."
            )
        })


@transaction.atomic
def create_license_record(
    *,
    actor,
    business_id,
    license_type,
    issuing_authority="",
    identifier="",
    issue_date=None,
    expiry_date=None,
    government_service_id=None,
    pathway_step_id=None,
):
    """Create an unverified license record for a business the actor owns."""

    business = _owned_business(actor, business_id)

    service = None
    if government_service_id is not None:
        service = GovernmentService.objects.filter(
            pk=government_service_id
        ).first()
        if service is None:
            raise ValidationError({
                "government_service_id": "Select a valid government service."
            })

    pathway_step = None
    if pathway_step_id is not None:
        pathway_step = (
            PathwayStep.objects
            .select_related(
                "service",
                "version__pathway__business_profile__business",
            )
            .filter(pk=pathway_step_id)
            .first()
        )
        if pathway_step is None:
            raise ValidationError({
                "pathway_step_id": "Select a valid pathway step."
            })

        step_business_id = (
            pathway_step.version.pathway.business_profile.business_id
        )
        if step_business_id != business.pk:
            raise PermissionDenied(
                "The pathway step does not belong to this business."
            )

        if service is not None and service.pk != pathway_step.service_id:
            raise ValidationError({
                "government_service_id": (
                    "The selected service does not match the pathway step."
                )
            })

        service = pathway_step.service

    _validate_dates(issue_date, expiry_date)
    _validate_expiry_tracking(service, expiry_date)

    record = LicenseRecord(
        business=business,
        government_service=service,
        pathway_step=pathway_step,
        license_type=license_type.strip(),
        issuing_authority=issuing_authority.strip(),
        identifier=identifier.strip(),
        issue_date=issue_date,
        expiry_date=expiry_date,
        created_by=actor,
    )
    record.full_clean()
    record.save()
    sync_license_renewal_event(record)
    return record


def list_license_records(*, actor, business_id):
    """List license records for a business the actor owns."""

    business = _owned_business(actor, business_id)
    return (
        LicenseRecord.objects
        .filter(business=business)
        .select_related(
            "government_service",
            "pathway_step__version",
        )
        .order_by("expiry_date", "id")
    )


def serialize_license_record_data(record, *, today=None):
    """Serialize one record consistently for license API responses."""
    today = today or timezone.localdate()
    soon_cutoff = today + timedelta(days=30)
    if record.expiry_date is None:
        expiry_status = "DATE_NOT_PROVIDED"
    elif record.expiry_date < today:
        expiry_status = "EXPIRED"
    elif record.expiry_date <= soon_cutoff:
        expiry_status = "EXPIRING_WITHIN_30_DAYS"
    else:
        expiry_status = "VALID_BEYOND_30_DAYS"

    service = record.government_service
    step = record.pathway_step
    return {
        "id": record.pk,
        "license_type": record.license_type,
        "issuing_authority": record.issuing_authority,
        "identifier": record.identifier,
        "issue_date": (
            record.issue_date.isoformat() if record.issue_date else None
        ),
        "expiry_date": (
            record.expiry_date.isoformat() if record.expiry_date else None
        ),
        "expiry_status": expiry_status,
        "verification_status": record.verification_status,
        "government_service": (
            {
                "code": service.code,
                "name_en": service.name_en,
                "official_url": service.official_url,
            }
            if service is not None
            else None
        ),
        "pathway_step": (
            {
                "id": step.pk,
                "version": step.version.version_number,
                "service_code": step.service_code_snapshot,
                "service_name_en": step.service_name_en_snapshot,
                "order": step.order,
                "status": step.status,
            }
            if step is not None
            else None
        ),
        "updated_at": record.updated_at.isoformat(),
    }


def list_license_record_data(*, actor, business_id, today=None):
    """Return dashboard-ready metadata for an owner's license records."""
    today = today or timezone.localdate()
    records = list_license_records(actor=actor, business_id=business_id)
    return {
        "as_of": today.isoformat(),
        "licenses": [
            serialize_license_record_data(record, today=today)
            for record in records
        ],
    }


@transaction.atomic
def update_license_record(
    *,
    actor,
    license_record_id,
    license_type=_UNSET,
    issuing_authority=_UNSET,
    identifier=_UNSET,
    issue_date=_UNSET,
    expiry_date=_UNSET,
):
    """Update an owned record without allowing ownership or verification changes."""

    record = _owned_license_record(actor, license_record_id)

    if license_type is not _UNSET:
        record.license_type = license_type.strip()
    if issuing_authority is not _UNSET:
        record.issuing_authority = issuing_authority.strip()
    if identifier is not _UNSET:
        record.identifier = identifier.strip()
    if issue_date is not _UNSET:
        record.issue_date = issue_date
    if expiry_date is not _UNSET:
        record.expiry_date = expiry_date

    service = record.government_service
    if service is None and record.pathway_step_id:
        service = record.pathway_step.service

    _validate_dates(record.issue_date, record.expiry_date)
    if expiry_date is not _UNSET:
        _validate_expiry_tracking(service, record.expiry_date)

    record.full_clean()
    record.save()
    sync_license_renewal_event(record)
    return record
