from django.conf import settings
from django.db import models


class Business(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="businesses",
    )

    business_name = models.CharField(
        max_length=200,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        default="DRAFT",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.business_name or f"Business {self.pk}"

class BusinessProfile(models.Model):
    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    applicant_type = models.CharField(max_length=40)

    is_adult = models.BooleanField(null=True, blank=True)
    is_government_employee = models.BooleanField(null=True, blank=True)

    nationality_country_code = models.CharField(
        max_length=2,
        null=True,
        blank=True,
    )

    saudi_status = models.CharField(
        max_length=40,
        null=True,
        blank=True,
    )

    has_investment_registration = models.BooleanField(
        null=True,
        blank=True,
    )

    business_structure = models.CharField(max_length=30)

    company_form = models.CharField(
        max_length=40,
        null=True,
        blank=True,
    )

    operating_model = models.CharField(max_length=40)

    has_ecommerce = models.BooleanField(default=False)

    has_employees = models.BooleanField(default=False)

    has_non_saudi_employees = models.BooleanField(
        null=True,
        blank=True,
    )

    direct_importer = models.BooleanField(
        null=True,
        blank=True,
    )

    is_manufacturer = models.BooleanField(default=False)

    needs_sector_license = models.BooleanField(
        null=True,
        blank=True,
    )

    
    REVENUE_BAND_CHOICES = [
        ("LOW", "SAR 187,500 or less"),
        ("MEDIUM", "Above SAR 187,500 and below SAR 375,000"),
        ("HIGH", "SAR 375,000 or more"),
    ]

    expected_taxable_revenue_band = models.CharField(
        max_length=30,
        choices=REVENUE_BAND_CHOICES,
        null=True,
        blank=True,
    )


    profile_version = models.PositiveIntegerField(default=1)

    updated_at = models.DateTimeField(auto_now=True)

    location = models.ForeignKey(
        "Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_profiles",
    )

    activity = models.ForeignKey(
        "Activity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="business_profiles",
    )


class Location(models.Model):
    region_name_ar = models.CharField(max_length=120)
    region_name_en = models.CharField(max_length=120)

    city_name_ar = models.CharField(max_length=120)
    city_name_en = models.CharField(max_length=120)

    municipality_code = models.CharField(
        max_length=80,
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.city_name_en

class Industry(models.Model):
    code = models.CharField(
        max_length=80,
        unique=True,
    )

    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name_en

class Activity(models.Model):
    industry = models.ForeignKey(
        Industry,
        on_delete=models.PROTECT,
        related_name="activities",
    )

    code = models.CharField(
        max_length=80,
        unique=True,
    )

    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200)

    parent_activity = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_activities",
    )

    official_activity_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name_en


class Question(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
    )

    text_ar = models.TextField()
    text_en = models.TextField()

    # Supported answer storage types
    QUESTION_TYPES = [
        ("BOOLEAN", "Yes / No"),
        ("SINGLE", "Single choice"),
        ("MULTIPLE", "Multiple choice"),
        ("TEXT", "Text"),
        ("NUMBER", "Number"),
        ("DECIMAL", "Decimal"),
        ("DATE", "Date"),
    ]

    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES,
    )

    # Original question type from Excel
    # Example: COUNTRY_SELECT, LOCATION_SELECT
    input_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    # Original required status from Excel
    REQUIRED_MODE_CHOICES = [
        ("YES", "Always required"),
        ("NO", "Optional"),
        ("CONDITIONAL", "Conditionally required"),
        (
            "DERIVED_CONDITIONAL",
            "Derived / Conditionally required",
        ),
    ]

    required_mode = models.CharField(
        max_length=30,
        choices=REQUIRED_MODE_CHOICES,
        null=True,
        blank=True,
    )

    help_text_ar = models.TextField(
        null=True,
        blank=True,
    )

    help_text_en = models.TextField(
        null=True,
        blank=True,
    )

    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    display_order = models.PositiveIntegerField(default=0)

    # Question scope
    scope = models.CharField(
        max_length=20,
        choices=[
            ("GENERAL", "General"),
            ("PROFILE", "Business Profile"),
            ("ACTIVITY", "Activity"),
        ],
        default="GENERAL",
    )

    # Related business activities
    activities = models.ManyToManyField(
        "Activity",
        blank=True,
        related_name="questions",
    )

    def __str__(self):
        return self.code

  

class QuestionOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
    )

    code = models.CharField(max_length=100)

    label_ar = models.CharField(max_length=200)
    label_en = models.CharField(max_length=200)

    value = models.CharField(max_length=200)

    display_order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["question", "code"],
                name="unique_question_option_code",
            )
        ]
        ordering = ["display_order"]

    def __str__(self):
        return self.label_en

