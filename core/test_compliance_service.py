from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models import (
    Authority,
    Business,
    BusinessProfile,
    ComplianceEvent,
    GovernmentService,
)
from core.Services.compliance_service import (
    complete_compliance_event,
    sync_license_renewal_event,
)
from core.Services.license_service import (
    create_license_record,
    update_license_record,
)


class ComplianceEventServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="compliance_owner")
        self.other_user = User.objects.create_user(username="compliance_other")
        self.business = Business.objects.create(
            user=self.owner,
            business_name="Compliance test business",
        )
        BusinessProfile.objects.create(
            business=self.business,
            applicant_type="INDIVIDUAL",
            business_structure="NEW",
            operating_model="PHYSICAL",
        )

        authority = Authority.objects.create(
            code="COMPLIANCE_TEST",
            name_en="Compliance Test Authority",
            name_ar="جهة اختبار الامتثال",
        )
        self.service = GovernmentService.objects.create(
            code="COMPLIANCE_TEST_SERVICE",
            name_en="Expiry-enabled service",
            name_ar="خدمة ذات تاريخ انتهاء",
            authority=authority,
            expiry_tracking_available=True,
        )

    def _create_license(self, expiry_date=date(2027, 1, 1)):
        return create_license_record(
            actor=self.owner,
            business_id=self.business.pk,
            license_type="Test license",
            government_service_id=self.service.pk,
            expiry_date=expiry_date,
        )

    def test_license_with_expiry_creates_open_renewal_event(self):
        license_record = self._create_license()

        event = ComplianceEvent.objects.get(
            license_record=license_record,
            event_type=ComplianceEvent.EventType.RENEWAL,
        )
        self.assertEqual(event.business_id, self.business.pk)
        self.assertEqual(event.due_date, date(2027, 1, 1))
        self.assertEqual(event.status, ComplianceEvent.Status.OPEN)

    def test_license_without_expiry_creates_no_renewal_event(self):
        self._create_license(expiry_date=None)

        self.assertFalse(ComplianceEvent.objects.exists())

    def test_syncing_same_expiry_is_idempotent(self):
        license_record = self._create_license()

        sync_license_renewal_event(license_record)
        sync_license_renewal_event(license_record)

        self.assertEqual(
            ComplianceEvent.objects.filter(
                license_record=license_record,
                event_type=ComplianceEvent.EventType.RENEWAL,
                due_date=date(2027, 1, 1),
            ).count(),
            1,
        )

    def test_expiry_change_cancels_old_event_and_creates_new_one(self):
        license_record = self._create_license()
        old_event = ComplianceEvent.objects.get(
            license_record=license_record
        )

        update_license_record(
            actor=self.owner,
            license_record_id=license_record.pk,
            expiry_date=date(2028, 1, 1),
        )

        old_event.refresh_from_db()
        new_event = ComplianceEvent.objects.get(
            license_record=license_record,
            due_date=date(2028, 1, 1),
        )
        self.assertEqual(old_event.status, ComplianceEvent.Status.CANCELLED)
        self.assertEqual(new_event.status, ComplianceEvent.Status.OPEN)

    def test_removing_expiry_cancels_open_event_without_deleting_it(self):
        license_record = self._create_license()
        event = ComplianceEvent.objects.get(license_record=license_record)

        update_license_record(
            actor=self.owner,
            license_record_id=license_record.pk,
            expiry_date=None,
        )

        event.refresh_from_db()
        self.assertEqual(event.status, ComplianceEvent.Status.CANCELLED)
        self.assertTrue(
            ComplianceEvent.objects.filter(pk=event.pk).exists()
        )

    def test_owner_can_complete_event_and_repeat_is_idempotent(self):
        license_record = self._create_license()
        event = ComplianceEvent.objects.get(license_record=license_record)

        completed = complete_compliance_event(
            actor=self.owner,
            event_id=event.pk,
        )
        completed_at = completed.completed_at
        repeated = complete_compliance_event(
            actor=self.owner,
            event_id=event.pk,
        )

        self.assertEqual(repeated.status, ComplianceEvent.Status.COMPLETED)
        self.assertEqual(repeated.completed_by, self.owner)
        self.assertEqual(repeated.completed_at, completed_at)

    def test_non_owner_cannot_complete_event(self):
        license_record = self._create_license()
        event = ComplianceEvent.objects.get(license_record=license_record)

        with self.assertRaises(PermissionDenied):
            complete_compliance_event(
                actor=self.other_user,
                event_id=event.pk,
            )

    def test_cancelled_event_cannot_be_completed(self):
        license_record = self._create_license()
        event = ComplianceEvent.objects.get(license_record=license_record)
        event.status = ComplianceEvent.Status.CANCELLED
        event.save(update_fields=["status", "updated_at"])

        with self.assertRaises(ValidationError):
            complete_compliance_event(
                actor=self.owner,
                event_id=event.pk,
            )
