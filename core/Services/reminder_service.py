from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.Services.compliance_service import sync_business_reminder_schedule
from core.models import Business, UserEmailVerification


@transaction.atomic
def set_email_reminder_preference(*, actor, business_id, enabled):
    """Set the authenticated owner's email reminder preference."""
    if not isinstance(enabled, bool):
        raise ValidationError({"enabled": "A true or false value is required."})
    business = (
        Business.objects
        .select_for_update()
        .filter(pk=business_id, user=actor)
        .first()
    )
    if business is None:
        raise PermissionDenied(
            "You cannot change reminder preferences for this business."
        )

    if enabled:
        email = getattr(actor, "email", "").strip()
        if not email:
            raise ValidationError({
                "email": "Add an email address to your account before opting in."
            })
        verified = UserEmailVerification.objects.filter(
            user=actor,
            email=email,
            verified_at__isnull=False,
        ).exists()
        if not verified:
            raise ValidationError({
                "email": "Verify your account email before opting in."
            })

    if business.email_reminders_enabled != enabled:
        business.email_reminders_enabled = enabled
        business.save(update_fields=["email_reminders_enabled", "updated_at"])
        sync_business_reminder_schedule(business)

    return business
