from types import SimpleNamespace

from django.test import SimpleTestCase

from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import (
    Business,
    BusinessProfile,
    BusinessAnswer,
    Question,
    QuestionOption,
    QuestionRule,
    RuleCondition,
)
from core.Services.questionnaire import (
    evaluate_condition,
    evaluate_rule,
    question_applies_to_business,
    get_visible_questions,
)

class EvaluateConditionTests(SimpleTestCase):
    def make_condition(
        self,
        source="ANSWER",
        operator="EQUALS",
        expected_value="YES",
        question_id=1,
    ):
        return SimpleNamespace(
            source=source,
            operator=operator,
            expected_value=expected_value,
            depends_on_question_id=question_id,
        )

    def make_answer(self, value):
        return SimpleNamespace(
            selected_option=SimpleNamespace(code=value),
            boolean_value=None,
            text_value=None,
            integer_value=None,
            decimal_value=None,
            date_value=None,
        )

    def setUp(self):
        self.profile = SimpleNamespace(
            activity=SimpleNamespace(
                code="COFFEE_SHOP",
                industry=SimpleNamespace(code="FOOD"),
            )
        )

    def test_equals_matches(self):
        condition = self.make_condition(expected_value="YES")
        answers = {1: self.make_answer("YES")}

        self.assertTrue(
            evaluate_condition(condition, answers, self.profile)
        )

    def test_equals_does_not_match(self):
        condition = self.make_condition(expected_value="YES")
        answers = {1: self.make_answer("NO")}

        self.assertFalse(
            evaluate_condition(condition, answers, self.profile)
        )

    def test_missing_answer_returns_false(self):
        condition = self.make_condition()

        self.assertFalse(
            evaluate_condition(condition, {}, self.profile)
        )

    def test_not_equals(self):
        condition = self.make_condition(
            operator="NOT_EQUALS",
            expected_value="NO",
        )
        answers = {1: self.make_answer("YES")}

        self.assertTrue(
            evaluate_condition(condition, answers, self.profile)
        )

    def test_contains(self):
        condition = self.make_condition(
            operator="CONTAINS",
            expected_value="coffee",
        )
        answers = {1: self.make_answer("COFFEE_SHOP")}

        self.assertTrue(
            evaluate_condition(condition, answers, self.profile)
        )

    def test_greater_than(self):
        condition = self.make_condition(
            operator="GREATER_THAN",
            expected_value="10",
        )
        answers = {1: self.make_answer("15")}

        self.assertTrue(
            evaluate_condition(condition, answers, self.profile)
        )

    def test_less_than(self):
        condition = self.make_condition(
            operator="LESS_THAN",
            expected_value="10",
        )
        answers = {1: self.make_answer("5")}

        self.assertTrue(
            evaluate_condition(condition, answers, self.profile)
        )

    def test_industry_condition(self):
        condition = self.make_condition(
            source="INDUSTRY",
            expected_value="FOOD",
        )

        self.assertTrue(
            evaluate_condition(condition, {}, self.profile)
        )

    def test_activity_condition(self):
        condition = self.make_condition(
            source="ACTIVITY",
            expected_value="COFFEE_SHOP",
        )

        self.assertTrue(
            evaluate_condition(condition, {}, self.profile)
        )

    def test_missing_activity_returns_false(self):
        condition = self.make_condition(
            source="ACTIVITY",
            expected_value="COFFEE_SHOP",
        )
        profile = SimpleNamespace(activity=None)

        self.assertFalse(
            evaluate_condition(condition, {}, profile)
        )

    def test_equals_matches_selected_multi_select_option(self):
        condition = SimpleNamespace(
            source="ANSWER",
            depends_on_question_id=1,
            expected_value="ONLINE",
            operator="EQUALS",
        )

        answer = SimpleNamespace(
            selected_option=None,
            selected_options=[
                SimpleNamespace(code="PHYSICAL"),
                SimpleNamespace(code="ONLINE"),
            ],
            boolean_value=None,
            text_value=None,
            integer_value=None,
            decimal_value=None,
            date_value=None,
        )

        answers = {1: answer}

        result = evaluate_condition(
            condition,
            answers,
            business_profile=SimpleNamespace(activity=None),
        )

        self.assertTrue(result)




