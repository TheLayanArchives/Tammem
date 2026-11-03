from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

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
from core.Services.monitoring_summary import get_business_monitoring_summary


class BusinessMonitoringSummaryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="monitor_owner")
        self.other_user = User.objects.create_user(username="monitor_other")
        self.business = Business.objects.create(
            user=self.owner,
            business_name="Monitoring test business",
        )
        self.profile = BusinessProfile.objects.create(
            business=self.business,
            applicant_type="INDIVIDUAL",
            business_structure="NEW",
            operating_model="PHYSICAL",
        )
        self.today = timezone.localdate()

    def test_license_counts_use_mutually_exclusive_date_ranges(self):
        expiry_dates = [
            self.today - timedelta(days=1),
            self.today,
            self.today + timedelta(days=30),
            self.today + timedelta(days=31),
            None,
        ]
        for index, expiry_date in enumerate(expiry_dates):
            LicenseRecord.objects.create(
                business=self.business,
                license_type=f"Test license {index}",
                expiry_date=expiry_date,
            )

        summary = get_business_monitoring_summary(
            actor=self.owner,
            business_id=self.business.pk,
            today=self.today,
        )

        self.assertEqual(summary["licenses"], {
            "total": 5,
            "expired": 1,
            "expiring_within_30_days": 2,
            "valid_beyond_30_days": 1,
            "expiry_date_not_provided": 1,
            "user_provided_unverified": 5,
        })
        self.assertEqual(summary["as_of"], self.today.isoformat())

    def test_pathway_progress_uses_saved_current_version_counts(self):
        authority = Authority.objects.create(
            code="MONITOR_TEST_AUTHORITY",
            name_en="Monitoring test authority",
            name_ar="جهة اختبار المراقبة",
        )
        required_service = GovernmentService.objects.create(
            code="MONITOR_REQUIRED_SERVICE",
            name_en="Required service",
            name_ar="خدمة مطلوبة",
            authority=authority,
        )
        optional_service = GovernmentService.objects.create(
            code="MONITOR_OPTIONAL_SERVICE",
            name_en="Optional service",
            name_ar="خدمة اختيارية",
            authority=authority,
        )
        pathway = Pathway.objects.create(
            business_profile=self.profile,
            status=Pathway.Status.ACTIVE,
        )
        version = PathwayVersion.objects.create(
            pathway=pathway,
            version_number=1,
            profile_version=self.profile.profile_version,
            reason=PathwayVersion.Reason.INITIAL,
            generation_snapshot={},
            generation_hash="a" * 64,
        )
        pathway.current_version = version
        pathway.save(update_fields=["current_version", "updated_at"])

        PathwayStep.objects.create(
            version=version,
            service=required_service,
            order=1,
            status=PathwayStep.Status.COMPLETED,
            mandatory_status="REQUIRED",
            service_code_snapshot=required_service.code,
            service_name_ar_snapshot=required_service.name_ar,
            service_name_en_snapshot=required_service.name_en,
        )
        PathwayStep.objects.create(
            version=version,
            service=optional_service,
            order=2,
            status=PathwayStep.Status.NOT_STARTED,
            mandatory_status="OPTIONAL",
            service_code_snapshot=optional_service.code,
            service_name_ar_snapshot=optional_service.name_ar,
            service_name_en_snapshot=optional_service.name_en,
        )

        summary = get_business_monitoring_summary(
            actor=self.owner,
            business_id=self.business.pk,
            today=self.today,
        )

        self.assertEqual(summary["pathway"], {
            "status": Pathway.Status.ACTIVE,
            "current_version": 1,
            "required_steps_total": 1,
            "required_steps_completed": 1,
            "progress_percent": 100.0,
        })

    def test_monitoring_endpoint_is_owner_scoped_and_omits_step_list(self):
        self.client.force_login(self.owner)
        url = f"/api/businesses/{self.business.pk}/monitoring/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["business"]["id"], self.business.pk)
        self.assertIsNone(body["pathway"])
        self.assertNotIn("outstanding_steps", body)

        self.client.force_login(self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_monitoring_endpoint_requires_authentication(self):
        response = self.client.get(
            f"/api/businesses/{self.business.pk}/monitoring/"
        )
        self.assertEqual(response.status_code, 401)
