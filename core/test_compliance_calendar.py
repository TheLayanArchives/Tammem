from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from core.models import Business, ComplianceEvent, LicenseRecord, Reminder
from core.Services.compliance_service import get_business_compliance_calendar


class BusinessComplianceCalendarTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="calendar_owner")
        self.other_user = User.objects.create_user(username="calendar_other")
        self.business = Business.objects.create(
            user=self.owner,
            business_name="Calendar test business",
        )
        self.today = timezone.localdate()

    def _event(self, *, due_date, status=ComplianceEvent.Status.OPEN):
        return ComplianceEvent.objects.create(
            business=self.business,
            event_type=ComplianceEvent.EventType.RENEWAL,
            due_date=due_date,
            status=status,
            completed_at=(
                timezone.now()
                if status == ComplianceEvent.Status.COMPLETED
                else None
            ),
        )

    def test_calendar_classifies_upcoming_overdue_completed_and_cancelled(self):
        upcoming = self._event(due_date=self.today)
        overdue = self._event(due_date=self.today - timedelta(days=1))
        completed = self._event(
            due_date=self.today - timedelta(days=2),
            status=ComplianceEvent.Status.COMPLETED,
        )
        cancelled = self._event(
            due_date=self.today + timedelta(days=2),
            status=ComplianceEvent.Status.CANCELLED,
        )

        result = get_business_compliance_calendar(
            actor=self.owner,
            business_id=self.business.pk,
            today=self.today,
        )

        statuses = {
            event["id"]: event["calendar_status"]
            for event in result["events"]
        }
        self.assertEqual(statuses[upcoming.pk], "UPCOMING")
        self.assertEqual(statuses[overdue.pk], "OVERDUE")
        self.assertEqual(statuses[completed.pk], "COMPLETED")
        self.assertEqual(statuses[cancelled.pk], "CANCELLED")
        self.assertEqual(result["as_of"], self.today.isoformat())

    def test_calendar_includes_license_and_reminder_details(self):
        event = self._event(due_date=self.today + timedelta(days=14))
        license_record = LicenseRecord.objects.create(
            business=self.business,
            license_type="Café permit",
            expiry_date=event.due_date,
        )
        event.license_record = license_record
        event.save(update_fields=["license_record", "updated_at"])
        reminder = Reminder.objects.create(
            business=self.business,
            compliance_event=event,
            lead_days=14,
            channel=Reminder.Channel.IN_APP,
            scheduled_for=self.today,
        )

        result = get_business_compliance_calendar(
            actor=self.owner,
            business_id=self.business.pk,
            today=self.today,
        )
        item = result["events"][0]

        self.assertEqual(item["license"]["id"], license_record.pk)
        self.assertEqual(
            item["license"]["verification_status"],
            LicenseRecord.VerificationStatus.USER_PROVIDED_UNVERIFIED,
        )
        self.assertEqual(item["reminders"][0]["id"], reminder.pk)
        self.assertEqual(item["reminders"][0]["channel"], "IN_APP")

    def test_calendar_is_owner_scoped(self):
        with self.assertRaises(PermissionDenied):
            get_business_compliance_calendar(
                actor=self.other_user,
                business_id=self.business.pk,
                today=self.today,
            )

        self.client.force_login(self.other_user)
        response = self.client.get(
            f"/api/businesses/{self.business.pk}/compliance-events/"
        )
        self.assertEqual(response.status_code, 404)

    def test_calendar_endpoint_requires_authentication(self):
        response = self.client.get(
            f"/api/businesses/{self.business.pk}/compliance-events/"
        )
        self.assertEqual(response.status_code, 401)