class EvaluateRuleTests(SimpleTestCase):
    def setUp(self):
        self.profile = SimpleNamespace(
            activity=SimpleNamespace(
                code="COFFEE_SHOP",
                industry=SimpleNamespace(code="FOOD"),
            )
        )

    def make_condition(self, question_id, expected):
        return SimpleNamespace(
            source="ANSWER",
            depends_on_question_id=question_id,
            expected_value=expected,
            operator="EQUALS",
        )

    def make_answer(self, code):
        return SimpleNamespace(
            selected_option=SimpleNamespace(code=code),
            boolean_value=None,
            text_value=None,
            integer_value=None,
            decimal_value=None,
            date_value=None,
        )

    def make_rule(self, logic, conditions):
        return SimpleNamespace(
            logic=logic,
            conditions=SimpleNamespace(
                all=lambda: conditions
            ),
        )

    def test_all_passes_when_every_condition_matches(self):
        rule = self.make_rule(
            "ALL",
            [
                self.make_condition(1, "YES"),
                self.make_condition(2, "YES"),
            ],
        )
        answers = {
            1: self.make_answer("YES"),
            2: self.make_answer("YES"),
        }

        self.assertTrue(
            evaluate_rule(rule, answers, self.profile)
        )

    def test_all_fails_when_one_condition_does_not_match(self):
        rule = self.make_rule(
            "ALL",
            [
                self.make_condition(1, "YES"),
                self.make_condition(2, "YES"),
            ],
        )
        answers = {
            1: self.make_answer("YES"),
            2: self.make_answer("NO"),
        }

        self.assertFalse(
            evaluate_rule(rule, answers, self.profile)
        )

    def test_any_passes_when_one_condition_matches(self):
        rule = self.make_rule(
            "ANY",
            [
                self.make_condition(1, "YES"),
                self.make_condition(2, "YES"),
            ],
        )
        answers = {
            1: self.make_answer("NO"),
            2: self.make_answer("YES"),
        }

        self.assertTrue(
            evaluate_rule(rule, answers, self.profile)
        )

    def test_any_fails_when_no_conditions_match(self):
        rule = self.make_rule(
            "ANY",
            [
                self.make_condition(1, "YES"),
                self.make_condition(2, "YES"),
            ],
        )
        answers = {
            1: self.make_answer("NO"),
            2: self.make_answer("NO"),
        }

        self.assertFalse(
            evaluate_rule(rule, answers, self.profile)
        )

    def test_empty_rule_returns_false(self):
        rule = self.make_rule("ALL", [])

        self.assertFalse(
            evaluate_rule(rule, {}, self.profile)
        )

    def test_unknown_logic_returns_false(self):
        rule = self.make_rule(
            "UNKNOWN",
            [self.make_condition(1, "YES")],
        )
        answers = {1: self.make_answer("YES")}

        self.assertFalse(
            evaluate_rule(rule, answers, self.profile)
        )

