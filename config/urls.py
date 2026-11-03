"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from core.views import (
    business_email_reminder_preference,
    business_compliance_calendar,
    business_monitoring_summary,
    business_licenses,
    confirm_account_email_verification,
    dashboard_due_reminders,
    request_account_email_verification,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'api/dashboard/reminders/',
        dashboard_due_reminders,
        name='dashboard-due-reminders',
    ),
    path(
        'api/businesses/<int:business_id>/reminder-preference/',
        business_email_reminder_preference,
        name='business-reminder-preference',
    ),
    path(
        'api/businesses/<int:business_id>/monitoring/',
        business_monitoring_summary,
        name='business-monitoring-summary',
    ),
    path(
        'api/businesses/<int:business_id>/compliance-events/',
        business_compliance_calendar,
        name='business-compliance-calendar',
    ),
    path(
        'api/businesses/<int:business_id>/licenses/',
        business_licenses,
        name='business-licenses',
    ),
    path(
        'api/account/email-verification/',
        request_account_email_verification,
        name='request-email-verification',
    ),
    path(
        'api/account/email-verification/confirm/',
        confirm_account_email_verification,
        name='confirm-email-verification',
    ),
]
