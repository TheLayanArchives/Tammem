import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Question, QuestionRule, RuleCondition


class Command(BaseCommand):
    help = "Import the reviewed construction question visibility rules."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / "core" / "data" / "construction_question_rules.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc))

        prepared = []
        for index, item in enumerate(data.get("rules", []), start=1):
            if item.get("logic") not in {"ALL", "ANY"} or not item.get("conditions"):
                raise CommandError(f"Invalid rule #{index}.")
            try:
                target = Question.objects.get(code=item["target"])
                conditions = []
                for raw in item["conditions"]:
                    question = Question.objects.get(code=raw["question"])
                    condition = RuleCondition(
                        source="ANSWER",
                        depends_on_question=question,
                        operator=raw["operator"],
                        expected_value=raw["value"],
                    )
                    condition.full_clean(exclude=["rule"])
                    conditions.append(condition)
            except (KeyError, Question.DoesNotExist, ValueError) as exc:
                raise CommandError(f"Invalid construction rule #{index}: {exc}")
            prepared.append((target, item["logic"], conditions))

        self.stdout.write(f"Validated {len(prepared)} construction visibility rules.")
        if not options["apply"]:
            self.stdout.write("Preview only. Use --apply to save.")
            return

        created = 0
        existing = 0
        desired_by_target = {}
        for target, logic, conditions in prepared:
            desired = tuple(sorted(
                (c.depends_on_question.code, c.operator, c.expected_value)
                for c in conditions
            ))
            desired_by_target.setdefault(target.pk, set()).add((logic, desired))

        with transaction.atomic():
            for target, logic, conditions in prepared:
                desired = sorted(
                    (c.depends_on_question.code, c.operator, c.expected_value)
                    for c in conditions
                )
                found = False
                for rule in target.rules.filter(is_active=True).prefetch_related("conditions__depends_on_question"):
                    actual = sorted(
                        (c.depends_on_question.code, c.operator, c.expected_value)
                        for c in rule.conditions.all()
                        if c.source == "ANSWER"
                    )
                    if rule.logic == logic and actual == desired:
                        found = True
                        break
                if found:
                    existing += 1
                    continue

                rule = QuestionRule.objects.create(target_question=target, logic=logic)
                for condition in conditions:
                    condition.rule = rule
                    condition.save()
                created += 1

            deactivated = 0
            for target_id in desired_by_target:
                target = Question.objects.get(pk=target_id)
                for rule in target.rules.filter(is_active=True).prefetch_related("conditions__depends_on_question"):
                    actual = tuple(sorted(
                        (c.depends_on_question.code, c.operator, c.expected_value)
                        for c in rule.conditions.all()
                        if c.source == "ANSWER"
                    ))
                    if (rule.logic, actual) not in desired_by_target[target_id]:
                        rule.is_active = False
                        rule.save(update_fields=["is_active"])
                        deactivated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created: {created}; already present: {existing}; "
            f"deactivated obsolete construction rules: {deactivated}."
        ))
