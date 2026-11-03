from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.utils import timezone

from core.models import (
    Business,
    BusinessProfile,
    LicenseRecord,
    Pathway,
)
from core.Services.pathway_persistence import get_pathway_summary


def get_business_monitoring_summary(*, actor, business_id, today=None):
    """Build an owner-scoped overview from saved pathway and license data."""
    business = Business.objects.filter(
        pk=business_id,
        user=actor,
    ).first()
    if business is None:
        raise PermissionDenied("You cannot access this business.")

    today = today or timezone.localdate()
    soon_cutoff = today + timedelta(days=30)

    profile = (
        BusinessProfile.objects
        .select_related("activity", "location")
        .filter(business=business)
        .first()
    )

    activity = None
    location = None
    pathway_summary = None
    if profile is not None:
        if profile.activity_id:
            activity = {
                "code": profile.activity.code,
                "name_en": profile.activity.name_en,
            }
        if profile.location_id:
            location = {
                "city": profile.location.city_name_en,
                "region": profile.location.region_name_en,
            }

        pathway = (
            Pathway.objects
            .select_related("current_version")
            .filter(business_profile=profile)
            .first()
        )
        if pathway is not None:
            saved_summary = get_pathway_summary(pathway)
            pathway_summary = {
                "status": pathway.status,
                "current_version": saved_summary["version"],
                "required_steps_total": saved_summary["required_total"],
                "required_steps_completed": saved_summary["required_done"],
                "progress_percent": saved_summary["progress_percent"],
            }

    license_counts = LicenseRecord.objects.filter(
        business=business,
    ).aggregate(
        total=Count("id"),
        expired=Count("id", filter=Q(expiry_date__lt=today)),
        expiring_within_30_days=Count(
            "id",
            filter=Q(expiry_date__gte=today, expiry_date__lte=soon_cutoff),
        ),
        valid_beyond_30_days=Count("id", filter=Q(expiry_date__gt=soon_cutoff)),
        expiry_date_not_provided=Count("id", filter=Q(expiry_date__isnull=True)),
        user_provided_unverified=Count(
            "id",
            filter=Q(
                verification_status=(
                    LicenseRecord.VerificationStatus.USER_PROVIDED_UNVERIFIED
                )
            ),
        ),
    )

    return {
        "as_of": today.isoformat(),
        "business": {
            "id": business.pk,
            "name": business.business_name,
            "status": business.status,
            "activity": activity,
            "location": location,
        },
        "pathway": pathway_summary,
        "licenses": license_counts,
    }
