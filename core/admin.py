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
    ServiceDependency,
    ServiceActivity,
    ServiceMandatoryRule,
    ServiceMandatoryCondition,
    Pathway,
    PathwayVersion,
    PathwayStep,
    PathwayChangeLog,
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

@admin.register(ServiceActivity)
class ServiceActivityAdmin(admin.ModelAdmin):
    list_display = ("service", "activity")
    search_fields = (
        "service__code",
        "activity__code",
    )


# Manage mandatory rules in Django Admin
@admin.register(ServiceMandatoryRule)
class ServiceMandatoryRuleAdmin(admin.ModelAdmin):
    list_display = (
        "service",
        "result_status",
        "priority",
        "is_active",
    )

    list_filter = (
        "result_status",
        "is_active",
    )

    search_fields = (
        "service__code",
        "service__name_en",
    )


# Manage conditions for mandatory rules
@admin.register(ServiceMandatoryCondition)
class ServiceMandatoryConditionAdmin(admin.ModelAdmin):
    list_display = (
        "rule",
        "field_name",
        "operator",
        "expected_value",
    )

    list_filter = (
        "field_name",
        "operator",
    )


# Version history is read-only in Admin;
# changes go through the service layer.


class PathwayVersionInline(admin.TabularInline):
    model = PathwayVersion
    extra = 0

    fields = (
        "version_number",
        "profile_version",
        "reason",
        "created_at",
    )

    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(Pathway)
class PathwayAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "business_profile",
        "status",
        "current_version",
        "updated_at",
    )

    list_filter = ("status",)

    readonly_fields = (
        "business_profile",
        "status",
        "current_version",
        "created_at",
        "updated_at",
    )

    inlines = (PathwayVersionInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PathwayStepInline(admin.TabularInline):
    model = PathwayStep
    extra = 0

    fields = (
        "order",
        "service",
        "status",
        "mandatory_status",
        "completed_at",
    )

    readonly_fields = fields
    can_delete = False


@admin.register(PathwayVersion)
class PathwayVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "pathway",
        "version_number",
        "profile_version",
        "reason",
        "created_at",
    )

    readonly_fields = (
        "pathway",
        "version_number",
        "profile_version",
        "reason",
        "generation_snapshot",
        "generation_hash",
        "created_at",
    )

    inlines = (PathwayStepInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PathwayStep)
class PathwayStepAdmin(admin.ModelAdmin):
    list_display = (
        "version",
        "order",
        "service",
        "status",
        "completed_at",
    )

    list_filter = (
        "status",
        "mandatory_status",
    )

    search_fields = (
        "service__code",
        "version__pathway__business_profile__business__business_name",
    )

    readonly_fields = [
        f.name for f in PathwayStep._meta.fields
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PathwayChangeLog)
class PathwayChangeLogAdmin(admin.ModelAdmin):
    list_display = (
        "pathway",
        "version",
        "action",
        "service_code",
        "changed_by",
        "created_at",
    )

    list_filter = ("action",)

    readonly_fields = [
        f.name for f in PathwayChangeLog._meta.fields
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
