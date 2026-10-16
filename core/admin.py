from django.contrib import admin
from .models import (
    Business,
    BusinessProfile,
    Location,
    Industry,
    Activity,  
    Question,
    QuestionOption,
    BusinessAnswer, 
    QuestionRule,
    RuleCondition,
    Authority,
    GovernmentService,
    ServiceRule,
    ServiceCondition,
    ServiceDependency
)

admin.site.register(Business)
admin.site.register(BusinessProfile)
admin.site.register(Location)
admin.site.register(Industry)
admin.site.register(Activity)
admin.site.register(Question)
admin.site.register(QuestionOption)
admin.site.register(BusinessAnswer)
admin.site.register(QuestionRule)
admin.site.register(RuleCondition)

# Register your models here.
@admin.register(Authority)
class AuthorityAdmin(admin.ModelAdmin):
    list_display = ("code", "name_en", "name_ar")
    search_fields = ("code", "name_en", "name_ar")

@admin.register(GovernmentService)
class GovernmentServiceAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name_en",
        "authority",
        "is_active",
    )

    search_fields = (
        "code",
        "name_en",
        "name_ar",
    )

    list_filter = (
        "authority",
        "is_active",
    )

@admin.register(ServiceRule)
class ServiceRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service",
        "logic",
        "is_active",
    )

    list_filter = (
        "logic",
        "is_active",
    )


@admin.register(ServiceCondition)
class ServiceConditionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "rule",
        "source",
        "question",
        "field_name",
        "operator",
        "expected_value",
    )

    list_filter = (
        "source",
        "operator",
    )

    search_fields = (
        "question__code",
        "rule__service__code",
    )

@admin.register(ServiceDependency)
class ServiceDependencyAdmin(admin.ModelAdmin):

    list_display = (
        "service",
        "prerequisite",
    )

    search_fields = (
        "service__code",
        "service__name_en",
        "prerequisite__code",
        "prerequisite__name_en",
    )