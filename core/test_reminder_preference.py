from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Business,
    ComplianceEvent,
    Reminder,
    UserEmailVerification,
)
from core.Services.reminder_service import set_email_reminder_preference


class EmailReminderPreferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="preference_owner",
            email="owner@example.test",
        )
        self.other_user = User.objects.create_user(
            username="preference_other",
            email="other@example.test",
        )
        self.business = Business.objects.create(
            user=self.owner,
            business_name="Preference test business",
        )
        UserEmailVerification.objects.create(
            user=self.owner,
            email=self.owner.email,
            verified_at=timezone.now(),
        )

    def test_email_reminders_are_off_by_default(self):
        self.assertFalse(self.business.email_reminders_enabled)

    def test_owner_can_enable_and_disable_email_reminders(self):
        event = ComplianceEvent.objects.create(
            business=self.business,
            event_type=ComplianceEvent.EventType.RENEWAL,
            due_date=timezone.localdate() + timedelta(days=90),
        )
        enabled = set_email_reminder_preference(
            actor=self.owner,
            business_id=self.business.pk,
            enabled=True,
        )
        self.assertTrue(enabled.email_reminders_enabled)
        self.assertEqual(
            Reminder.objects.filter(
                compliance_event=event,
                channel=Reminder.Channel.EMAIL,
                delivery_status=Reminder.DeliveryStatus.PENDING,
            ).count(),
            3,
        )

        disabled = set_email_reminder_preference(
            actor=self.owner,
            business_id=self.business.pk,
            enabled=False,
        )
        self.assertFalse(disabled.email_reminders_enabled)
        self.assertEqual(
            Reminder.objects.filter(
                compliance_event=event,
                channel=Reminder.Channel.EMAIL,
                delivery_status=Reminder.DeliveryStatus.CANCELLED,
            ).count(),
            3,
        )

    def test_other_user_cannot_change_preference(self):
        with self.assertRaises(PermissionDenied):
            set_email_reminder_preference(
                actor=self.other_user,
                business_id=self.business.pk,
                enabled=True,
            )

    def test_preference_requires_a_boolean(self):
        with self.assertRaises(ValidationError):
            set_email_reminder_preference(
                actor=self.owner,
                business_id=self.business.pk,
                enabled="true",
            )

    def test_user_needs_an_email_address_to_opt_in(self):
        User = get_user_model()
        user_without_email = User.objects.create_user(
            username="preference_no_email",
        )
        business_without_email = Business.objects.create(
            user=user_without_email,
            business_name="No email preference business",
        )
        with self.assertRaises(ValidationError):
            set_email_reminder_preference(
                actor=user_without_email,
                business_id=business_without_email.pk,
                enabled=True,
            )

    def test_preference_endpoint_reads_and_updates_owner_business(self):
        self.client.force_login(self.owner)
        url = f"/api/businesses/{self.business.pk}/reminder-preference/"

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["email_reminders_enabled"])

        response = self.client.patch(
            url,
            data='{"email_reminders_enabled": true}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["email_reminders_enabled"])

    def test_preference_endpoint_rejects_invalid_payload_and_other_owner(self):
        self.client.force_login(self.other_user)
        url = f"/api/businesses/{self.business.pk}/reminder-preference/"

        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        response = self.client.patch(
            url,
            data='{"email_reminders_enabled": "yes"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_preference_endpoint_requires_authentication(self):
        response = self.client.get(
            f"/api/businesses/{self.business.pk}/reminder-preference/"
        )
        self.assertEqual(response.status_code, 401)