class QuestionApplicabilityTests(SimpleTestCase):
    def setUp(self):
        self.profile = SimpleNamespace(
            activity_id=7,
            activity=SimpleNamespace(id=7),
        )

    def make_question(self, scope, associated_activity_ids=None):
        associated_activity_ids = (
            associated_activity_ids or []
        )

        return SimpleNamespace(
            scope=scope,
            activities=SimpleNamespace(
                filter=lambda id: SimpleNamespace(
                    exists=lambda: id in associated_activity_ids
                )
            ),
        )

    def test_general_question_applies(self):
        question = self.make_question("GENERAL")

        self.assertTrue(
            question_applies_to_business(
                question, self.profile
            )
        )

    def test_profile_question_applies(self):
        question = self.make_question("PROFILE")

        self.assertTrue(
            question_applies_to_business(
                question, self.profile
            )
        )

    def test_associated_activity_question_applies(self):
        question = self.make_question(
            "ACTIVITY",
            associated_activity_ids=[7],
        )

        self.assertTrue(
            question_applies_to_business(
                question, self.profile
            )
        )

    def test_unassociated_activity_question_does_not_apply(self):
        question = self.make_question(
            "ACTIVITY",
            associated_activity_ids=[99],
        )

        self.assertFalse(
            question_applies_to_business(
                question, self.profile
            )
        )

    def test_activity_question_does_not_apply_without_activity(self):
        question = self.make_question(
            "ACTIVITY",
            associated_activity_ids=[7],
        )
        profile_without_activity = SimpleNamespace(
            activity_id=None,
            activity=None,
        )

        self.assertFalse(
            question_applies_to_business(
                question, profile_without_activity
            )
        )


class GetVisibleQuestionsTests(SimpleTestCase):
    def setUp(self):
        self.profile = SimpleNamespace(
            pk=1,
            id=1,
            activity_id=7,
            activity=SimpleNamespace(id=7),
        )

    @patch("core.Services.questionnaire.Question.objects")
    @patch("core.Services.questionnaire.BusinessAnswer.objects")
    def test_active_unruled_question_is_visible(
        self,
        mock_answers,
        mock_questions,
    ):
        question = SimpleNamespace(
            pk=10,
            scope="GENERAL",
            display_order=1,
            rules=SimpleNamespace(
                filter=lambda **kwargs: SimpleNamespace(
                    exists=lambda: False
                )
            ),
            activities=SimpleNamespace(),
        )

        mock_answers.filter.return_value.select_related.return_value = []

        mock_questions.filter.return_value.order_by.return_value = [
            question
        ]

        visible = get_visible_questions(self.profile)

        self.assertEqual(visible, [question])

    @patch("core.Services.questionnaire.evaluate_rule")
    @patch("core.Services.questionnaire.Question.objects")
    @patch("core.Services.questionnaire.BusinessAnswer.objects")
    def test_question_with_passing_rule_is_visible(
        self,
        mock_answers,
        mock_questions,
        mock_evaluate_rule,
    ):
        mock_answers.filter.return_value.select_related.return_value = []

        rule = SimpleNamespace()
        rules = MagicMock()
        rules.exists.return_value = True
        rules.__iter__.return_value = iter([rule])

        question = SimpleNamespace(
            pk=11,
            scope="GENERAL",
            display_order=1,
            rules=SimpleNamespace(
                filter=lambda **kwargs: rules
            ),
        )

        mock_questions.filter.return_value.order_by.return_value = [
            question
        ]
        mock_evaluate_rule.return_value = True

        visible = get_visible_questions(self.profile)

        self.assertEqual(visible, [question])
        mock_evaluate_rule.assert_called_once_with(
            rule,
            {},
            self.profile,
        )

    @patch("core.Services.questionnaire.evaluate_rule")
    @patch("core.Services.questionnaire.Question.objects")
    @patch("core.Services.questionnaire.BusinessAnswer.objects")
    def test_question_with_failing_rule_is_hidden(
        self,
        mock_answers,
        mock_questions,
        mock_evaluate_rule,
    ):
        mock_answers.filter.return_value.select_related.return_value = []

        rule = SimpleNamespace()
        rules = MagicMock()
        rules.exists.return_value = True
        rules.__iter__.return_value = iter([rule])

        question = SimpleNamespace(
            pk=12,
            scope="GENERAL",
            display_order=1,
            rules=SimpleNamespace(
                filter=lambda **kwargs: rules
            ),
        )

        mock_questions.filter.return_value.order_by.return_value = [
            question
        ]
        mock_evaluate_rule.return_value = False

        visible = get_visible_questions(self.profile)

        self.assertEqual(visible, [])
        mock_evaluate_rule.assert_called_once_with(
            rule,
            {},
            self.profile,
        )



