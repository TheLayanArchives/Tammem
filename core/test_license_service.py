from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models import (
    Authority,
    Business,
    BusinessProfile,
    GovernmentService,
    LicenseRecord,
    Pathway,
    PathwayStep,
    PathwayVersion,
)
from core.Services.license_service import (
    create_license_record,
    list_license_records,
    update_license_record,
)


class LicenseRecordServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="license_owner")
        self.other_user = User.objects.create_user(username="other_owner")

        self.business = self._create_business(self.owner, "Owner business")
        self.other_business = self._create_business(
            self.other_user, "Other business"
        )

        authority = Authority.objects.create(
            code="LICENSE_TEST",
            name_en="Test Authority",
            name_ar="جهة اختبار",
        )
        self.expiring_service = GovernmentService.objects.create(
            code="EXPIRING_TEST",
            name_en="Expiring service",
            name_ar="خدمة تنتهي",
            authority=authority,
            expiry_tracking_available=True,
        )
        self.non_expiring_service = GovernmentService.objects.create(
            code="NON_EXPIRING_TEST",
            name_en="Non-expiring service",
            name_ar="خدمة بدون انتهاء",
            authority=authority,
            expiry_tracking_available=False,
        )

    def _create_business(self, user, name):
        business = Business.objects.create(
            user=user,
            business_name=name,
        )
        BusinessProfile.objects.create(
            business=business,
            applicant_type="INDIVIDUAL",
            business_structure="NEW",
            operating_model="PHYSICAL",
        )
        return business

    def _create_pathway_step(self, business, service):
        pathway = Pathway.objects.create(
            business_profile=business.profile,
        )
        version = PathwayVersion.objects.create(
            pathway=pathway,
            version_number=1,
            profile_version=1,
            reason=PathwayVersion.Reason.INITIAL,
            generation_snapshot={},
            generation_hash="a" * 64,
        )
        pathway.current_version = version
        pathway.save(update_fields=["current_version", "updated_at"])

        return PathwayStep.objects.create(
            version=version,
            service=service,
            order=1,
            mandatory_status="REQUIRED",
            step_type="SERVICE",
            service_code_snapshot=service.code,
            service_name_ar_snapshot=service.name_ar,
            service_name_en_snapshot=service.name_en,
        )

    def test_create_records_owner_and_unverified_status(self):
        record = create_license_record(
            actor=self.owner,
            business_id=self.business.pk,
            license_type="Municipal license",
            government_service_id=self.expiring_service.pk,
            issue_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1),
        )

        self.assertEqual(record.business_id, self.business.pk)
        self.assertEqual(record.created_by, self.owner)
        self.assertEqual(
            record.verification_status,
            LicenseRecord.VerificationStatus.USER_PROVIDED_UNVERIFIED,
        )

    def test_expiry_date_is_optional_for_an_eligible_service(self):
        record = create_license_record(
            actor=self.owner,
            business_id=self.business.pk,
            license_type="Municipal license",
            government_service_id=self.expiring_service.pk,
        )

        self.assertIsNone(record.expiry_date)

    def test_expiry_date_is_rejected_for_unlisted_service(self):
        with self.assertRaises(ValidationError):
            create_license_record(
                actor=self.owner,
                business_id=self.business.pk,
                license_type="Registration",
                government_service_id=self.non_expiring_service.pk,
                expiry_date=date(2027, 1, 1),
            )

    def test_pathway_step_sets_its_service_on_record(self):
        step = self._create_pathway_step(
            self.business,
            self.expiring_service,
        )

        record = create_license_record(
            actor=self.owner,
            business_id=self.business.pk,
            license_type="Municipal license",
            pathway_step_id=step.pk,
            expiry_date=date(2027, 1, 1),
        )

        self.assertEqual(record.pathway_step_id, step.pk)
        self.assertEqual(record.government_service_id, self.expiring_service.pk)

    def test_pathway_step_from_another_business_is_rejected(self):
        step = self._create_pathway_step(
            self.other_business,
            self.expiring_service,
        )

        with self.assertRaises(PermissionDenied):
            create_license_record(
                actor=self.owner,
                business_id=self.business.pk,
                license_type="Municipal license",
                pathway_step_id=step.pk,
            )

    def test_service_must_match_linked_pathway_step(self):
        step = self._create_pathway_step(
            self.business,
            self.expiring_service,
        )

        with self.assertRaises(ValidationError):
            create_license_record(
                actor=self.owner,
                business_id=self.business.pk,
                license_type="Municipal license",
                pathway_step_id=step.pk,
                government_service_id=self.non_expiring_service.pk,
            )

    def test_dates_cannot_expire_before_issue(self):
        with self.assertRaises(ValidationError):
            create_license_record(
                actor=self.owner,
                business_id=self.business.pk,
                license_type="Municipal license",
                government_service_id=self.expiring_service.pk,
                issue_date=date(2027, 1, 1),
                expiry_date=date(2026, 1, 1),
            )

    def test_list_and_update_are_scoped_to_business_owner(self):
        record = create_license_record(
            actor=self.owner,
            business_id=self.business.pk,
            license_type="Municipal license",
            government_service_id=self.expiring_service.pk,
        )

        records = list_license_records(
            actor=self.owner,
            business_id=self.business.pk,
        )
        self.assertEqual(list(records), [record])

        with self.assertRaises(PermissionDenied):
            list_license_records(
                actor=self.other_user,
                business_id=self.business.pk,
            )

        with self.assertRaises(PermissionDenied):
            update_license_record(
                actor=self.other_user,
                license_record_id=record.pk,
                identifier="CHANGED",
            )

        updated = update_license_record(
            actor=self.owner,
            license_record_id=record.pk,
            identifier="LIC-123",
            expiry_date=date(2027, 1, 1),
        )
        self.assertEqual(updated.identifier, "LIC-123")
        self.assertEqual(updated.expiry_date, date(2027, 1, 1))
        self.assertEqual(
            updated.verification_status,
            LicenseRecord.VerificationStatus.USER_PROVIDED_UNVERIFIED,
        )
