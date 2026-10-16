from decimal import Decimal, InvalidOperation
from datetime import date
from .models import Question

from .service_eligibility import get_answer_value


def evaluate_question_condition(condition, business_profile):

    # Step 1: Get the actual value
    if condition.source == "ANSWER":
        if condition.depends_on_question_id is None:
            return None

        actual_value = get_answer_value(
            business_profile,
            condition.depends_on_question
        )

    elif condition.source == "ACTIVITY":
        actual_value = (
            business_profile.activity.code
            if business_profile.activity_id else None
        )

    elif condition.source == "INDUSTRY":
        actual_value = (
            business_profile.activity.industry.code
            if business_profile.activity_id
            and business_profile.activity.industry_id
            else None
        )

    else:
        return None

    # Step 2: Check for missing values
    if actual_value is None:
        return None

    expected_value = condition.expected_value
    operator = condition.operator

    # Step 3: Convert values to comparable types
    if isinstance(actual_value, bool):
        normalized = expected_value.strip().lower()

        if normalized not in ("true", "false"):
            return None

        expected_value = normalized == "true"

    elif isinstance(actual_value, Decimal):
        try:
            expected_value = Decimal(expected_value)
        except InvalidOperation:
            return None

    elif isinstance(actual_value, int):
        try:
            expected_value = int(expected_value)
        except ValueError:
            return None

    elif isinstance(actual_value, date):
        try:
            expected_value = date.fromisoformat(expected_value)
        except ValueError:
            return None

    # Step 4: Evaluate the operator
    if operator == "EQUALS":
        return actual_value == expected_value

    elif operator == "NOT_EQUALS":
        return actual_value != expected_value

    elif operator == "CONTAINS":
        if isinstance(actual_value, (list, str)):
            return expected_value in actual_value
        return None

    elif operator == "GREATER_THAN":
        if isinstance(actual_value, (int, Decimal, date)):
            return actual_value > expected_value
        return None

    elif operator == "LESS_THAN":
        if isinstance(actual_value, (int, Decimal, date)):
            return actual_value < expected_value
        return None

    return None
"---------------------------------------------------------"
"---------------------------------------------------------"
def evaluate_question_rule(rule, business_profile):

    # Step 1: Check if the rule is active
    if not rule.is_active:
        return False

    # Step 2: Get all conditions for this rule
    conditions = list(rule.conditions.all())

    # A rule without conditions is not valid
    if not conditions:
        return None

    # Step 3: Evaluate each condition
    results = [
        evaluate_question_condition(condition, business_profile)
        for condition in conditions
    ]

    # Step 4: Apply ALL logic
    if rule.logic == "ALL":

        if False in results:
            return False

        if None in results:
            return None

        return True

    # Step 5: Apply ANY logic
    elif rule.logic == "ANY":

        if True in results:
            return True

        if None in results:
            return None

        return False

    # Unknown logic
    return None

"-----------------------------------------------------------"
"-----------------------------------------------------------"
"-----------------------------------------------------------"
def get_visible_questions(business_profile):

    visible_questions = []

    # Get all active questions in display order
    questions = Question.objects.filter(
        is_active=True
    ).order_by("display_order", "id").prefetch_related(
        "activities",
        "rules__conditions__depends_on_question"
    )

    for question in questions:

        # Step 1: Check activity-specific questions
        if question.scope == "ACTIVITY":

            if not business_profile.activity_id:
                continue

            # If activities are assigned, the activity must match
            assigned_activities = [
                activity.id for activity in question.activities.all()
            ]

            if (
                assigned_activities
                and business_profile.activity_id not in assigned_activities
            ):
                continue

        # Step 2: Get active question rules
        rules = [
            rule for rule in question.rules.all()
            if rule.is_active
        ]

        # Step 3: Questions without rules are visible
        if not rules:
            visible_questions.append(question)
            continue

        # Step 4: Evaluate rules (OR between rules)
        results = [
            evaluate_question_rule(rule, business_profile)
            for rule in rules
        ]

        # Show the question if at least one rule matches
        if True in results:
            visible_questions.append(question)

    return visible_questions