class BusinessAnswer(models.Model):
    business_profile = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name="answers",
    )

    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="business_answers",
    )

    selected_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="business_answers",
    )

    # Stores multiple selected options for MULTIPLE questions
    selected_options = models.ManyToManyField(
        "QuestionOption",
        blank=True,
        related_name="multiple_business_answers"
    )

    text_value = models.TextField(
        null=True,
        blank=True,
    )

    boolean_value = models.BooleanField(
        null=True,
        blank=True,
    )

    integer_value = models.IntegerField(
        null=True,
        blank=True,
    )

    decimal_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )

    date_value = models.DateField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business_profile", "question"],
                name="unique_business_profile_question",
            )
        ]

    def __str__(self):
        return f"{self.business_profile} - {self.question}"

class QuestionRule(models.Model):
    target_question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="rules",
    )

    LOGIC_CHOICES = [
        ("ALL", "All conditions must match"),
        ("ANY", "Any condition can match"),
    ]

    logic = models.CharField(
        max_length=10,
        choices=LOGIC_CHOICES,
        default="ALL",
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Rule → {self.target_question.code}"

class RuleCondition(models.Model):
    rule = models.ForeignKey(
        QuestionRule,
        on_delete=models.CASCADE,
        related_name="conditions",
    )

    source = models.CharField(
        max_length=20,
        choices=[
            ("ANSWER", "Business Answer"),
            ("INDUSTRY", "Industry"),
            ("ACTIVITY", "Activity"),
        ],
        default="ANSWER",
    )

    depends_on_question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="rule_conditions",
        null=True,
        blank=True,
    )

    OPERATOR_CHOICES = [
        ("EQUALS", "Equals"),
        ("NOT_EQUALS", "Does not equal"),
        ("CONTAINS", "Contains"),
        ("GREATER_THAN", "Greater than"),
        ("LESS_THAN", "Less than"),
    ]

    operator = models.CharField(
        max_length=30,
        choices=OPERATOR_CHOICES,
    )

    expected_value = models.CharField(
        max_length=200,
    )

    def __str__(self):
        if self.source == "ANSWER" and self.depends_on_question:
            left_side = self.depends_on_question.code
        elif self.source == "INDUSTRY":
            left_side = "INDUSTRY"
        elif self.source == "ACTIVITY":
            left_side = "ACTIVITY"
        else:
            left_side = self.source

        return f"{left_side} {self.operator} {self.expected_value}"

#-------------------------------------------#
#              SHOUQ: New CODEEE            #
#-------------------------------------------#  
class Authority(models.Model):
    # Unique code for each government authority
    code = models.CharField(max_length=50, unique=True)

    # Government authority name in English
    name_en = models.CharField(max_length=200)

    # Government authority name in Arabic
    name_ar = models.CharField(max_length=200)

    def __str__(self):
        return self.name_en

class GovernmentService(models.Model):
    # Unique identifier for each government service
    code = models.CharField(
        max_length=50,
        unique=True
    )

    # Service names
    name_ar = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)

    # Service descriptions
    description_ar = models.TextField(blank=True)
    description_en = models.TextField(blank=True)

    # Government authority responsible for the service
    authority = models.ForeignKey(
        Authority,
        on_delete=models.PROTECT,
        related_name="services"
    )

    # Official government service URL
    official_url = models.URLField(
        blank=True,
        null=True
    )

    # Whether the service is active in the system
    is_active = models.BooleanField(default=True)

    
    # Defines whether the service is mandatory or optional
    


    MANDATORY_CHOICES = [
        ("REQUIRED", "Required"),
        ("OPTIONAL", "Optional"),
        ("CONDITIONAL", "Conditional"),
        ("UNDECIDED", "Undecided - Needs Review"),
    ]

    mandatory_status = models.CharField(
        max_length=20,
        choices=MANDATORY_CHOICES,
        default="OPTIONAL"
    )

    # Defines when the service should appear
    APPLICABILITY_CHOICES = [
        ("ALWAYS", "Always Applicable"),
        ("CONDITIONAL", "Conditionally Applicable"),
    ]

    applicability = models.CharField(
        max_length=20,
        choices=APPLICABILITY_CHOICES,
        default="CONDITIONAL"
    )


    def __str__(self):
        return f"{self.code} - {self.name_en}"

    
class ServiceRule(models.Model):

    # Government service associated with this rule
    service = models.ForeignKey(
        GovernmentService,
        on_delete=models.CASCADE,
        related_name="rules"
    )

    # Logic used to evaluate conditions
    LOGIC_CHOICES = [
        ("ALL", "All conditions must match"),
        ("ANY", "At least one condition must match"),
    ]

    logic = models.CharField(
        max_length=10,
        choices=LOGIC_CHOICES,
        default="ALL"
    )

    # Enable or disable this rule
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Rule {self.pk} - {self.service.code}"

    

