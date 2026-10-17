
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    GovernmentService,
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
                    condition = ServiceCondition(
                        source=raw["source"],
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

                if condition.source == "ANSWER":
                    raise CommandError(
                        "ANSWER rules are not supported "
                        "by this importer yet."
                    )

                validated_conditions.append(
                    {
                        "source": condition.source,
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
                (service, logic, validated_conditions)
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

        with transaction.atomic():
            for service, logic, conditions in prepared:
                existing_rules = (
                    ServiceRule.objects
                    .filter(service=service, logic=logic)
                    .prefetch_related("conditions")
                )

                desired = sorted(
                    (
                        c["source"],
                        c["field_name"] or "",
                        c["operator"],
                        str(c["expected_value"]),
                    )
                    for c in conditions
                )

                already_exists = False

                for existing in existing_rules:
                    actual = sorted(
                        (
                            c.source,
                            c.field_name or "",
                            c.operator,
                            str(c.expected_value),
                        )
                        for c in existing.conditions.all()
                    )

                    if actual == desired:
                        already_exists = True
                        break

                if already_exists:
                    skipped += 1
                    continue

                rule = ServiceRule.objects.create(
                    service=service,
                    logic=logic,
                    is_active=False,
                )

                for c in conditions:
                    ServiceCondition.objects.create(
                        rule=rule,
                        **c,
                    )

                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {created}, Skipped: {skipped}"
            )
        )
