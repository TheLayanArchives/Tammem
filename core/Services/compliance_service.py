from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from core.models import (
    Business,
    ComplianceEvent,
    Reminder,
    UserEmailVerification,
)


def get_business_compliance_calendar(*, actor, business_id, today=None):
    """Return calendar events for a business owned by the actor."""
    business_exists = Business.objects.filter(
        pk=business_id,
        user=actor,
    ).exists()
    if not business_exists:
        raise PermissionDenied("You cannot access this business.")

    today = today or timezone.localdate()
    events = (
        ComplianceEvent.objects
        .filter(business_id=business_id)
        .select_related(
            "license_record",
            "license_record__government_service",
        )
        .prefetch_related("reminders")
        .order_by("due_date", "id")
    )

    results = []
    for event in events:
        if event.status == ComplianceEvent.Status.COMPLETED:
            calendar_status = "COMPLETED"
        elif event.status == ComplianceEvent.Status.CANCELLED:
            calendar_status = "CANCELLED"
        elif event.due_date < today:
            calendar_status = "OVERDUE"
        else:
            calendar_status = "UPCOMING"

        license_record = event.license_record
        service = (
            license_record.government_service
            if license_record is not None
            else None
        )
        results.append({
            "id": event.pk,
            "event_type": event.event_type,
            "status": event.status,
            "calendar_status": calendar_status,
            "due_date": event.due_date.isoformat(),
            "completed_at": (
                event.completed_at.isoformat()
                if event.completed_at
                else None
            ),
            "license": (
                {
                    "id": license_record.pk,
                    "type": license_record.license_type,
                    "expiry_date": (
                        license_record.expiry_date.isoformat()
                        if license_record.expiry_date
                        else None
                    ),
                    "verification_status": license_record.verification_status,
                    "service_code": service.code if service else None,
                    "service_name_en": service.name_en if service else None,
                }
                if license_record is not None
                else None
            ),
            "reminders": [
                {
                    "id": reminder.pk,
                    "channel": reminder.channel,
                    "scheduled_for": reminder.scheduled_for.isoformat(),
                    "delivery_status": reminder.delivery_status,
                    "sent_at": (
                        reminder.sent_at.isoformat()
                        if reminder.sent_at
                        else None
                    ),
                }
                for reminder in event.reminders.all()
            ],
        })

    return {"as_of": today.isoformat(), "events": results}


def _sync_event_reminders(event):
    """Maintain pending in-app reminders for an open event."""
    reminders = Reminder.objects.filter(compliance_event=event)
    now = timezone.now()

    if event.status != ComplianceEvent.Status.OPEN:
        reminders.filter(
            delivery_status__in=[
                Reminder.DeliveryStatus.PENDING,
                Reminder.DeliveryStatus.AVAILABLE,
            ],
        ).update(
            delivery_status=Reminder.DeliveryStatus.CANCELLED,
            updated_at=now,
        )
        return

    configured_days = getattr(
        settings, "COMPLIANCE_REMINDER_LEAD_DAYS", [30, 14, 7]
    )
    lead_days = set()
    for value in configured_days:
        try:
            days = int(value)
        except (TypeError, ValueError):
            continue
        if days > 0:
            lead_days.add(days)

    today = timezone.localdate()
    scheduled_leads = set()
    channels = [Reminder.Channel.IN_APP]
    if event.business.email_reminders_enabled:
        channels.append(Reminder.Channel.EMAIL)

    for days in lead_days:
        scheduled_for = event.due_date - timedelta(days=days)
        if scheduled_for < today:
            continue

        scheduled_leads.add(days)
        for channel in channels:
            reminder, created = Reminder.objects.get_or_create(
                compliance_event=event,
                lead_days=days,
                channel=channel,
                defaults={
                    "business": event.business,
                    "scheduled_for": scheduled_for,
                    "delivery_status": Reminder.DeliveryStatus.PENDING,
                },
            )
            if (
                not created
                and reminder.delivery_status == Reminder.DeliveryStatus.CANCELLED
            ):
                reminder.business = event.business
                reminder.scheduled_for = scheduled_for
                reminder.delivery_status = Reminder.DeliveryStatus.PENDING
                reminder.sent_at = None
                reminder.save(update_fields=[
                    "business", "scheduled_for", "delivery_status", "sent_at",
                    "updated_at",
                ])

    for channel in [Reminder.Channel.IN_APP, Reminder.Channel.EMAIL]:
        if channel in channels:
            reminders.filter(
                channel=channel,
                delivery_status=Reminder.DeliveryStatus.PENDING,
            ).exclude(
                lead_days__in=scheduled_leads,
            ).update(
                delivery_status=Reminder.DeliveryStatus.CANCELLED,
                updated_at=now,
            )
        else:
            reminders.filter(
                channel=channel,
                delivery_status=Reminder.DeliveryStatus.PENDING,
            ).update(
                delivery_status=Reminder.DeliveryStatus.CANCELLED,
                updated_at=now,
            )


@transaction.atomic
def sync_business_reminder_schedule(business):
    """Resync reminders when a business changes its email opt-in."""
    events = business.compliance_events.filter(
        status=ComplianceEvent.Status.OPEN,
    )
    for event in events:
        _sync_event_reminders(event)