class ServiceCondition(models.Model):

    
    SOURCE_CHOICES = [
        ("ANSWER", "Business Answer"),
        ("ACTIVITY", "Business Activity"),
        ("INDUSTRY", "Business Industry"),
        ("LOCATION", "Business Location"),
        ("PROFILE_FIELD", "Business Profile Field"),
    ]


    OPERATOR_CHOICES = [
        ("EQUALS", "Equals"),
        ("NOT_EQUALS", "Does not equal"),
        ("CONTAINS", "Contains"),
        ("GREATER_THAN", "Greater than"),
        ("LESS_THAN", "Less than"),
    ]

    # Rule that contains this condition
    rule = models.ForeignKey(
        ServiceRule,
        on_delete=models.CASCADE,
        related_name="conditions"
    )

    # Source of the value being evaluated
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES
    )

    # Used when source is ANSWER
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="service_conditions"
    )

    # Used for location fields
    field_name = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # Comparison operation
    operator = models.CharField(
        max_length=30,
        choices=OPERATOR_CHOICES
    )

    # Expected value for comparison
    expected_value = models.CharField(
        max_length=200
    )

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        if self.source == "ANSWER":
            if not self.question_id:
                raise ValidationError({
                    "question": "Select a question for ANSWER conditions."
                })

            if self.field_name:
                raise ValidationError({
                    "field_name": "Leave this empty for ANSWER conditions."
                })

        else:
            if self.question_id:
                raise ValidationError({
                    "question": "Question is only allowed for ANSWER conditions."
                })

            
            if self.source == "LOCATION":
                allowed_fields = [
                    "city_name_en",
                    "region_name_en",
                    "municipality_code",
                ]

                if self.field_name not in allowed_fields:
                    raise ValidationError({
                        "field_name": "Select a supported location field."
                    })

            # NEW: Allow conditions based on BusinessProfile
            elif self.source == "PROFILE_FIELD":
                allowed_fields = [
                    "has_employees",
                    "has_ecommerce",
                    "direct_importer",
                    "is_manufacturer",
                    "expected_taxable_revenue_band",
                ]

                if self.field_name not in allowed_fields:
                    raise ValidationError({
                        "field_name": "Select a supported profile field."
                    })

            elif self.field_name:
                raise ValidationError({
                    "field_name": "Leave this empty for this source."
                })


    def __str__(self):
        return (
            f"{self.source} "
            f"{self.operator} "
            f"{self.expected_value}"
        )


class ServiceMandatoryRule(models.Model):
    # Service whose mandatory status depends on a condition
    service = models.ForeignKey(
        GovernmentService,
        on_delete=models.CASCADE,
        related_name="mandatory_rules"
    )

    # Mandatory status when the condition matches
    RESULT_CHOICES = [
        ("REQUIRED", "Required"),
        ("OPTIONAL", "Optional"),
        ("NOT_REQUIRED", "Not Required"),
    ]

    result_status = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES
    )

    # Lower number means higher priority
    priority = models.PositiveIntegerField(default=10)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return (
            f"{self.service.code} - "
            f"{self.result_status}"
        )


class ServiceMandatoryCondition(models.Model):

    # The mandatory rule that owns this condition
    rule = models.ForeignKey(
        ServiceMandatoryRule,
        on_delete=models.CASCADE,
        related_name="conditions"
    )

    # BusinessProfile field used in the condition
    field_name = models.CharField(max_length=50)

    OPERATOR_CHOICES = [
        ("EQUALS", "Equals"),
        ("GREATER_THAN", "Greater than"),
        ("GREATER_THAN_OR_EQUAL", "Greater than or equal"),
        ("LESS_THAN", "Less than"),
        ("LESS_THAN_OR_EQUAL", "Less than or equal"),
    ]

    operator = models.CharField(
        max_length=30,
        choices=OPERATOR_CHOICES
    )

    # Value to compare against
    expected_value = models.CharField(max_length=200)

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        allowed_fields = {
            "has_employees",
            "has_ecommerce",
            "direct_importer",
            "is_manufacturer",
            "expected_taxable_revenue_band",
        }

        if self.field_name not in allowed_fields:
            raise ValidationError({
                "field_name": "Select a supported profile field."
            })

    def __str__(self):
        return (
            f"{self.field_name} "
            f"{self.operator} "
            f"{self.expected_value}"
        )


