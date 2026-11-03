from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.Services.compliance_service import process_due_reminders
from core.models import Business, ComplianceEvent, Reminder


class DueReminderProcessingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="reminder_owner")
        self.other_user = User.objects.create_user(username="reminder_other")
        self.business = Business.objects.create(
            user=self.owner,
            business_name="Reminder test business",
        )
        self.event = ComplianceEvent.objects.create(
            business=self.business,
            event_type=ComplianceEvent.EventType.RENEWAL,
            due_date=timezone.localdate() + timedelta(days=7),
        )

    def _make_reminder(self, *, scheduled_for, lead_days=7):
        return Reminder.objects.create(
            business=self.business,
            compliance_event=self.event,
            lead_days=lead_days,
            scheduled_for=scheduled_for,
        )

    def test_processing_marks_only_due_open_reminders_available(self):
        today = timezone.localdate()
        due = self._make_reminder(scheduled_for=today)
        future = self._make_reminder(
            scheduled_for=today + timedelta(days=1),
            lead_days=14,
        )

        count = process_due_reminders(today=today)

        self.assertEqual(count, 1)
        due.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(
            due.delivery_status,
            Reminder.DeliveryStatus.AVAILABLE,
        )
        self.assertEqual(
            future.delivery_status,
            Reminder.DeliveryStatus.PENDING,
        )
        self.assertEqual(process_due_reminders(today=today), 0)

    def test_dashboard_returns_due_reminders_only_to_their_owner(self):
        reminder = self._make_reminder(
            scheduled_for=timezone.localdate(),
        )
        self.client.force_login(self.owner)

        response = self.client.get("/api/dashboard/reminders/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["reminders"]],
            [reminder.pk],
        )

        self.client.force_login(self.other_user)
        response = self.client.get("/api/dashboard/reminders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reminders": []})

    def test_dashboard_requires_authentication(self):
        response = self.client.get("/api/dashboard/reminders/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication required."},
        )
