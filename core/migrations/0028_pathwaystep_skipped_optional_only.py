from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_pathway_pathwayversion_pathwaystep_pathwaychangelog_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pathwaystep",
            name="status",
            field=models.CharField(
                choices=[
                    ("NOT_STARTED", "Not started"),
                    ("IN_PROGRESS", "In progress"),
                    ("COMPLETED", "Completed"),
                    ("BLOCKED", "Blocked"),
                    ("SKIPPED", "Skipped"),
                ],
                default="NOT_STARTED",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="pathwaystep",
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(status="SKIPPED")
                    | models.Q(mandatory_status="OPTIONAL")
                ),
                name="skipped_pathway_step_must_be_optional",
            ),
        ),
    ]
