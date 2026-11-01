import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from openpyxl import load_workbook

from core.models import (
    Authority,
    Activity,
    Business,
    BusinessAnswer,
    BusinessProfile,
    GovernmentService,
    Industry,
    Question,
    QuestionOption,
    ServiceCondition,
    ServiceDependency,
    ServiceRule,
    ServiceActivity,
)
from core.service_eligibility import get_applicable_services
from core.Services.questionnaire import get_visible_questions
from core.Services.pathway import generate_business_pathway
from core.Services.pathway_persistence import save_business_pathway


DATA_DIR = Path(__file__).resolve().parent / "data"


class ConstructionRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        user = User.objects.create_user(username="construction-rules-test")
        business = Business.objects.create(user=user, business_name="Test cafe")
        cls.profile = BusinessProfile.objects.create(
            business=business,
            applicant_type="INDIVIDUAL",
            business_structure="NEW",
            operating_model="PHYSICAL",
        )
        industry = Industry.objects.create(
            code="FOOD_TEST", name_en="Food", name_ar="أغذية"
        )
        cls.activities = {
            code: Activity.objects.create(
                industry=industry,
                code=code,
                name_en=code,
                name_ar=code,
            )
            for code in ("CAFE_A", "CAFE_B", "CAFE_C", "CAFE_K")
        }
        cls.activity = cls.activities["CAFE_A"]
        cls.profile.activity = cls.activity
        cls.profile.save(update_fields=["activity"])

        bool_question = Question.objects.create(
            code="Q037", text_en="Has location", text_ar="هل يوجد موقع؟",
            question_type="BOOLEAN", scope="PROFILE",
        )
        cls.questions = {"Q037": bool_question}
        q030 = Question.objects.create(
            code="Q030", text_en="Customer access", text_ar="وصول العملاء",
            question_type="MULTIPLE", scope="PROFILE",
        )
        cls.questions["Q030"] = q030
        for code in (
            "PHYSICAL_LOCATION", "ONLINE", "MOBILE_LOCATION_BASED",
            "CUSTOMER_PREMISES", "HOME_BASED", "MULTIPLE_LOCATIONS",
        ):
            QuestionOption.objects.create(
                question=q030, code=code, value=code,
                label_en=code, label_ar=code,
            )
        q038 = Question.objects.create(
            code="Q038", text_en="Location type", text_ar="نوع الموقع",
            question_type="SINGLE", scope="PROFILE",
        )
        cls.questions["Q038"] = q038
        for code in ("RESTAURANT_CAFE", "SHOP_STORE", "HOME", "MOBILE_UNIT"):
            QuestionOption.objects.create(
                question=q038, code=code, value=code,
                label_en=code, label_ar=code,
            )
        q039 = Question.objects.create(
            code="Q039", text_en="Property relationship", text_ar="العلاقة بالعقار",
            question_type="SINGLE", scope="PROFILE",
        )
        cls.questions["Q039"] = q039
        for code, label in (
            ("OWNER", "Owner"),
            ("TENANT_LEASED", "Tenant/leased"),
            ("INVESTMENT_OTHER_CONTRACT", "Investment/other contract"),
            ("OTHER", "Other"),
        ):
            QuestionOption.objects.create(
                question=q039, code=code, value=code,
                label_en=label, label_ar=label,
            )

        catalogue = json.loads(
            (DATA_DIR / "construction_questions.json").read_text(encoding="utf-8")
        )
        for item in catalogue["questions"]:
            question = Question.objects.create(
                code=item["code"],
                text_en=item["text_en"],
                text_ar=item["text_ar"],
                question_type="SINGLE",
                scope="PROFILE",
            )
            cls.questions[item["code"]] = question
            for order, (code, label_en, label_ar) in enumerate(item["options"], 1):
                QuestionOption.objects.create(
                    question=question,
                    code=code,
                    value=code,
                    label_en=label_en,
                    label_ar=label_ar,
                    display_order=order,
                )

        call_command("import_construction_question_rules", "--apply", verbosity=0)

        authority = Authority.objects.create(
            code="MOMAH_BALADY_TEST",
            name_en="Ministry of Municipalities and Housing",
            name_ar="وزارة البلديات والإسكان",
        )
        service_data = json.loads(
            (DATA_DIR / "construction_services.json").read_text(encoding="utf-8")
        )
        service_rules = json.loads(
            (DATA_DIR / "service_rules.json").read_text(encoding="utf-8")
        )["rules"]
        for item in service_data["services"]:
            service = GovernmentService.objects.create(
                code=item["code"],
                name_en=item["name_en"],
                name_ar=item["name_ar"],
                authority=authority,
                applicability="CONDITIONAL",
                mandatory_status="UNDECIDED",
            )
            for activity in cls.activities.values():
                ServiceActivity.objects.create(
                    service=service,
                    activity=activity,
                )
            for rule_data in service_rules:
                if rule_data["service_code"] != service.code:
                    continue
                rule = ServiceRule.objects.create(service=service, logic="ALL")
                for condition in rule_data["conditions"]:
                    ServiceCondition.objects.create(
                        rule=rule,
                        source="ANSWER",
                        question=cls.questions[condition["question_code"]],
                        operator=condition["operator"],
                        expected_value=condition["expected_value"],
                    )

    def setUp(self):
        self.save_answer("Q030", ["PHYSICAL_LOCATION"])
        self.save_answer("Q037", True)
        self.save_answer("Q038", "RESTAURANT_CAFE")

    def save_answer(self, code, value):
        question = self.questions[code]
        defaults = {"boolean_value": None, "selected_option": None}
        if question.question_type == "BOOLEAN":
            defaults["boolean_value"] = value
        elif question.question_type == "SINGLE":
            defaults["selected_option"] = QuestionOption.objects.get(
                question=question, code=value
            )
        answer, _ = BusinessAnswer.objects.update_or_create(
            business_profile=self.profile,
            question=question,
            defaults=defaults,
        )
        if question.question_type == "MULTIPLE":
            answer.selected_options.set(
                QuestionOption.objects.filter(question=question, code__in=value)
            )

    def visible_codes(self):
        return {q.code for q in get_visible_questions(self.profile)}

    def applicable_codes(self):
        result = get_applicable_services(self.profile)
        return {service.code for service in result["applicable"]}

    def test_new_construction_selects_building_permit(self):
        self.save_answer("Q037", True)
        self.save_answer("Q111", "VACANT_LAND_NEW_CONSTRUCTION_REQUIRED")

        self.assertIn("Q111", self.visible_codes())
        self.assertIn("BUILDING_PERMIT", self.applicable_codes())
        self.assertNotIn("BUILDING_RENOVATION", self.applicable_codes())
        self.assertNotIn("BUILDING_MODIFICATION", self.applicable_codes())

    def test_construction_questions_use_operating_premises_not_customer_channel(self):
        self.save_answer("Q030", ["ONLINE"])
        self.assertIn("Q111", self.visible_codes())

        self.save_answer("Q038", "MOBILE_UNIT")
        self.assertNotIn("Q111", self.visible_codes())

        self.save_answer("Q037", False)
        self.save_answer("Q038", "RESTAURANT_CAFE")
        self.assertNotIn("Q038", self.visible_codes())
        self.assertNotIn("Q111", self.visible_codes())

    def test_renovation_and_structural_work_select_distinct_services(self):
        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT")
        self.save_answer("Q112", "RENOVATION_OF_EXISTING_BUILDING_ELEMENTS")
        self.assertEqual(self.applicable_codes(), {"BUILDING_RENOVATION"})

        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_EXPANSION_OR_STRUCTURAL_CHANGES")
        self.save_answer("Q112", "STRUCTURAL_CHANGES_OR_BUILDING_EXPANSION")
        self.assertEqual(self.applicable_codes(), {"BUILDING_MODIFICATION"})

    def test_cosmetic_fit_out_does_not_trigger_construction_permit(self):
        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT")
        self.save_answer("Q112", "INTERIOR_DECORATION_AND_FINISHING_ONLY")
        self.assertEqual(self.applicable_codes(), set())

    def test_each_cafe_type_gets_the_service_for_each_work_scope(self):
        scenarios = (
            (
                "VACANT_LAND_NEW_CONSTRUCTION_REQUIRED",
                None,
                "BUILDING_PERMIT",
            ),
            (
                "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT",
                "RENOVATION_OF_EXISTING_BUILDING_ELEMENTS",
                "BUILDING_RENOVATION",
            ),
            (
                "EXISTING_BUILDING_REQUIRING_EXPANSION_OR_STRUCTURAL_CHANGES",
                "STRUCTURAL_CHANGES_OR_BUILDING_EXPANSION",
                "BUILDING_MODIFICATION",
            ),
        )

        for activity in self.activities.values():
            self.profile.activity = activity
            self.profile.save(update_fields=["activity"])
            for premises, works, expected_service in scenarios:
                self.save_answer("Q111", premises)
                if works:
                    self.save_answer("Q112", works)
                pathway = generate_business_pathway(self.profile)
                pathway_codes = {
                    step["service_code"] for step in pathway["steps"]
                }
                self.assertEqual(pathway_codes, {expected_service})

            self.save_answer(
                "Q111",
                "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT",
            )
            self.save_answer("Q112", "INTERIOR_DECORATION_AND_FINISHING_ONLY")
            pathway = generate_business_pathway(self.profile)
            self.assertFalse(
                {step["service_code"] for step in pathway["steps"]}
                & {
                    "BUILDING_PERMIT",
                    "BUILDING_RENOVATION",
                    "BUILDING_MODIFICATION",
                }
            )

    def test_cloud_kitchen_with_online_customer_channel_still_gets_permit_pathway(self):
        self.profile.activity = self.activities["CAFE_C"]
        self.profile.save(update_fields=["activity"])
        self.save_answer("Q030", ["ONLINE"])
        self.save_answer("Q037", True)
        self.save_answer("Q038", "RESTAURANT_CAFE")
        self.save_answer("Q111", "VACANT_LAND_NEW_CONSTRUCTION_REQUIRED")

        self.assertIn("Q111", self.visible_codes())
        self.assertEqual(self.applicable_codes(), {"BUILDING_PERMIT"})
        pathway = generate_business_pathway(self.profile)
        self.assertIn(
            "BUILDING_PERMIT",
            {step["service_code"] for step in pathway["steps"]},
        )

    def test_cloud_profile_without_a_confirmed_premises_does_not_trigger_stale_answers(self):
        self.profile.activity = self.activities["CAFE_C"]
        self.profile.save(update_fields=["activity"])
        self.save_answer("Q030", ["ONLINE"])
        self.save_answer("Q037", False)
        self.save_answer("Q038", "RESTAURANT_CAFE")
        self.save_answer("Q111", "VACANT_LAND_NEW_CONSTRUCTION_REQUIRED")

        self.assertNotIn("Q111", self.visible_codes())
        self.assertFalse(self.applicable_codes())

    def test_tenant_coverage_and_verification_control_only_status_question(self):
        self.save_answer("Q037", True)
        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT")
        self.save_answer("Q112", "RENOVATION_OF_EXISTING_BUILDING_ELEMENTS")
        self.save_answer("Q039", "TENANT_LEASED")
        self.save_answer("Q115", "YES")
        self.save_answer("Q116", "YES_ALL_PLANNED_WORKS_ARE_COVERED")

        visible = self.visible_codes()
        self.assertIn("Q118", visible)
        self.assertNotIn("Q114", visible)
        self.assertIn("BUILDING_RENOVATION", self.applicable_codes())

        self.save_answer("Q118", "NO")
        self.assertIn("Q114", self.visible_codes())
        self.assertIn("BUILDING_RENOVATION", self.applicable_codes())

        pathway = generate_business_pathway(self.profile)
        renovation_step = next(
            step for step in pathway["steps"]
            if step["service_code"] == "BUILDING_RENOVATION"
        )
        self.assertNotEqual(renovation_step.get("status"), "COMPLETED")


    def test_fully_covered_verified_tenant_permit_completes_existing_work_step(self):
        self.save_answer("Q037", True)
        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT")
        self.save_answer("Q112", "RENOVATION_OF_EXISTING_BUILDING_ELEMENTS")
        self.save_answer("Q039", "TENANT_LEASED")
        self.save_answer("Q115", "YES")
        self.save_answer("Q116", "YES_ALL_PLANNED_WORKS_ARE_COVERED")
        self.save_answer("Q118", "YES")

        pathway = generate_business_pathway(self.profile)
        renovation_step = next(
            step for step in pathway["steps"]
            if step["service_code"] == "BUILDING_RENOVATION"
        )
        self.assertEqual(renovation_step["status"], "COMPLETED")
        self.assertIn("covers all planned work", renovation_step["notes"])

        saved = save_business_pathway(self.profile)
        persisted_step = saved.steps.get(
            service_code_snapshot="BUILDING_RENOVATION"
        )
        self.assertEqual(persisted_step.status, "COMPLETED")
        self.assertIsNotNone(persisted_step.completed_at)

    def test_stale_tenant_answers_do_not_complete_owner_work_step(self):
        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT")
        self.save_answer("Q112", "RENOVATION_OF_EXISTING_BUILDING_ELEMENTS")
        self.save_answer("Q039", "OWNER")
        self.save_answer("Q115", "YES")
        self.save_answer("Q116", "YES_ALL_PLANNED_WORKS_ARE_COVERED")
        self.save_answer("Q118", "YES")

        pathway = generate_business_pathway(self.profile)
        renovation_step = next(
            step for step in pathway["steps"]
            if step["service_code"] == "BUILDING_RENOVATION"
        )
        self.assertNotEqual(renovation_step.get("status"), "COMPLETED")

    def test_partial_owner_permit_coverage_warns_without_completing_step(self):
        self.save_answer("Q111", "EXISTING_BUILDING_REQUIRING_RENOVATION_OR_FIT_OUT")
        self.save_answer("Q112", "RENOVATION_OF_EXISTING_BUILDING_ELEMENTS")
        self.save_answer("Q039", "TENANT_LEASED")
        self.save_answer("Q115", "YES")
        self.save_answer("Q116", "PARTIALLY_COVERED")

        pathway = generate_business_pathway(self.profile)
        renovation_step = next(
            step for step in pathway["steps"]
            if step["service_code"] == "BUILDING_RENOVATION"
        )
        self.assertNotEqual(renovation_step.get("status"), "COMPLETED")
        self.assertTrue(any("part of the planned work" in warning for warning in renovation_step["warnings"]))

    def test_already_issued_permit_is_not_auto_completed(self):
        self.save_answer("Q111", "VACANT_LAND_NEW_CONSTRUCTION_REQUIRED")
        self.save_answer("Q114", "ALREADY_ISSUED")

        pathway = generate_business_pathway(self.profile)
        permit_step = next(
            step for step in pathway["steps"]
            if step["service_code"] == "BUILDING_PERMIT"
        )
        self.assertNotEqual(permit_step.get("status"), "COMPLETED")
        self.assertTrue(any("verify its validity" in warning for warning in permit_step["warnings"]))


