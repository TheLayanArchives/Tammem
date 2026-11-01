import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Activity,
    Authority,
    GovernmentService,
    ServiceActivity,
    ServiceDependency,
    ServiceRule,
)


class Command(BaseCommand):
    help = "Import construction-specific services and pathway links."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / "core" / "data" / "construction_services.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc))

        try:
            authority = Authority.objects.get(code=data["authority_code"])
            legacy = GovernmentService.objects.get(code=data["legacy_service_code"])
        except (KeyError, Authority.DoesNotExist, GovernmentService.DoesNotExist) as exc:
            raise CommandError(f"Required authority or service is missing: {exc}")

        activities = {
            activity.code: activity
            for activity in Activity.objects.filter(code__in=data["activity_codes"])
        }
        missing_activities = set(data["activity_codes"]) - set(activities)
        if missing_activities:
            raise CommandError(f"Missing activities: {sorted(missing_activities)}")

        prepared = []
        for item in data.get("services", []):
            try:
                if item["trigger_question"] not in {"Q111", "Q112"}:
                    raise ValueError("Unexpected construction trigger question")
                prepared.append(item)
            except (KeyError, ValueError) as exc:
                raise CommandError(f"Invalid construction service record: {exc}")
        if len(prepared) != 3 or len({item["code"] for item in prepared}) != 3:
            raise CommandError("Expected three uniquely coded construction services.")
        construction_codes = {item["code"] for item in prepared}

        self.stdout.write(
            f"Validated {len(prepared)} services and {len(activities)} activity links."
        )
        if not options["apply"]:
            self.stdout.write("Preview only. Use --apply to save.")
            return

        with transaction.atomic():
            for item in prepared:
                service, _ = GovernmentService.objects.update_or_create(
                    code=item["code"],
                    defaults={
                        "authority": authority,
                        "name_en": item["name_en"],
                        "name_ar": item["name_ar"],
                        "description_en": item["description_en"],
                        "description_ar": item["description_ar"],
                        "official_url": data["official_url"],
                        "is_active": True,
                        "applicability": "CONDITIONAL",
                        # Triggering a potential service is not a legal determination
                        # that the applicant must obtain it.
                        "mandatory_status": "UNDECIDED",
                    },
                )
                for activity in activities.values():
                    ServiceActivity.objects.get_or_create(
                        service=service,
                        activity=activity,
                    )

            # R06 was a combined placeholder. Keep its row for historic pathway
            # snapshots, but retire its active links and prerequisite metadata.
            legacy.name_en = data["legacy_name_en"]
            legacy.name_ar = data["legacy_name_ar"]
            legacy.description_en = data["legacy_description_en"]
            legacy.description_ar = data["legacy_description_ar"]
            legacy.official_url = ""
            legacy.is_active = False
            legacy.save(update_fields=[
                "name_en", "name_ar", "description_en", "description_ar",
                "official_url", "is_active",
            ])
            ServiceActivity.objects.filter(service=legacy).delete()
            ServiceDependency.objects.filter(service=legacy).delete()
            ServiceRule.objects.filter(service=legacy).update(is_active=False)

            # The former R06 -> R05 link treated a commercial lease as a permit
            # prerequisite. No prerequisite is asserted for the split services.
            ServiceDependency.objects.filter(
                service__code__in=construction_codes
            ).delete()

        self.stdout.write(self.style.SUCCESS("Construction services imported."))
