from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Authority, Business, LicenseRecord
from core.Services.license_service import list_license_record_data


class LicenseListApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="license_list_owner")
        self.other_user = User.objects.create_user(username="license_list_other")
        self.business = Business.objects.create(
            user=self.owner,
            business_name="License list business",
        )
        self.today = timezone.localdate()
        authority = Authority.objects.create(
            code="LICENSE_CREATE_AUTHORITY",
            name_en="License create authority",
            name_ar="جهة إنشاء الترخيص",
        )
        self.expiry_service = authority.services.create(
            code="LICENSE_CREATE_EXPIRY_SERVICE",
            name_en="Expiry-enabled license",
            name_ar="ترخيص قابل للانتهاء",
            expiry_tracking_available=True,
        )
        self.non_expiry_service = authority.services.create(
            code="LICENSE_CREATE_NO_EXPIRY_SERVICE",
            name_en="No-expiry license",
            name_ar="ترخيص دون انتهاء",
            expiry_tracking_available=False,
        )

    def test_license_data_includes_metadata_and_date_based_status(self):
        dates = [
            self.today - timedelta(days=1),
            self.today + timedelta(days=7),
            self.today + timedelta(days=31),
            None,
        ]
        for index, expiry_date in enumerate(dates):
            LicenseRecord.objects.create(
                business=self.business,
                license_type=f"Record {index}",
                identifier=f"ID-{index}",
                issue_date=self.today - timedelta(days=10),
                expiry_date=expiry_date,
            )

        result = list_license_record_data(
            actor=self.owner,
            business_id=self.business.pk,
            today=self.today,
        )

        self.assertEqual(result["as_of"], self.today.isoformat())
        by_type = {record["license_type"]: record for record in result["licenses"]}
        self.assertEqual(by_type["Record 0"]["expiry_status"], "EXPIRED")
        self.assertEqual(
            by_type["Record 1"]["expiry_status"],
            "EXPIRING_WITHIN_30_DAYS",
        )
        self.assertEqual(
            by_type["Record 2"]["expiry_status"],
            "VALID_BEYOND_30_DAYS",
        )
        self.assertEqual(
            by_type["Record 3"]["expiry_status"],
            "DATE_NOT_PROVIDED",
        )
        self.assertTrue(all(
            item["verification_status"]
            == LicenseRecord.VerificationStatus.USER_PROVIDED_UNVERIFIED
            for item in result["licenses"]
        ))
        self.assertEqual(by_type["Record 1"]["identifier"], "ID-1")

    def test_endpoint_returns_service_metadata(self):
        authority = Authority.objects.create(
            code="LICENSE_LIST_AUTHORITY",
            name_en="License list authority",
            name_ar="جهة قائمة التراخيص",
        )
        service = authority.services.create(
            code="LICENSE_LIST_SERVICE",
            name_en="Business license",
            name_ar="رخصة تجارية",
            official_url="https://example.gov.sa/service",
        )
        LicenseRecord.objects.create(
            business=self.business,
            government_service=service,
            license_type="Business license",
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            f"/api/businesses/{self.business.pk}/licenses/"
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["licenses"][0]
        self.assertEqual(item["government_service"]["code"], service.code)
        self.assertIsNone(item["pathway_step"])

    def test_license_endpoint_is_owner_scoped(self):
        self.client.force_login(self.other_user)
        response = self.client.get(
            f"/api/businesses/{self.business.pk}/licenses/"
        )
        self.assertEqual(response.status_code, 404)

    def test_license_endpoint_requires_authentication(self):
        response = self.client.get(
            f"/api/businesses/{self.business.pk}/licenses/"
        )
        self.assertEqual(response.status_code, 401)

    def test_post_creates_owner_record_and_renewal_event(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/api/businesses/{self.business.pk}/licenses/",
            data=(
                '{"license_type":"Café license",'
                f'"government_service_id":{self.expiry_service.pk},'
                f'"issue_date":"{self.today.isoformat()}",'
                f'"expiry_date":"{(self.today + timedelta(days=90)).isoformat()}"'
                "}"
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        record = LicenseRecord.objects.get(business=self.business)
        self.assertEqual(record.created_by, self.owner)
        self.assertEqual(
            record.verification_status,
            LicenseRecord.VerificationStatus.USER_PROVIDED_UNVERIFIED,
        )
        self.assertEqual(response.json()["license"]["id"], record.pk)
        self.assertTrue(record.compliance_events.filter(status="OPEN").exists())

    def test_post_rejects_expiry_without_eligible_service(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/api/businesses/{self.business.pk}/licenses/",
            data=(
                '{"license_type":"Unlinked license",'
                f'"expiry_date":"{(self.today + timedelta(days=90)).isoformat()}"'
                "}"
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(LicenseRecord.objects.filter(business=self.business).exists())

        response = self.client.post(
            f"/api/businesses/{self.business.pk}/licenses/",
            data=(
                '{"license_type":"No-expiry service",'
                f'"government_service_id":{self.non_expiry_service.pk},'
                f'"expiry_date":"{(self.today + timedelta(days=90)).isoformat()}"'
                "}"
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_post_rejects_foreign_business_and_malformed_fields(self):
        self.client.force_login(self.other_user)
        url = f"/api/businesses/{self.business.pk}/licenses/"
        response = self.client.post(
            url,
            data='{"license_type":"Test"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.post(
            url,
            data='{"license_type":"Test","issue_date":"tomorrow"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
