from core.models import (
    BusinessAnswer,
    Question,
    QuestionRule,
)

def evaluate_condition(condition, answers, business_profile):
    """
    Check whether one RuleCondition is satisfied.

    Supported sources:
    - ANSWER
    - INDUSTRY
    - ACTIVITY
    """

    expected = condition.expected_value

    # -----------------------------------
    # 1. Get the actual value
    # -----------------------------------

    if condition.source == "ANSWER":
        answer = answers.get(condition.depends_on_question_id)

        if not answer:
            return False

        if answer.selected_option:
            actual = answer.selected_option.code
        elif answer.boolean_value is not None:
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

    # -----------------------------------
    # 2. Evaluate the operator
    # -----------------------------------

    if condition.operator == "EQUALS":
        return actual == expected

    if condition.operator == "NOT_EQUALS":
        return actual != expected

    if condition.operator == "CONTAINS":
        return expected.lower() in actual.lower()

    if condition.operator == "GREATER_THAN":
        return float(actual) > float(expected)

    if condition.operator == "LESS_THAN":
        return float(actual) < float(expected)

    return False


def evaluate_rule(rule, answers, business_profile):
    """
    Check whether all/any conditions for a rule are satisfied.
    """

    conditions = list(rule.conditions.all())

    if not conditions:
        return False

    results = [
        evaluate_condition(
            condition,
            answers,
            business_profile
        )
        for condition in conditions
    ]

    if rule.logic == "ALL":
        return all(results)

    if rule.logic == "ANY":
        return any(results)

    return False

def question_applies_to_business(question, business_profile):
    """
    Check whether a question applies to this business profile.
    """

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
    """
    Return the questions that should currently be visible
    for a BusinessProfile.
    """

    answers = {
        answer.question_id: answer
        for answer in BusinessAnswer.objects.filter(
            business_profile=business_profile
        ).select_related("selected_option")
    }

    visible_questions = []

    for question in Question.objects.filter(
        is_active=True
    ).order_by("display_order"):

        # First check whether this question applies
        # to the business profile/activity.
        if not question_applies_to_business(
            question,
            business_profile
        ):
            continue

        rules = question.rules.filter(
            is_active=True
        )

        # If the question has no rules,
        # it is visible by default.
        if not rules.exists():
            visible_questions.append(question)
            continue

        # The question has rules.
        # It is visible if at least one rule passes.
        for rule in rules:
            if evaluate_rule(
                rule,
                answers,
                business_profile
            ):
                visible_questions.append(question)
                break

    return visible_questions