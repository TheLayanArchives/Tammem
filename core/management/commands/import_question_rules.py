from pathlib import Path
from openpyxl import load_workbook
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Question, QuestionRule, RuleCondition

# Explicitly reviewed single-parent dependencies only.
# Expected values are stored answer values, not Excel descriptions.
# BOOLEAN questions must be saved in BusinessAnswer.boolean_value.
REVIEWED = {
    ('Q001', 'Q002'): ('EQUALS', 'SAUDI_INDIVIDUAL'),
    ('Q001', 'Q003'): ('EQUALS', 'SAUDI_INDIVIDUAL'),
    ('Q001', 'Q004'): ('IN', ('GCC_INDIVIDUAL', 'FOREIGN_INDIVIDUAL')),
    ('Q001', 'Q005'): ('EQUALS', 'FOREIGN_INDIVIDUAL'),
    ('Q008', 'Q009'): ('EQUALS', 'COMPANY'),
    ('Q008', 'Q010'): ('EQUALS', 'BRANCH_OF_AN_EXISTING_COMPANY'),
    ('Q053', 'Q054'): ('EQUALS', 'true'),
    ('Q054', 'Q055'): ('EQUALS', 'true'),
    ('Q053', 'Q056'): ('EQUALS', 'true'),
    ('Q053', 'Q057'): ('EQUALS', 'true'),
    ('Q053', 'Q058'): ('EQUALS', 'true'),
    ('Q053', 'Q059'): ('EQUALS', 'true'),
    ('Q060', 'Q061'): ('EQUALS', 'true'),
    ('Q060', 'Q062'): ('EQUALS', 'true'),
    ('Q060', 'Q063'): ('EQUALS', 'true'),
    ('Q066', 'Q067'): ('EQUALS', 'true'),
    ('Q070', 'Q071'): ('EQUALS', 'true'),
    ('Q092', 'Q093'): ('EQUALS', 'true'),
}

class Command(BaseCommand):
    help = 'Import explicitly reviewed TAMMEM dependency rules; report unreviewed rows.'

    def add_arguments(self, parser):
        parser.add_argument('excel_path')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        path = Path(opts['excel_path'])
        if not path.is_file():
            raise CommandError(f'Excel not found: {path}')
        wb = load_workbook(path, read_only=True, data_only=True)
        if 'Question Dependencies' not in wb.sheetnames:
            raise CommandError('Missing Question Dependencies worksheet')
        rows = list(wb['Question Dependencies'].values)
        if tuple(rows[0][:3]) != ('Parent Question', 'Child Question', 'Trigger Condition'):
            raise CommandError('Unexpected dependency worksheet headers')
        pairs = {(str(r[0]).strip(), str(r[1]).strip()) for r in rows[1:] if r[0] and r[1]}
        missing = set(REVIEWED) - pairs
        if missing:
            raise CommandError(f'Reviewed mappings absent from Excel: {sorted(missing)}')
        created = 0
        existing = 0
        with transaction.atomic():
            for (parent_code, child_code), (operator, value) in REVIEWED.items():
                parent = Question.objects.get(code=parent_code)
                child = Question.objects.get(code=child_code)
                # Never modify an existing rule set without reviewing it.
                rules = list(child.rules.all())
                if rules:
                    matches = any(
                        len(list(rule.conditions.all())) == 1
                        and rule.logic == 'ALL'
                        and rule.conditions.first().source == 'ANSWER'
                        and rule.conditions.first().depends_on_question_id == parent.pk
                        and rule.conditions.first().operator == operator
                        and rule.conditions.first().expected_value == value
                        for rule in rules
                    ) if operator != 'IN' else False
                    if matches:
                        existing += 1
                        continue
                    raise CommandError(f'{child_code} already has rules; review manually before import')
                if operator == 'IN':
                    # Multiple rules implement OR; each contains one EQUALS condition.
                    for choice in value:
                        rule = QuestionRule.objects.create(target_question=child, logic='ALL')
                        RuleCondition.objects.create(rule=rule, source='ANSWER', depends_on_question=parent, operator='EQUALS', expected_value=choice)
                else:
                    rule = QuestionRule.objects.create(target_question=child, logic='ALL')
                    RuleCondition.objects.create(rule=rule, source='ANSWER', depends_on_question=parent, operator=operator, expected_value=value)
                created += 1
            if opts['dry_run']:
                transaction.set_rollback(True)
        self.stdout.write(f'{"Validated" if opts["dry_run"] else "Imported"}: {created} new target mappings, {existing} already present.')
        self.stdout.write(f'Unreviewed Excel dependencies: {len(pairs - set(REVIEWED))}; NOT imported.')
        for parent, child in sorted(pairs - set(REVIEWED)):
            self.stdout.write(f'REVIEW {parent} -> {child}')
