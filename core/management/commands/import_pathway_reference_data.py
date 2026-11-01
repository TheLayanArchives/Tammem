import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Activity,
    GovernmentService,
    Industry,
    ServiceActivity,
    ServiceDependency,
)


class Command(BaseCommand):
    help = "Import pathway activities, service links, and dependencies."

    def add_arguments(self, parser):
        parser.add_argument(
            "fixture",
            nargs="?",
            default=None,
            help="Path to a Django JSON fixture (defaults to tammem_pathway_only.json).",
        )

    def handle(self, *args, **options):
        fixture_path = (
            Path(options["fixture"])
            if options["fixture"]
            else Path(__file__).resolve().parents[2]
            / "data"
            / "tammem_pathway_only.json"
        )
        if not fixture_path.is_file():
            raise CommandError(f"Fixture not found: {fixture_path}")

        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read fixture: {exc}")

        records = defaultdict(list)
        for item in fixture:
            if not isinstance(item, dict) or "model" not in item:
                raise CommandError("Fixture contains an invalid record.")
            records[item["model"]].append(item)

        industries = records["core.industry"]
        activities = records["core.activity"]
        services = records["core.governmentservice"]
        service_activities = records["core.serviceactivity"]
        dependencies = records["core.servicedependency"]

        if not activities or not services:
            raise CommandError("Fixture must include activities and services.")

        industry_codes = {
            item["pk"]: item["fields"]["code"] for item in industries
        }
        activity_codes = {
            item["pk"]: item["fields"]["code"] for item in activities
        }
        service_codes = {
            item["pk"]: item["fields"]["code"] for item in services
        }
        for record in activities:
            industry_id = record["fields"].get("industry")
            if industry_id not in industry_codes:
                raise CommandError(
                    f"Activity {record['fields'].get('code')} has no fixture industry."
                )
        for record in service_activities:
            fields = record["fields"]
            if fields.get("service") not in service_codes or fields.get("activity") not in activity_codes:
                raise CommandError("Fixture has an invalid service-activity link.")
        for record in dependencies:
            fields = record["fields"]
            if fields.get("service") not in service_codes or fields.get("prerequisite") not in service_codes:
                raise CommandError("Fixture has an invalid service dependency.")
        missing_services = set(service_codes.values()) - set(
            GovernmentService.objects.values_list("code", flat=True)
        )
        if missing_services:
            raise CommandError(
                f"Import services first; missing: {sorted(missing_services)}"
            )

        graph = defaultdict(list)
        for item in dependencies:
            fields = item["fields"]
            service_code = service_codes[fields["service"]]
            prerequisite_code = service_codes[fields["prerequisite"]]
            if service_code == prerequisite_code:
                raise CommandError(f"Service {service_code} depends on itself.")
            graph[service_code].append(prerequisite_code)

        visiting = set()
        visited = set()

        def visit(code):
            if code in visiting:
                raise CommandError(f"Circular dependency detected at {code}.")
            if code in visited:
                return
            visiting.add(code)
            for prerequisite in graph[code]:
                visit(prerequisite)
            visiting.remove(code)
            visited.add(code)

        for service_code in service_codes.values():
            visit(service_code)

        service_objects = {
            item.code: item
            for item in GovernmentService.objects.filter(
                code__in=service_codes.values()
            )
        }
        industry_objects = {}
        activity_objects = {}
        created_counts = defaultdict(int)

        with transaction.atomic():
            for record in industries:
                fields = record["fields"]
                industry, created = Industry.objects.get_or_create(
                    code=fields["code"],
                    defaults={
                        "name_ar": fields["name_ar"],
                        "name_en": fields["name_en"],
                        "is_active": fields.get("is_active", True),
                    },
                )
                industry_objects[record["pk"]] = industry
                created_counts["industries"] += int(created)

            for record in activities:
                fields = record["fields"]
                parent_id = fields.get("parent_activity")
                defaults = {
                    "industry": industry_objects[fields["industry"]],
                    "name_ar": fields["name_ar"],
                    "name_en": fields["name_en"],
                    "parent_activity": activity_objects.get(parent_id),
                    "official_activity_code": fields.get("official_activity_code"),
                    "is_active": fields.get("is_active", True),
                }
                activity, created = Activity.objects.get_or_create(
                    code=fields["code"], defaults=defaults
                )
                activity_objects[record["pk"]] = activity
                created_counts["activities"] += int(created)

            for record in service_activities:
                fields = record["fields"]
                _, created = ServiceActivity.objects.get_or_create(
                    service=service_objects[service_codes[fields["service"]]],
                    activity=activity_objects[fields["activity"]],
                )
                created_counts["service_activity_links"] += int(created)

            for record in dependencies:
                fields = record["fields"]
                _, created = ServiceDependency.objects.get_or_create(
                    service=service_objects[service_codes[fields["service"]]],
                    prerequisite=service_objects[
                        service_codes[fields["prerequisite"]]
                    ],
                )
                created_counts["dependencies"] += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                "Pathway reference data imported. "
                f"New industries: {created_counts['industries']}; "
                f"new activities: {created_counts['activities']}; "
                f"new service-activity links: {created_counts['service_activity_links']}; "
                f"new dependencies: {created_counts['dependencies']}."
            )
        )
