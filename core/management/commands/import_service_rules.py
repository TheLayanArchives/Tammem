
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    GovernmentService,
    Question,
    ServiceRule,
    ServiceCondition,
)


class Command(BaseCommand):
    help = "Import government service eligibility rules from JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Save validated rules to the database",
        )

    def handle(self, *args, **options):
        file_path = (
            Path(settings.BASE_DIR)
            / "core"
            / "data"
            / "service_rules.json"
        )

        if not file_path.exists():
            raise CommandError(
                f"JSON file not found: {file_path}"
            )

        try:
            data = json.loads(
                file_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc))

        if not isinstance(data, dict) or not isinstance(
            data.get("rules"), list
        ):
            raise CommandError(
                "JSON must contain a 'rules' list."
            )

        prepared = []
        seen = set()

        for index, item in enumerate(data["rules"], start=1):
            try:
                code = item["service_code"]
                logic = item["logic"]
                conditions = item["conditions"]
            except (KeyError, TypeError) as exc:
                raise CommandError(
                    f"Invalid rule #{index}: {exc}"
                )

            if logic not in ("ALL", "ANY"):
                raise CommandError(
                    f"Invalid logic for {code}"
                )

            is_active = item.get("is_active", False)
            if not isinstance(is_active, bool):
                raise CommandError(
                    f"is_active must be true or false for {code}"
                )

            if not isinstance(conditions, list) or not conditions:
                raise CommandError(
                    f"Rule for {code} needs conditions"
                )

            try:
                service = GovernmentService.objects.get(
                    code=code
                )
            except GovernmentService.DoesNotExist:
                raise CommandError(
                    f"Service not found: {code}"
                )

            validated_conditions = []

            for raw in conditions:
                try:
                    source = raw["source"]
                    question = None
                    if source == "ANSWER":
                        question_code = raw.get("question_code")
                        if not question_code:
                            raise CommandError(
                                f"ANSWER condition for {code} needs question_code."
                            )
                        try:
                            question = Question.objects.get(
                                code=question_code
                            )
                        except Question.DoesNotExist:
                            raise CommandError(
                                f"Question not found for {code}: {question_code}"
                            )
                    elif raw.get("question_code"):
                        raise CommandError(
                            f"question_code is only valid for ANSWER conditions ({code})."
                        )

                    condition = ServiceCondition(
                        source=source,
                        question=question,
                        field_name=raw.get("field_name"),
                        operator=raw["operator"],
                        expected_value=raw["expected_value"],
                    )
                    condition.full_clean(
                        exclude=["rule"]
                    )
                except Exception as exc:
                    raise CommandError(
                        f"Invalid condition for {code}: {exc}"
                    )

                validated_conditions.append(
                    {
                        "source": condition.source,
                        "question": question,
                        "field_name": condition.field_name,
                        "operator": condition.operator,
                        "expected_value": condition.expected_value,
                    }
                )

            signature = (
                code,
                logic,
                tuple(
                    sorted(
                        (
                            c["source"],
                            c["question"].code if c["question"] else "",
                            c["field_name"] or "",
                            c["operator"],
                            str(c["expected_value"]),
                        )
                        for c in validated_conditions
                    )
                ),
            )

            if signature in seen:
                raise CommandError(
                    f"Duplicate rule in JSON: {code}"
                )

            seen.add(signature)
            prepared.append(
                (service, logic, validated_conditions, is_active)
            )

        self.stdout.write(
            f"Validated {len(prepared)} rule(s)."
        )

        if not options["apply"]:
            self.stdout.write(
                "Preview only. Use --apply to save."
            )
            return

        created = 0
        skipped = 0
        activation_updates = 0
        deactivated = 0
        construction_codes = {
            "BUILDING_PERMIT",
            "BUILDING_RENOVATION",
            "BUILDING_MODIFICATION",
        }
        reconciled_service_codes = construction_codes | {"R14"}
        desired_reconciled_rules = {}
        for service, logic, conditions, _ in prepared:
            if service.code not in reconciled_service_codes:
                continue
            signature = tuple(sorted(
                (
                    c["source"],
                    c["question"].code if c["question"] else "",
                    c["field_name"] or "",
                    c["operator"],
                    str(c["expected_value"]),
                )
                for c in conditions
            ))
            desired_reconciled_rules.setdefault(service.code, set()).add(
                (logic, signature)
            )

        with transaction.atomic():
            for service, logic, conditions, is_active in prepared:
                existing_rules = (
                    ServiceRule.objects
                    .filter(service=service, logic=logic)
                    .prefetch_related("conditions")
                )

                desired = sorted(
                    (
                        c["source"],
                        c["question"].code if c["question"] else "",
                        c["field_name"] or "",
                        c["operator"],
                        str(c["expected_value"]),
                    )
                    for c in conditions
                )

                matching_rule = None

                for existing in existing_rules:
                    actual = sorted(
                        (
                            c.source,
                            c.question.code if c.question_id else "",
                            c.field_name or "",
                            c.operator,
                            str(c.expected_value),
                        )
                        for c in existing.conditions.all()
                    )

                    if actual == desired:
                        matching_rule = existing
                        break

                if matching_rule:
                    if matching_rule.is_active != is_active:
                        matching_rule.is_active = is_active
                        matching_rule.save(update_fields=["is_active"])
                        activation_updates += 1
                    else:
                        skipped += 1
                    continue

                rule = ServiceRule.objects.create(
                    service=service,
                    logic=logic,
                    is_active=is_active,
                )

                for c in conditions:
                    ServiceCondition.objects.create(
                        rule=rule,
                        **c,
                    )

                created += 1

            # These services are imported as complete reviewed rule sets.
            # Retire superseded rules so obsolete conditions cannot remain
            # active alongside the current eligibility logic.
            for service_code, desired_signatures in desired_reconciled_rules.items():
                stale_rules = (
                    ServiceRule.objects
                    .filter(service__code=service_code, is_active=True)
                    .prefetch_related("conditions__question")
                )
                for rule in stale_rules:
                    actual = tuple(sorted(
                        (
                            condition.source,
                            condition.question.code if condition.question_id else "",
                            condition.field_name or "",
                            condition.operator,
                            str(condition.expected_value),
                        )
                        for condition in rule.conditions.all()
                    ))
                    if (rule.logic, actual) not in desired_signatures:
                        rule.is_active = False
                        rule.save(update_fields=["is_active"])
                        deactivated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {created}, Skipped: {skipped}, "
                f"Activation updates: {activation_updates}, "
                f"Deactivated obsolete rules: {deactivated}"
            )
        )