class ServiceDependency(models.Model):

    # The service that requires another service first
    service = models.ForeignKey(
        GovernmentService,
        on_delete=models.CASCADE,
        related_name="dependencies"
    )

    # The service that must be completed beforehand
    prerequisite = models.ForeignKey(
        GovernmentService,
        on_delete=models.PROTECT,
        related_name="required_by"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service", "prerequisite"],
                name="unique_service_dependency"
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        if (
            self.service_id
            and self.prerequisite_id
            and self.service_id == self.prerequisite_id
        ):
            raise ValidationError(
                "A service cannot depend on itself."
            )

    def __str__(self):
        return (
            f"{self.service.code} requires "
            f"{self.prerequisite.code}"
        )

 
class ServiceActivity(models.Model):
    # Government service
    service = models.ForeignKey(
        GovernmentService,
        on_delete=models.CASCADE,
        related_name="service_activities"
    )

    # Business activity (cafe type)
    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name="service_activities"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service", "activity"],
                name="unique_service_activity"
            )
        ]

    def __str__(self):
        return f"{self.service.code} - {self.activity.code}"


# ==============================================================
# Persisted, versioned business pathways (does not change rules).
# ==============================================================

class Pathway(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ARCHIVED = "ARCHIVED", "Archived"

    business_profile = models.OneToOneField(
        BusinessProfile,
        on_delete=models.PROTECT,
        related_name="pathway"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    current_version = models.ForeignKey(
        "PathwayVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_pathways",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pathway for profile {self.business_profile_id}"


class PathwayVersion(models.Model):
    class Reason(models.TextChoices):
        INITIAL = "INITIAL", "Initial generation"
        PROFILE_CHANGED = "PROFILE_CHANGED", "Profile updated"
        RULES_CHANGED = "RULES_CHANGED", "Government rules updated"
        MANUAL_REVIEW = "MANUAL_REVIEW", "Manual review"

    pathway = models.ForeignKey(
        Pathway,
        on_delete=models.CASCADE,
        related_name="versions"
    )

    version_number = models.PositiveIntegerField()
    profile_version = models.PositiveIntegerField()

    reason = models.CharField(
        max_length=25,
        choices=Reason.choices
    )

    # Frozen generation output for audits.
    generation_snapshot = models.JSONField(default=dict)
    generation_hash = models.CharField(max_length=64)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["pathway", "version_number"],
                name="unique_pathway_version_number"
            ),
        ]

    def __str__(self):
        return f"Pathway {self.pathway_id} v{self.version_number}"


class PathwayStep(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        BLOCKED = "BLOCKED", "Blocked"

    version = models.ForeignKey(
        PathwayVersion,
        on_delete=models.CASCADE,
        related_name="steps"
    )

    service = models.ForeignKey(
        GovernmentService,
        on_delete=models.PROTECT,
        related_name="pathway_steps"
    )

    order = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED
    )

    mandatory_status = models.CharField(max_length=25)
    step_type = models.CharField(max_length=20, default="SERVICE")

    # Preserve service information from this version.
    service_code_snapshot = models.CharField(max_length=50)
    service_name_ar_snapshot = models.CharField(max_length=255)
    service_name_en_snapshot = models.CharField(max_length=255)

    official_url_snapshot = models.URLField(
        null=True,
        blank=True
    )

    warnings = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "service"],
                name="unique_pathway_version_service"
            ),
            models.UniqueConstraint(
                fields=["version", "order"],
                name="unique_pathway_version_order"
            ),
            models.CheckConstraint(
                condition=models.Q(order__gte=1),
                name="pathway_step_order_positive"
            ),
        ]

    def __str__(self):
        return (
            f"v{self.version_id} "
            f"#{self.order} {self.service_code_snapshot}"
        )


class PathwayChangeLog(models.Model):
    class Action(models.TextChoices):
        VERSION_CREATED = "VERSION_CREATED", "Version created"
        STEP_ADDED = "STEP_ADDED", "Step added"
        STEP_REMOVED = "STEP_REMOVED", "Step removed from new version"
        STEP_REORDERED = "STEP_REORDERED", "Step reordered"
        STEP_STATUS_CHANGED = "STEP_STATUS_CHANGED", "Step status changed"

    pathway = models.ForeignKey(
        Pathway,
        on_delete=models.CASCADE,
        related_name="change_logs"
    )

    version = models.ForeignKey(
        PathwayVersion,
        on_delete=models.CASCADE,
        related_name="change_logs"
    )

    action = models.CharField(
        max_length=25,
        choices=Action.choices
    )

    service_code = models.CharField(max_length=50, blank=True)
    details = models.JSONField(default=dict)

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pathway_changes"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} in v{self.version_id}"
