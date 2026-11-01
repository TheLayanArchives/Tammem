from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from core.models import Question, QuestionOption


class Command(BaseCommand):
    help = "Import reviewed Arabic question text from the EN-AR workbook."

    def add_arguments(self, parser):
        parser.add_argument("excel_path", nargs="?", default=None)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate without saving changes.",
        )

    def handle(self, *args, **options):
        path = (
            Path(options["excel_path"])
            if options["excel_path"]
            else Path(__file__).resolve().parents[2]
            / "data"
            / "Questions_EN-AR (version 1).xlsx"
        )
        if not path.is_file():
            raise CommandError(f"Excel file not found: {path}")

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            if "Sheet1" not in workbook.sheetnames:
                raise CommandError("Missing worksheet: Sheet1")

            rows = workbook["Sheet1"].iter_rows(values_only=True)
            try:
                headers = [
                    str(value).strip() if value is not None else ""
                    for value in next(rows)
                ]
            except StopIteration:
                raise CommandError("The worksheet is empty.")

            required = {
                "Question ID",
                "Question EN",
                "Question AR(Final Version)",
            }
            missing = required - set(headers)
            if missing:
                raise CommandError(
                    f"Missing columns: {sorted(missing)}"
                )

            positions = {name: headers.index(name) for name in required}
            translations = {}
            for line, row in enumerate(rows, start=2):
                code = str(row[positions["Question ID"]] or "").strip()
                if not code:
                    continue
                if code in translations:
                    raise CommandError(
                        f"Duplicate question ID on Excel row {line}: {code}"
                    )

                text_en = str(
                    row[positions["Question EN"]] or ""
                ).strip()
                text_ar = str(
                    row[positions["Question AR(Final Version)"]] or ""
                ).strip()
                if not text_en or not text_ar:
                    raise CommandError(
                        f"Missing English or final Arabic text on row {line}: {code}"
                    )
                translations[code] = (text_en, text_ar)
        finally:
            workbook.close()

        questions = {item.code: item for item in Question.objects.all()}
        missing_questions = set(translations) - set(questions)
        missing_rows = set(questions) - set(translations)
        if missing_questions or missing_rows:
            raise CommandError(
                "Question IDs do not match the database. "
                f"Missing in database: {sorted(missing_questions)}; "
                f"missing in workbook: {sorted(missing_rows)}."
            )

        mismatched_english = sorted(
            code
            for code, (text_en, _) in translations.items()
            if questions[code].text_en.strip() != text_en
        )
        if mismatched_english:
            raise CommandError(
                "English text differs from the database for: "
                f"{mismatched_english}"
            )

        option_path = path.parent / "Tammem_Question_Option_Translations_Approved.xlsx"
        if not option_path.is_file():
            raise CommandError(
                f"Option translation workbook not found: {option_path}"
            )

        option_workbook = load_workbook(
            option_path, read_only=True, data_only=True
        )
        try:
            if "Option Translations" not in option_workbook.sheetnames:
                raise CommandError(
                    "Missing worksheet: Option Translations"
                )
            option_rows = option_workbook[
                "Option Translations"
            ].iter_rows(values_only=True)
            try:
                option_headers = [
                    str(value).strip() if value is not None else ""
                    for value in next(option_rows)
                ]
            except StopIteration:
                raise CommandError(
                    "The option translation worksheet is empty."
                )

            option_required = {
                "Question ID",
                "Option Code",
                "Option EN",
                "Option AR",
                "Review Status",
            }
            missing = option_required - set(option_headers)
            if missing:
                raise CommandError(
                    f"Missing option translation columns: {sorted(missing)}"
                )

            option_positions = {
                name: option_headers.index(name)
                for name in option_required
            }
            option_translations = {}
            for line, row in enumerate(option_rows, start=2):
                question_code = str(
                    row[option_positions["Question ID"]] or ""
                ).strip()
                option_code = str(
                    row[option_positions["Option Code"]] or ""
                ).strip()
                if not question_code or not option_code:
                    continue
                if str(
                    row[option_positions["Review Status"]] or ""
                ).strip().lower() != "approved":
                    continue
                key = (question_code, option_code)
                if key in option_translations:
                    raise CommandError(
                        f"Duplicate option translation on row {line}: "
                        f"{question_code}/{option_code}"
                    )
                label_en = str(
                    row[option_positions["Option EN"]] or ""
                ).strip()
                label_ar = str(
                    row[option_positions["Option AR"]] or ""
                ).strip()
                if not label_en or not label_ar:
                    raise CommandError(
                        f"Missing option text on row {line}: "
                        f"{question_code}/{option_code}"
                    )
                option_translations[key] = (label_en, label_ar)
        finally:
            option_workbook.close()

        updated = 0
        options_updated = 0
        options_skipped = 0
        with transaction.atomic():
            for code, (_, text_ar) in translations.items():
                question = questions[code]
                if question.text_ar != text_ar:
                    question.text_ar = text_ar
                    question.save(update_fields=["text_ar"])
                    updated += 1
            for (question_code, option_code), (
                label_en,
                label_ar,
            ) in option_translations.items():
                option = QuestionOption.objects.filter(
                    question__code=question_code,
                    code=option_code,
                ).first()
                if option is None:
                    options_skipped += 1
                    continue
                if option.label_en.strip() != label_en:
                    raise CommandError(
                        "Option English text differs from the database for "
                        f"{question_code}/{option_code}."
                    )
                if option.label_ar != label_ar:
                    option.label_ar = label_ar
                    option.save(update_fields=["label_ar"])
                    options_updated += 1
            if options["dry_run"]:
                transaction.set_rollback(True)

        verb = "Validated" if options["dry_run"] else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} Arabic translations for {len(translations)} "
                f"questions; {updated} {'would be ' if options['dry_run'] else ''}updated; "
                f"{options_updated} option labels {'would be ' if options['dry_run'] else ''}updated; "
                f"{options_skipped} approved option translations had no matching option."
            )
        )