@transaction.atomic
def process_due_reminders(*, today=None):
    """Make due in-app reminders available for the dashboard to display."""
    today = today or timezone.localdate()
    now = timezone.now()
    return Reminder.objects.filter(
        channel=Reminder.Channel.IN_APP,
        delivery_status=Reminder.DeliveryStatus.PENDING,
        scheduled_for__lte=today,
        compliance_event__status=ComplianceEvent.Status.OPEN,
    ).update(
        delivery_status=Reminder.DeliveryStatus.AVAILABLE,
        updated_at=now,
    )


def send_due_email_reminders(*, today=None):
    """Send opted-in due email reminders using Django's configured backend."""
    today = today or timezone.localdate()
    reminder_ids = list(
        Reminder.objects.filter(
            channel=Reminder.Channel.EMAIL,
            delivery_status=Reminder.DeliveryStatus.PENDING,
            scheduled_for__lte=today,
            compliance_event__status=ComplianceEvent.Status.OPEN,
            business__email_reminders_enabled=True,
        )
        .order_by("scheduled_for", "id")
        .values_list("pk", flat=True)
    )

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    for reminder_id in reminder_ids:
        with transaction.atomic():
            reminder = (
                Reminder.objects.select_for_update(of=("self",))
                .select_related(
                    "business",
                    "business__user",
                    "compliance_event",
                    "compliance_event__license_record",
                    "compliance_event__license_record__government_service",
                )
                .filter(pk=reminder_id)
                .first()
            )
            if (
                reminder is None
                or reminder.delivery_status != Reminder.DeliveryStatus.PENDING
                or reminder.compliance_event.status != ComplianceEvent.Status.OPEN
                or not reminder.business.email_reminders_enabled
            ):
                continue

            recipient = reminder.business.user.email.strip()
            if not recipient:
                skipped_count += 1
                continue

            verified = UserEmailVerification.objects.filter(
                user=reminder.business.user,
                email=recipient,
                verified_at__isnull=False,
            ).exists()
            if not verified:
                skipped_count += 1
                continue

            license_record = reminder.compliance_event.license_record
            service = (
                license_record.government_service
                if license_record is not None
                else None
            )
            license_name = (
                license_record.license_type
                if license_record is not None
                else "License or permit"
            )
            if service is not None:
                license_name = service.name_en

            subject = f"Reminder: {license_name} renewal"
            message = (
                f"This is a reminder for {reminder.business.business_name}.\n\n"
                f"{license_name} is due on "
                f"{reminder.compliance_event.due_date.isoformat()}.\n"
                f"This reminder was scheduled {reminder.lead_days} days "
                "before the due date.\n\n"
                "This is an automated reminder based on the date you provided."
            )
            try:
                delivered = send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
            except Exception:
                delivered = 0

            if delivered:
                reminder.delivery_status = Reminder.DeliveryStatus.SENT
                reminder.sent_at = timezone.now()
                sent_count += 1
                reminder.save(update_fields=[
                    "delivery_status", "sent_at", "updated_at",
                ])
            else:
                reminder.delivery_status = Reminder.DeliveryStatus.FAILED
                failed_count += 1
                reminder.save(update_fields=["delivery_status", "updated_at"])

    return {
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }


@transaction.atomic
def sync_license_renewal_event(license_record):
    """Keep one renewal event aligned with a license record's expiry date."""

    events = ComplianceEvent.objects.filter(
        license_record=license_record,
        event_type=ComplianceEvent.EventType.RENEWAL,
    )

    if license_record.expiry_date is None:
        for event in events.filter(status=ComplianceEvent.Status.OPEN):
            event.status = ComplianceEvent.Status.CANCELLED
            event.save(update_fields=["status", "updated_at"])
            _sync_event_reminders(event)
        return None

    for event in events.filter(
        status=ComplianceEvent.Status.OPEN,
    ).exclude(
        due_date=license_record.expiry_date,
    ):
        event.status = ComplianceEvent.Status.CANCELLED
        event.save(update_fields=["status", "updated_at"])
        _sync_event_reminders(event)

    event, _ = ComplianceEvent.objects.get_or_create(
        license_record=license_record,
        event_type=ComplianceEvent.EventType.RENEWAL,
        due_date=license_record.expiry_date,
        defaults={
            "business": license_record.business,
            "status": ComplianceEvent.Status.OPEN,
        },
    )

    if event.status == ComplianceEvent.Status.CANCELLED:
        event.status = ComplianceEvent.Status.OPEN
        event.completed_at = None
        event.completed_by = None
        event.save(update_fields=[
            "status",
            "completed_at",
            "completed_by",
            "updated_at",
        ])

    _sync_event_reminders(event)
    return event


@transaction.atomic
def complete_compliance_event(*, actor, event_id):
    """Record an owner's confirmation that a renewal task is complete."""

    event = (
        ComplianceEvent.objects
        .select_for_update()
        .filter(
            pk=event_id,
            business__user=actor,
        )
        .first()
    )

    if event is None:
        raise PermissionDenied(
            "You cannot access this compliance event."
        )

    if event.status == ComplianceEvent.Status.CANCELLED:
        raise ValidationError(
            "A cancelled compliance event cannot be completed."
        )

    if event.status != ComplianceEvent.Status.COMPLETED:
        event.status = ComplianceEvent.Status.COMPLETED
        event.completed_at = timezone.now()
        event.completed_by = actor
        event.save(update_fields=[
            "status",
            "completed_at",
            "completed_by",
            "updated_at",
        ])
        _sync_event_reminders(event)

    return event
