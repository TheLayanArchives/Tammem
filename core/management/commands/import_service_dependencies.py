
import json
from pathlib import Path
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import GovernmentService, ServiceDependency


class Command(BaseCommand):
    help = "Validate and import service dependencies from JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Save dependencies to the database.",
        )

    def handle(self, *args, **options):
        file_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "service_dependencies.json"
        )

        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        try:
            with file_path.open(encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError(str(error))

        dependencies = data.get("dependencies")

        if not isinstance(dependencies, list):
            raise CommandError("'dependencies' must be a list.")

        services = {
            service.code: service
            for service in GovernmentService.objects.all()
        }

        pairs = set()

        # Validate JSON relationships
        for index, item in enumerate(dependencies, start=1):
            if not isinstance(item, dict):
                raise CommandError(f"Item {index} must be an object.")

            service_code = item.get("service_code")
            prerequisite_code = item.get("depends_on_code")

            if service_code not in services:
                raise CommandError(
                    f"Unknown service: {service_code}"
                )

            if prerequisite_code not in services:
                raise CommandError(
                    f"Unknown prerequisite: {prerequisite_code}"
                )

            if service_code == prerequisite_code:
                raise CommandError(
                    f"Service {service_code} cannot depend on itself."
                )

            pair = (service_code, prerequisite_code)

            if pair in pairs:
                raise CommandError(
                    f"Duplicate dependency: "
                    f"{service_code} -> {prerequisite_code}"
                )

            pairs.add(pair)

        # Include existing database relationships
        existing_pairs = set(
            ServiceDependency.objects.values_list(
                "service__code",
                "prerequisite__code",
            )
        )

        # Build dependency graph
        graph = defaultdict(list)

        for service_code, prerequisite_code in pairs | existing_pairs:
            graph[service_code].append(prerequisite_code)

        # Detect circular dependencies
        visiting = set()
        visited = set()

        def visit(node):
            if node in visiting:
                raise CommandError(
                    f"Circular dependency detected at {node}"
                )

            if node in visited:
                return

            visiting.add(node)

            for prerequisite in graph.get(node, []):
                visit(prerequisite)

            visiting.remove(node)
            visited.add(node)

        for node in list(graph):
            visit(node)

        self.stdout.write(
            self.style.SUCCESS(
                f"Validated {len(pairs)} dependency relationship(s)."
            )
        )

        # Preview mode
        if not options["apply"]:
            self.stdout.write(
                "Preview only. Use --apply to save."
            )
            return

        created = 0
        skipped = 0

        # Import relationships into PostgreSQL
        with transaction.atomic():
            for service_code, prerequisite_code in sorted(pairs):
                service = services[service_code]
                prerequisite = services[prerequisite_code]

                _, was_created = ServiceDependency.objects.get_or_create(
                    service=service,
                    prerequisite=prerequisite,
                )

                if was_created:
                    created += 1
                else:
                    skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {created}, Skipped: {skipped}"
            )
        )
