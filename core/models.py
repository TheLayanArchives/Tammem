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

    expected_taxable_revenue_band = models.CharField(
        max_length=30,
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

    def __str__(self):
        return self.code
    scope = models.CharField(
    max_length=20,
    choices=[
        ("GENERAL", "General"),
        ("PROFILE", "Business Profile"),
        ("ACTIVITY", "Activity"),
    ],
    default="GENERAL",
    )
    activities = models.ManyToManyField(
        "Activity",
        blank=True,
        related_name="questions",
    )
  

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