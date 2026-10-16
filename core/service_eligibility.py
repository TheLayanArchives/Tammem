from .models import BusinessAnswer, GovernmentService


def get_answer_value(business_profile, question):

    answer = BusinessAnswer.objects.filter(
        business_profile=business_profile,
        question=question
    ).first()

    if answer is None:
        return None

    question_type = question.question_type

    if question_type == "BOOLEAN":
        return answer.boolean_value

    elif question_type == "SINGLE":
        if answer.selected_option_id is None:
            return None
        return answer.selected_option.code

    elif question_type == "MULTIPLE":
        selected_options = list(
            answer.selected_options.values_list(
                "code", flat=True
            )
        )

        if not selected_options:
            return None

        return selected_options

    elif question_type == "TEXT":
        return answer.text_value

    elif question_type == "NUMBER":
        return answer.integer_value

    elif question_type == "DECIMAL":
        return answer.decimal_value

    elif question_type == "DATE":
        return answer.date_value

    return None

"----------------------------------------------------------------------------"
"----------------------------------------------------------------------------"
"----------------------------------------------------------------------------"
from decimal import Decimal, InvalidOperation
from datetime import date
def evaluate_service_condition(condition, business_profile):

    # Step 1: Get the actual value
    if condition.source == "ANSWER":
        actual_value = get_answer_value(
            business_profile,
            condition.question
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

    elif condition.source == "LOCATION":
        location = business_profile.location

        if location is None:
            return None

        allowed_fields = {
            "city_name_en",
            "region_name_en",
            "municipality_code",
        }

        if condition.field_name not in allowed_fields:
            return None

        actual_value = getattr(
            location,
            condition.field_name,
            None
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

"----------------------------------------------------------------------------"
"----------------------------------------------------------------------------"
"----------------------------------------------------------------------------"
def evaluate_service_rule(rule, business_profile):

    # Get all conditions belonging to this rule
    conditions = list(rule.conditions.all())

    # An inactive rule must not match
    if not rule.is_active:
        return False

    # A rule without conditions is not valid
    if not conditions:
        return None

    # Evaluate each condition
    results = [
        evaluate_service_condition(condition, business_profile)
        for condition in conditions
    ]

    # ALL means every condition must be True
    if rule.logic == "ALL":

        if False in results:
            return False

        if None in results:
            return None

        return True

    # ANY means at least one condition must be True
    elif rule.logic == "ANY":

        if True in results:
            return True

        if None in results:
            return None

        return False

    # Unknown logic
    return None

"----------------------------------------------------------------------------"
"----------------------------------------------------------------------------"
"----------------------------------------------------------------------------"
def get_applicable_services(business_profile):

    applicable_services = []
    not_applicable_services = []
    unknown_services = []

    # Get all active government services
    services = GovernmentService.objects.filter(
        is_active=True
    ).prefetch_related("rules__conditions")

    for service in services:

        # Get active rules for this service
        rules = [
            rule for rule in service.rules.all()
            if rule.is_active
        ]

        # No rules means eligibility is not defined
        if not rules:
            unknown_services.append(service)
            continue

        # Evaluate all rules for this service
        results = [
            evaluate_service_rule(rule, business_profile)
            for rule in rules
        ]

        # OR logic between different rules
        if True in results:
            applicable_services.append(service)

        elif None in results:
            unknown_services.append(service)

        else:
            not_applicable_services.append(service)

    return {
        "applicable": applicable_services,
        "not_applicable": not_applicable_services,
        "unknown": unknown_services,
    }