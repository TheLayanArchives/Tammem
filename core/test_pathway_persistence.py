
"""Run: python manage.py test core.test_pathway_persistence"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Business,
    BusinessProfile,
    Authority,
    GovernmentService,
    Pathway,
    PathwayStep,
    PathwayVersion,
    PathwayChangeLog,
)

from core.Services.pathway_persistence import (
    save_business_pathway,
    update_pathway_step_status,
    get_pathway_summary,
)


def generated(
    codes,
    *,
    unresolved=False,
    mandatory_status="REQUIRED",
):
    """Create sample pathway output for testing."""

    return {
        "steps": [
            {
                "order": i,
                "service_code": code,
                "service_name_ar": code,
                "service_name_en": code,
                "mandatory_status": mandatory_status,
                "official_url": "https://example.org/",
                "step_type": "SERVICE",
                "warnings": [],
            }
            for i, code in enumerate(codes, 1)
        ],
        "unknown_services": [],
        "not_applicable_services": [],
        "missing_dependencies": (
            [("B", "X")] if unresolved else []
        ),
        "has_unresolved_dependencies": unresolved,
    }


class PathwayPersistenceTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tammem_test",
            password="test-pass",
        )

        self.business = Business.objects.create(
            user=self.user,
            business_name="Test cafe",
        )

        self.profile = BusinessProfile.objects.create(
            business=self.business,
            applicant_type="INDIVIDUAL",
            business_structure="NEW",
            operating_model="PHYSICAL",
        )

        authority = Authority.objects.create(
            code="TEST",
            name_en="Test",
            name_ar="اختبار",
        )

        for code in ("A", "B", "C"):
            GovernmentService.objects.create(
                code=code,
                name_ar=code,
                name_en=code,
                authority=authority,
            )

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_create_and_idempotent_rerun(self, generator):
        generator.return_value = generated(["A", "B"])

        first = save_business_pathway(
            self.profile,
            actor=self.user,
        )

        second = save_business_pathway(
            self.profile,
            actor=self.user,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PathwayVersion.objects.count(), 1)
        self.assertEqual(first.steps.count(), 2)

        self.assertEqual(
            get_pathway_summary(first.pathway)["progress_percent"],
            0,
        )

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_new_version_carries_progress_and_history(
        self,
        generator,
    ):
        generator.return_value = generated(["A", "B"])

        v1 = save_business_pathway(
            self.profile,
            actor=self.user,
        )

        original = v1.steps.get(service__code="A")

        update_pathway_step_status(
            original.pk,
            "COMPLETED",
            actor=self.user,
        )

        generator.return_value = generated(["A", "C"])

        v2 = save_business_pathway(
            self.profile,
            actor=self.user,
        )

        self.assertEqual(v2.version_number, 2)

        self.assertEqual(
            v2.steps.get(service__code="A").status,
            "COMPLETED",
        )

        self.assertEqual(
            v2.steps.get(service__code="C").status,
            "NOT_STARTED",
        )

        self.assertTrue(
            v1.steps.filter(service__code="B").exists()
        )

        self.assertTrue(
            PathwayChangeLog.objects.filter(
                action="STEP_REMOVED",
                service_code="B",
            ).exists()
        )

        with self.assertRaises(ValidationError):
            update_pathway_step_status(
                original.pk,
                "NOT_STARTED",
                actor=self.user,
            )

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_invalid_dependencies_never_saved(
        self,
        generator,
    ):
        generator.return_value = generated(
            ["A", "B"],
            unresolved=True,
        )

        with self.assertRaises(ValidationError):
            save_business_pathway(
                self.profile,
                actor=self.user,
            )

        self.assertFalse(Pathway.objects.exists())

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_completion_percentage(self, generator):
        generator.return_value = generated(["A", "B"])

        version = save_business_pathway(
            self.profile,
            actor=self.user,
        )

        step = version.steps.get(service__code="A")

        update_pathway_step_status(
            step.pk,
            "COMPLETED",
            actor=self.user,
        )

        self.assertEqual(
            get_pathway_summary(
                version.pathway
            )["progress_percent"],
            50.0,
        )

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_optional_step_can_be_skipped_without_counting_as_required_progress(
        self,
        generator,
    ):
        generator.return_value = generated(
            ["A"], mandatory_status="OPTIONAL"
        )

        version = save_business_pathway(
            self.profile,
            actor=self.user,
        )
        step = version.steps.get(service__code="A")

        skipped = update_pathway_step_status(
            step.pk,
            PathwayStep.Status.SKIPPED,
            actor=self.user,
        )

        self.assertEqual(skipped.status, PathwayStep.Status.SKIPPED)
        self.assertIsNone(skipped.completed_at)
        self.assertEqual(
            get_pathway_summary(version.pathway),
            {
                "version": 1,
                "required_total": 0,
                "required_done": 0,
                "progress_percent": 0,
            },
        )

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_required_step_cannot_be_skipped(self, generator):
        generator.return_value = generated(["A"])

        version = save_business_pathway(
            self.profile,
            actor=self.user,
        )
        step = version.steps.get(service__code="A")

        with self.assertRaises(ValidationError):
            update_pathway_step_status(
                step.pk,
                PathwayStep.Status.SKIPPED,
                actor=self.user,
            )

        step.refresh_from_db()
        self.assertEqual(
            step.status,
            PathwayStep.Status.NOT_STARTED,
        )

    @patch(
        "core.Services.pathway_persistence.generate_business_pathway"
    )
    def test_skipped_optional_step_resets_if_it_becomes_required(
        self,
        generator,
    ):
        generator.return_value = generated(
            ["A"], mandatory_status="OPTIONAL"
        )
        version_one = save_business_pathway(
            self.profile,
            actor=self.user,
        )
        step = version_one.steps.get(service__code="A")
        update_pathway_step_status(
            step.pk,
            PathwayStep.Status.SKIPPED,
            actor=self.user,
        )

        generator.return_value = generated(["A"])
        version_two = save_business_pathway(
            self.profile,
            actor=self.user,
        )

        self.assertEqual(
            version_two.steps.get(service__code="A").status,
            PathwayStep.Status.NOT_STARTED,
        )
