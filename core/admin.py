from django.contrib import admin
from .models import (
    Business,
    BusinessProfile,
    Location,
    Industry,
    Activity,  Question,
    QuestionOption,
    BusinessAnswer, QuestionRule,
    RuleCondition,
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
