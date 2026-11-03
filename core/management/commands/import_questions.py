from pathlib import Path
import re
from openpyxl import load_workbook
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Activity, Question, QuestionOption

TYPE_MAP = {
    'SINGLE_CHOICE': 'SINGLE', 'MULTI_SELECT': 'MULTIPLE',
    'MULTI_ACTIVITY_SELECT': 'MULTIPLE', 'BOOLEAN': 'BOOLEAN',
    'TEXT': 'TEXT', 'NUMBER': 'NUMBER', 'COUNTRY_SELECT': 'SINGLE',
    'ACTIVITY_SELECT': 'SINGLE', 'PROFESSION_SELECT': 'SINGLE',
    'LOCATION_SELECT': 'SINGLE', 'OWNER_PERCENTAGES': 'TEXT',
    'CURRENCY': 'DECIMAL', 'CURRENCY_RANGE': 'SINGLE',
}
REQUIRED_MODE_MAP = {
    'YES': 'YES',
    'NO': 'NO',
    'CONDITIONAL': 'CONDITIONAL',
    'DERIVED/CONDITIONAL': 'DERIVED_CONDITIONAL',
}
INACTIVE_QUESTION_CODES = {
    "Q097",
    "Q098",
    "Q099",
    "Q100",
    "Q101",
    "Q102",
}


def option_code(label):
    return re.sub(r'[^A-Z0-9]+', '_', label.upper()).strip('_')[:100]


class Command(BaseCommand):
    help = 'Import TAMMEM question catalogue from scoped Excel workbook.'

    def add_arguments(self, parser):
        parser.add_argument('excel_path', type=str)
        parser.add_argument('--dry-run', action='store_true', help='Validate without committing changes')

    def handle(self, *args, **kwargs):
        path = Path(kwargs['excel_path'])
        if not path.is_file():
            raise CommandError(f'Excel not found: {path}')
        wb = load_workbook(path, read_only=True, data_only=True)
        if 'Master Questions' not in wb:
            raise CommandError('Missing worksheet: Master Questions')
        records = wb['Master Questions'].iter_rows(values_only=True)
        headers = [str(h).strip() if h is not None else '' for h in next(records)]
        fields = ('Question ID', 'Question', 'Question Type', 'Required', 'Options / Source', 'Scope')
        missing = set(fields) - set(headers)
        if missing:
            raise CommandError(f'Missing columns: {sorted(missing)}')
        data = []
        seen = set()
        for line, values in enumerate(records, 2):
            row = dict(zip(headers, values))
            code = str(row['Question ID'] or '').strip()
            if not code:
                continue
            raw_type = str(row['Question Type'] or '').strip().upper()
            scope = str(row['Scope'] or '').strip().upper()
            raw_required = str(row['Required'] or '').strip().upper()
            if (
                code in seen
                or raw_type not in TYPE_MAP
                or scope not in {'GENERAL','PROFILE','ACTIVITY'}
                or raw_required not in REQUIRED_MODE_MAP
            ):
                raise CommandError(f'Invalid or duplicate code/type/scope on Excel row {line}: {code}')
            text_en = str(row['Question'] or '').strip()
            if not text_en:
                raise CommandError(f'Empty question text on row {line}')
            seen.add(code)
            data.append((line, code, raw_type, scope, text_en, raw_required, row))
        counts = {'GENERAL': 0, 'PROFILE': 0, 'ACTIVITY': 0}
        fixed_options = 0
        review = []
        with transaction.atomic():
            for line, code, raw_type, scope, text_en, raw_required, row in data:
                required = raw_required == 'YES'
                question_defaults = {
                    'text_en': text_en,
                    'question_type': TYPE_MAP[raw_type],
                    'scope': scope,
                    'is_required': required,
                    'required_mode': REQUIRED_MODE_MAP[raw_required],
                    'is_active': code not in INACTIVE_QUESTION_CODES,
                    'display_order': line - 1,
                }
                question = Question.objects.filter(code=code).first()
                if question is None:
                    question = Question.objects.create(
                        code=code,
                        text_ar='',
                        **question_defaults,
                    )
                else:
                    changed_fields = []
                    for field, value in question_defaults.items():
                        if getattr(question, field) != value:
                            setattr(question, field, value)
                            changed_fields.append(field)
                    if changed_fields:
                        question.save(update_fields=changed_fields)

                raw_activity_codes = str(
                    row.get('Activity Codes') or ''
                ).strip()
                if raw_activity_codes:
                    activity_codes = {
                        item.strip()
                        for item in raw_activity_codes.split(',')
                        if item.strip()
                    }
                    activities = list(
                        Activity.objects.filter(code__in=activity_codes)
                    )
                    found_codes = {activity.code for activity in activities}
                    missing_codes = activity_codes - found_codes
                    if missing_codes:
                        raise CommandError(
                            f'{code}: unknown Activity Codes '
                            f'{sorted(missing_codes)}'
                        )
                    question.activities.set(activities)
                counts[scope] += 1
                raw_options = str(row['Options / Source'] or '').strip()
                # Semicolons identify enumerated options in the catalogue; external sources are not fabricated.
                if raw_type in {'BOOLEAN','SINGLE_CHOICE','MULTI_SELECT','CURRENCY_RANGE'} and ';' in raw_options:
                    labels = [label.strip() for label in raw_options.split(';') if label.strip()]
                    for order, label in enumerate(labels, 1):
                        opt_code = option_code(label)
                        option_defaults = {
                            'label_en': label,
                            'value': opt_code,
                            'display_order': order,
                            'is_active': True,
                        }
                        option = QuestionOption.objects.filter(
                            question=question, code=opt_code
                        ).first()
                        if option is None:
                            QuestionOption.objects.create(
                                question=question,
                                code=opt_code,
                                label_ar='',
                                **option_defaults,
                            )
                        else:
                            changed_fields = []
                            for field, value in option_defaults.items():
                                if getattr(option, field) != value:
                                    setattr(option, field, value)
                                    changed_fields.append(field)
                            if changed_fields:
                                option.save(update_fields=changed_fields)
                        fixed_options += 1
                elif raw_type in {'SINGLE_CHOICE','MULTI_SELECT','COUNTRY_SELECT','ACTIVITY_SELECT',
                                   'MULTI_ACTIVITY_SELECT','PROFESSION_SELECT','LOCATION_SELECT','CURRENCY_RANGE'}:
                    review.append(f'{code}: requires external catalogue or reviewed options ({raw_options})')
            if kwargs['dry_run']:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f"{'Validated (no database changes)' if kwargs['dry_run'] else 'Imported'} {len(data)} questions: {counts}."))
        self.stdout.write(f'Fixed options processed: {fixed_options}')
        self.stdout.write('Not imported: dependency rules and external-catalogue options.')
        for item in review:
            self.stdout.write('REVIEW ' + item)