class LegacyR06ImportTests(TestCase):
    def test_catalog_reimport_keeps_r06_retired_and_drops_old_links(self):
        workbook_path = DATA_DIR / "TAMMEM_28_Services_Reviewed_Decisions.xlsx"
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            rows = list(workbook["Services"].iter_rows(values_only=True))
            headers = rows[0]
            authority_codes = {
                str(dict(zip(headers, row))["Authority_Code"]).strip()
                for row in rows[1:]
                if dict(zip(headers, row)).get("Authority_Code")
            }
        finally:
            workbook.close()

        authorities = {
            code: Authority.objects.create(
                code=code,
                name_en=code,
                name_ar=code,
            )
            for code in authority_codes
        }
        industry = Industry.objects.create(
            code="LEGACY_TEST", name_en="Test", name_ar="Test"
        )
        activity = Activity.objects.create(
            industry=industry,
            code="LEGACY_TEST_CAFE",
            name_en="Test cafe",
            name_ar="Test cafe",
        )
        r05 = GovernmentService.objects.create(
            code="R05", name_en="Lease", name_ar="Lease",
            authority=authorities["MOMAH_BALADY"],
        )
        legacy = GovernmentService.objects.create(
            code="R06", name_en="Old combined service", name_ar="Old",
            authority=authorities["MOMAH_BALADY"],
        )
        building_permit = GovernmentService.objects.create(
            code="BUILDING_PERMIT", name_en="Building permit", name_ar="Building permit",
            authority=authorities["MOMAH_BALADY"],
        )
        ServiceActivity.objects.create(service=legacy, activity=activity)
        ServiceDependency.objects.create(service=legacy, prerequisite=r05)
        ServiceDependency.objects.create(service=building_permit, prerequisite=r05)
        ServiceRule.objects.create(service=legacy, is_active=True)

        call_command("import_government_services", "--apply", verbosity=0)

        legacy.refresh_from_db()
        self.assertFalse(legacy.is_active)
        self.assertTrue(legacy.name_en.startswith("Retired R06"))
        self.assertFalse(ServiceActivity.objects.filter(service=legacy).exists())
        self.assertFalse(ServiceDependency.objects.filter(service=legacy).exists())
        self.assertFalse(legacy.rules.filter(is_active=True).exists())
        self.assertFalse(
            ServiceDependency.objects.filter(service=building_permit).exists()
        )
