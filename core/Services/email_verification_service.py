import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from core.Services.compliance_service import sync_business_reminder_schedule
from core.models import Business, UserEmailVerification


@transaction.atomic
def request_email_verification(*, user, confirmation_url):
    """Email a short-lived, single-use verification link to the account email."""
    email = getattr(user, "email", "").strip()
    if not email:
        raise ValidationError({"email": "Add an email address to your account."})

    verification, _ = UserEmailVerification.objects.select_for_update().get_or_create(
        user=user,
        defaults={"email": email},
    )
    if verification.email == email and verification.verified_at is not None:
        return False

    raw_token = secrets.token_urlsafe(32)
    verification.email = email
    verification.token_digest = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()
    verification.expires_at = timezone.now() + timedelta(
        seconds=settings.EMAIL_VERIFICATION_TOKEN_MAX_AGE
    )
    verification.verified_at = None
    verification.save(update_fields=[
        "email", "token_digest", "expires_at", "verified_at", "updated_at",
    ])

    delivered = send_mail(
        subject="Verify your TAMMEM email address",
        message=(
            "Use this link to verify your TAMMEM account email. "
            "The link expires in one hour and can only be used once:\n\n"
            f"{confirmation_url}?token={raw_token}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    if not delivered:
        raise ValidationError({"email": "The verification email could not be sent."})

    return True


@transaction.atomic
def confirm_email_verification(*, token):
    """Verify the current account email using an unexpired one-time token."""
    if not token:
        raise ValidationError({"token": "A verification token is required."})

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    verification = (
        UserEmailVerification.objects
        .select_for_update()
        .select_related("user")
        .filter(
            token_digest=digest,
            verified_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if verification is None:
        raise ValidationError({"token": "This verification link is invalid or expired."})

    if verification.email != verification.user.email.strip():
        raise ValidationError({"token": "This link is for an outdated email address."})

    verification.verified_at = timezone.now()
    verification.token_digest = ""
    verification.expires_at = None
    verification.save(update_fields=[
        "verified_at", "token_digest", "expires_at", "updated_at",
    ])

    for business in Business.objects.filter(
        user=verification.user,
        email_reminders_enabled=True,
    ):
        sync_business_reminder_schedule(business)

    return verification
