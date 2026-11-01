from core.models import (
    BusinessAnswer,
    Question,
    QuestionRule,
)


def evaluate_condition(condition, answers, business_profile):
    """Check whether one RuleCondition is satisfied."""

    expected = condition.expected_value

    if condition.source == "ANSWER":
        answer = answers.get(condition.depends_on_question_id)

        if not answer:
            return False

        # Single-select answer
        if answer.selected_option:
            actual = answer.selected_option.code

        else:
            # Multi-select answer
            selected_options = getattr(answer, "selected_options", None)

            if selected_options is not None:
                if hasattr(selected_options, "all"):
                    selected_options = list(selected_options.all())
                else:
                    selected_options = list(selected_options)

                selected_codes = [
                    option.code for option in selected_options
                ]

                if selected_codes:
                    if condition.operator in {"EQUALS", "CONTAINS"}:
                        return expected in selected_codes

                    if condition.operator == "NOT_EQUALS":
                        return expected not in selected_codes

                    return False

            # Boolean, text, numeric, and date answers
            if answer.boolean_value is not None:
                actual = str(answer.boolean_value).lower()

            elif answer.text_value is not None:
                actual = answer.text_value

            elif answer.integer_value is not None:
                actual = str(answer.integer_value)

            elif answer.decimal_value is not None:
                actual = str(answer.decimal_value)

            elif answer.date_value is not None:
                actual = str(answer.date_value)

            else:
                return False

    elif condition.source == "INDUSTRY":
        if not business_profile.activity:
            return False

        if not business_profile.activity.industry:
            return False

        actual = business_profile.activity.industry.code

    elif condition.source == "ACTIVITY":
        if not business_profile.activity:
            return False

        actual = business_profile.activity.code

    else:
        return False

    # Compare the actual value with the expected value
    if condition.operator == "EQUALS":
        return actual == expected

    if condition.operator == "NOT_EQUALS":
        return actual != expected

    if condition.operator == "CONTAINS":
        if not isinstance(actual, str) or not isinstance(expected, str):
            return False

        return expected.lower() in actual.lower()

    if condition.operator == "GREATER_THAN":
        try:
            return float(actual) > float(expected)
        except (ValueError, TypeError):
            return False

    if condition.operator == "LESS_THAN":
        try:
            return float(actual) < float(expected)
        except (ValueError, TypeError):
            return False

    return False


def evaluate_rule(rule, answers, business_profile):
    """Evaluate all conditions belonging to a rule."""

    conditions = list(rule.conditions.all())

    if not conditions:
        return False

    results = [
        evaluate_condition(condition, answers, business_profile)
        for condition in conditions
    ]

    if rule.logic == "ALL":
        return all(results)

    if rule.logic == "ANY":
        return any(results)

    return False


def question_applies_to_business(question, business_profile):
    """Check whether a question applies to the selected business activity."""

    if question.scope == "GENERAL":
        return True

    if question.scope == "PROFILE":
        return True

    if question.scope == "ACTIVITY":
        if not business_profile.activity:
            return False

        return question.activities.filter(
            id=business_profile.activity_id
        ).exists()

    return False


def get_visible_questions(business_profile):
    """Return active questions applicable to the business and its answers."""

    answers = {
        answer.question_id: answer
        for answer in BusinessAnswer.objects.filter(
            business_profile=business_profile
        ).select_related("selected_option")
    }

    visible_questions = []

    questions = Question.objects.filter(
        is_active=True
    ).order_by("display_order")

    for question in questions:
        if not question_applies_to_business(
            question,
            business_profile,
        ):
            continue

        rules = question.rules.filter(is_active=True)

        if not rules.exists():
            visible_questions.append(question)
            continue

        for rule in rules:
            if evaluate_rule(rule, answers, business_profile):
                visible_questions.append(question)
                break

    return visible_questions
