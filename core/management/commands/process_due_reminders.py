from django.core.management.base import BaseCommand

from core.Services.compliance_service import (
    process_due_reminders,
    send_due_email_reminders,
)


class Command(BaseCommand):
    help = "Process due in-app and opted-in email compliance reminders."

    def handle(self, *args, **options):
        available_count = process_due_reminders()
        email_results = send_due_email_reminders()
        self.stdout.write(
            self.style.SUCCESS(
                f"Made {available_count} in-app reminder(s) available; "
                f"email reminders sent: {email_results['sent']}, "
                f"failed: {email_results['failed']}, "
                f"skipped (unverified or missing email): "
                f"{email_results['skipped']}."
            )
        )
