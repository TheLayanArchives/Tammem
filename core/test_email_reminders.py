from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from core.Services.compliance_service import send_due_email_reminders
from core.models import (
    Business,
    ComplianceEvent,
    Reminder,
    UserEmailVerification,
)


class EmailReminderDeliveryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="email_reminder_owner",
            email="owner@example.test",
        )
        self.business = Business.objects.create(
            user=self.owner,
            business_name="Email reminder test business",
            email_reminders_enabled=True,
        )
        UserEmailVerification.objects.create(
            user=self.owner,
            email=self.owner.email,
            verified_at=timezone.now(),
        )
        self.event = ComplianceEvent.objects.create(
            business=self.business,
            event_type=ComplianceEvent.EventType.RENEWAL,
            due_date=timezone.localdate() + timedelta(days=7),
        )
        self.reminder = Reminder.objects.create(
            business=self.business,
            compliance_event=self.event,
            lead_days=7,
            channel=Reminder.Channel.EMAIL,
            scheduled_for=timezone.localdate(),
        )

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        }
    )
    def test_due_opted_in_reminder_sends_and_is_marked_sent(self):
        result = send_due_email_reminders()

        self.reminder.refresh_from_db()
        self.assertEqual(result, {"sent": 1, "failed": 0, "skipped": 0})
        self.assertEqual(
            self.reminder.delivery_status,
            Reminder.DeliveryStatus.SENT,
        )
        self.assertIsNotNone(self.reminder.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@example.test"])

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        }
    )
    def test_opted_out_business_is_not_sent_email(self):
        self.business.email_reminders_enabled = False
        self.business.save(update_fields=["email_reminders_enabled"])

        result = send_due_email_reminders()

        self.assertEqual(result, {"sent": 0, "failed": 0, "skipped": 0})
        self.assertEqual(len(mail.outbox), 0)
        self.reminder.refresh_from_db()
        self.assertEqual(
            self.reminder.delivery_status,
            Reminder.DeliveryStatus.PENDING,
        )