class SaudiIndividualVisibilityTests(SimpleTestCase):
    def setUp(self):
        self.profile = SimpleNamespace(
            pk=1,
            id=1,
            activity_id=7,
            activity=SimpleNamespace(id=7),
        )

    @patch("core.Services.questionnaire.BusinessAnswer.objects")
    @patch("core.Services.questionnaire.Question.objects")
    def test_q002_visibility_depends_on_q001_answer(
        self,
        mock_questions,
        mock_answers,
    ):
        # Q001 has no rules, so it is visible by default.
        q001 = SimpleNamespace(
            code="Q001",
            pk=1,
            scope="GENERAL",
            display_order=1,
            rules=SimpleNamespace(
                filter=lambda **kwargs: SimpleNamespace(
                    exists=lambda: False
                )
            ),
            activities=SimpleNamespace(),
        )

        # Q002 should appear only when Q001 is SAUDI_INDIVIDUAL.
        condition = SimpleNamespace(
            source="ANSWER",
            depends_on_question_id=1,
            expected_value="SAUDI_INDIVIDUAL",
            operator="EQUALS",
        )

        rule = SimpleNamespace(
            logic="ALL",
            conditions=SimpleNamespace(
                all=lambda: [condition]
            ),
        )

        # Mock a queryset-like object that supports exists()
        # and iteration, as get_visible_questions() expects.
        q002_rules = MagicMock()
        q002_rules.exists.return_value = True
        q002_rules.__iter__.return_value = iter([rule])

        q002 = SimpleNamespace(
            code="Q002",
            pk=2,
            scope="GENERAL",
            display_order=2,
            rules=SimpleNamespace(
                filter=lambda **kwargs: q002_rules
            ),
            activities=SimpleNamespace(),
        )

        mock_questions.filter.return_value.order_by.return_value = [
            q001,
            q002,
        ]

        # Check both possible answers to Q001.
        test_cases = [
            ("SAUDI_INDIVIDUAL", True),
            ("FOREIGN_INDIVIDUAL", False),
        ]

        for answer_code, expected_q002_visibility in test_cases:
            answer = SimpleNamespace(
                question_id=1,
                selected_option=SimpleNamespace(code=answer_code),
                boolean_value=None,
                text_value=None,
                integer_value=None,
                decimal_value=None,
                date_value=None,
            )

            mock_answers.filter.return_value.select_related.return_value = [
                answer
            ]

            with self.subTest(answer_code=answer_code):
                visible = get_visible_questions(self.profile)

                self.assertIn(q001, visible)

                if expected_q002_visibility:
                    self.assertIn(q002, visible)
                else:
                    self.assertNotIn(q002, visible)

class QuestionnaireDatabaseIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="questionnaire_test_user",
            password="test-password-123",
        )

        self.business = Business.objects.create(
            user=self.user,
            business_name="Integration Test Business",
        )

        self.profile = BusinessProfile.objects.create(
            business=self.business,
            applicant_type="INDIVIDUAL",
            business_structure="TEST_STRUCTURE",
            operating_model="TEST_MODEL",
            has_ecommerce=False,
            has_employees=False,
            is_manufacturer=False,
            profile_version=1,
        )

        self.q001 = Question.objects.create(
            code="TEST_Q001",
            text_ar="سؤال تجريبي أول",
            text_en="Test question one",
            question_type="SINGLE",
            is_required=True,
            is_active=True,
            display_order=1,
            scope="GENERAL",
        )

        self.q002 = Question.objects.create(
            code="TEST_Q002",
            text_ar="سؤال تجريبي ثانٍ",
            text_en="Test question two",
            question_type="BOOLEAN",
            is_required=False,
            is_active=True,
            display_order=2,
            scope="GENERAL",
        )

        self.saudi_option = QuestionOption.objects.create(
            question=self.q001,
            code="SAUDI_INDIVIDUAL",
            label_ar="سعودي",
            label_en="Saudi individual",
            value="SAUDI_INDIVIDUAL",
            display_order=1,
            is_active=True,
        )

        self.foreign_option = QuestionOption.objects.create(
            question=self.q001,
            code="FOREIGN_INDIVIDUAL",
            label_ar="غير سعودي",
            label_en="Foreign individual",
            value="FOREIGN_INDIVIDUAL",
            display_order=2,
            is_active=True,
        )

        self.rule = QuestionRule.objects.create(
            target_question=self.q002,
            logic="ALL",
            is_active=True,
        )

        RuleCondition.objects.create(
            rule=self.rule,
            source="ANSWER",
            depends_on_question=self.q001,
            operator="EQUALS",
            expected_value="SAUDI_INDIVIDUAL",
        )

    def test_question_visibility_changes_with_database_answer(self):
        # Initially, there is no answer to Q001.
        visible_codes = {
            question.code
            for question in get_visible_questions(self.profile)
        }
        self.assertIn("TEST_Q001", visible_codes)
        self.assertNotIn("TEST_Q002", visible_codes)

        # Save a real database answer selecting the Saudi option.
        BusinessAnswer.objects.create(
            business_profile=self.profile,
            question=self.q001,
            selected_option=self.saudi_option,
        )

        visible_codes = {
            question.code
            for question in get_visible_questions(self.profile)
        }
        self.assertIn("TEST_Q002", visible_codes)

        # Change the answer to the foreign individual option.
        answer = BusinessAnswer.objects.get(
            business_profile=self.profile,
            question=self.q001,
        )
        answer.selected_option = self.foreign_option
        answer.save()

        visible_codes = {
            question.code
            for question in get_visible_questions(self.profile)
        }
        self.assertNotIn("TEST_Q002", visible_codes)

class ActivityQuestionDatabaseTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from core.models import Activity, Industry

        User = get_user_model()
        user = User.objects.create_user(
            username="activity_test_user",
            password="test-password-123",
        )

        business = Business.objects.create(
            user=user,
            business_name="Activity Test Business",
        )

        industry = Industry.objects.create(
            code="TEST_INDUSTRY",
            name_en="Test Industry",
            name_ar="قطاع تجريبي",
            is_active=True,
        )

        self.activity_a = Activity.objects.create(
            industry=industry,
            code="TEST_ACTIVITY_A",
            name_en="Test Activity A",
            name_ar="نشاط تجريبي أ",
            is_active=True,
        )

        self.activity_b = Activity.objects.create(
            industry=industry,
            code="TEST_ACTIVITY_B",
            name_en="Test Activity B",
            name_ar="نشاط تجريبي ب",
            is_active=True,
        )

        self.profile = BusinessProfile.objects.create(
            business=business,
            applicant_type="INDIVIDUAL",
            business_structure="TEST_STRUCTURE",
            operating_model="TEST_MODEL",
            has_ecommerce=False,
            has_employees=False,
            is_manufacturer=False,
            profile_version=1,
            activity=self.activity_a,
        )

        self.activity_question = Question.objects.create(
            code="TEST_ACTIVITY_QUESTION",
            text_ar="سؤال نشاط تجريبي",
            text_en="Test activity question",
            question_type="BOOLEAN",
            is_required=False,
            is_active=True,
            display_order=1,
            scope="ACTIVITY",
        )

        self.activity_question.activities.add(self.activity_a)

    def test_question_applies_to_associated_activity(self):
        from core.Services.questionnaire import question_applies_to_business

        self.assertTrue(
            question_applies_to_business(
                self.activity_question,
                self.profile,
            )
        )

    def test_question_does_not_apply_to_unassociated_activity(self):
        from core.Services.questionnaire import question_applies_to_business

        self.profile.activity = self.activity_b

        self.assertFalse(
            question_applies_to_business(
                self.activity_question,
                self.profile,
            )
        )

    def test_question_does_not_apply_without_activity(self):
        from core.Services.questionnaire import question_applies_to_business

        self.profile.activity = None

        self.assertFalse(
            question_applies_to_business(
                self.activity_question,
                self.profile,
            )
        )

