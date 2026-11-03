import json
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from core.models import Business, Reminder, UserEmailVerification
from core.Services.email_verification_service import (
    confirm_email_verification,
    request_email_verification,
)
from core.Services.compliance_service import get_business_compliance_calendar
from core.Services.monitoring_summary import get_business_monitoring_summary
from core.Services.license_service import (
    create_license_record,
    list_license_record_data,
    serialize_license_record_data,
)
from core.Services.reminder_service import set_email_reminder_preference


@require_GET
def dashboard_due_reminders(request):
    """Return due in-app reminders for the authenticated user's businesses."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Authentication required."},
            status=401,
        )

    reminders = (
        Reminder.objects
        .filter(
            business__user=request.user,
            channel=Reminder.Channel.IN_APP,
            scheduled_for__lte=timezone.localdate(),
            compliance_event__status="OPEN",
        )
        .filter(Q(delivery_status=Reminder.DeliveryStatus.PENDING) |
                Q(delivery_status=Reminder.DeliveryStatus.AVAILABLE))
        .select_related(
            "business",
            "compliance_event",
            "compliance_event__license_record",
            "compliance_event__license_record__government_service",
        )
        .order_by("scheduled_for", "id")
    )

    results = []
    for reminder in reminders:
        license_record = reminder.compliance_event.license_record
        service = (
            license_record.government_service
            if license_record is not None
            else None
        )
        results.append({
            "id": reminder.pk,
            "business_id": reminder.business_id,
            "business_name": reminder.business.business_name,
            "event_type": reminder.compliance_event.event_type,
            "due_date": reminder.compliance_event.due_date.isoformat(),
            "scheduled_for": reminder.scheduled_for.isoformat(),
            "lead_days": reminder.lead_days,
            "license_type": (
                license_record.license_type
                if license_record is not None
                else None
            ),
            "service_code": service.code if service is not None else None,
            "service_name_en": service.name_en if service is not None else None,
        })

    return JsonResponse({"reminders": results})


@require_GET
def business_monitoring_summary(request, business_id):
    """Return an overview for one business owned by the signed-in user."""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    try:
        summary = get_business_monitoring_summary(
            actor=request.user,
            business_id=business_id,
        )
    except PermissionDenied:
        return JsonResponse({"detail": "Business not found."}, status=404)

    return JsonResponse(summary)


@require_GET
def business_compliance_calendar(request, business_id):
    """Return renewal calendar events for one owned business."""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    try:
        calendar = get_business_compliance_calendar(
            actor=request.user,
            business_id=business_id,
        )
    except PermissionDenied:
        return JsonResponse({"detail": "Business not found."}, status=404)

    return JsonResponse(calendar)


@require_http_methods(["GET", "POST"])
def business_licenses(request, business_id):
    """Return license metadata for one business owned by the user."""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    if request.method == "GET":
        try:
            data = list_license_record_data(
                actor=request.user,
                business_id=business_id,
            )
        except PermissionDenied:
            return JsonResponse({"detail": "Business not found."}, status=404)
        return JsonResponse(data)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Expected a JSON request body."}, status=400)

    allowed_fields = {
        "license_type",
        "issuing_authority",
        "identifier",
        "issue_date",
        "expiry_date",
        "government_service_id",
        "pathway_step_id",
    }
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "The request body must be a JSON object."}, status=400)
    unknown_fields = set(payload) - allowed_fields
    if unknown_fields:
        return JsonResponse({
            "detail": "Unknown fields in request.",
            "fields": sorted(str(field) for field in unknown_fields),
        }, status=400)

    license_type = payload.get("license_type")
    if not isinstance(license_type, str) or not license_type.strip():
        return JsonResponse({
            "errors": {"license_type": ["This field is required."]}
        }, status=400)

    parsed_values = {}
    for field in ("issuing_authority", "identifier"):
        value = payload.get(field, "")
        if not isinstance(value, str):
            return JsonResponse({
                "errors": {field: ["Enter a text value."]}
            }, status=400)
        parsed_values[field] = value

    for field in ("issue_date", "expiry_date"):
        value = payload.get(field)
        if value is None:
            parsed_values[field] = None
            continue
        if not isinstance(value, str):
            return JsonResponse({
                "errors": {field: ["Use a date in YYYY-MM-DD format."]}
            }, status=400)
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError:
            parsed_date = None
        if parsed_date is None or parsed_date.isoformat() != value:
            return JsonResponse({
                "errors": {field: ["Use a date in YYYY-MM-DD format."]}
            }, status=400)
        parsed_values[field] = parsed_date

    for field in ("government_service_id", "pathway_step_id"):
        value = payload.get(field)
        if value is None:
            parsed_values[field] = None
        elif type(value) is not int or value < 1:
            return JsonResponse({
                "errors": {field: ["Use a positive integer ID or null."]}
            }, status=400)
        else:
            parsed_values[field] = value

    try:
        record = create_license_record(
            actor=request.user,
            business_id=business_id,
            license_type=license_type,
            **parsed_values,
        )
    except PermissionDenied:
        return JsonResponse({"detail": "Business or pathway step not found."}, status=404)
    except ValidationError as error:
        errors = (
            error.message_dict
            if hasattr(error, "message_dict")
            else error.messages
        )
        return JsonResponse({"errors": errors}, status=400)

    return JsonResponse({
        "as_of": timezone.localdate().isoformat(),
        "license": serialize_license_record_data(record),
    }, status=201)


@require_http_methods(["GET", "PATCH"])
def business_email_reminder_preference(request, business_id):
    """Read or update the authenticated owner's email reminder opt-in."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"detail": "Authentication required."},
            status=401,
        )

    if request.method == "GET":
        business = Business.objects.filter(
            pk=business_id,
            user=request.user,
        ).first()
        if business is None:
            return JsonResponse({"detail": "Business not found."}, status=404)
        return JsonResponse({
            "business_id": business.pk,
            "email_reminders_enabled": business.email_reminders_enabled,
            "email_verified": UserEmailVerification.objects.filter(
                user=request.user,
                email=request.user.email.strip(),
                verified_at__isnull=False,
            ).exists(),
        })

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Expected a JSON request body."}, status=400)

    if (
        not isinstance(payload, dict)
        or set(payload) != {"email_reminders_enabled"}
        or not isinstance(payload["email_reminders_enabled"], bool)
    ):
        return JsonResponse({
            "detail": "Provide email_reminders_enabled as true or false."
        }, status=400)

    try:
        business = set_email_reminder_preference(
            actor=request.user,
            business_id=business_id,
            enabled=payload["email_reminders_enabled"],
        )
    except PermissionDenied:
        return JsonResponse({"detail": "Business not found."}, status=404)
    except ValidationError as error:
        return JsonResponse({"errors": error.messages}, status=400)

    return JsonResponse({
        "business_id": business.pk,
        "email_reminders_enabled": business.email_reminders_enabled,
        "email_verified": UserEmailVerification.objects.filter(
            user=request.user,
            email=request.user.email.strip(),
            verified_at__isnull=False,
        ).exists(),
    })


@require_http_methods(["POST"])
def request_account_email_verification(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    confirmation_url = request.build_absolute_uri(
        reverse("confirm-email-verification")
    )
    try:
        sent = request_email_verification(
            user=request.user,
            confirmation_url=confirmation_url,
        )
    except ValidationError as error:
        return JsonResponse({"errors": error.messages}, status=400)

    return JsonResponse({
        "detail": "Verification message processed by the configured email backend.",
        "sent": sent,
    })


@require_http_methods(["GET", "POST"])
def confirm_account_email_verification(request):
    if request.method == "GET":
        return render(
            request,
            "core/confirm_email_verification.html",
            {"token": request.GET.get("token", "")},
        )

    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"detail": "Expected a JSON request body."}, status=400)
        token = payload.get("token") if isinstance(payload, dict) else None
    else:
        token = request.POST.get("token")

    try:
        verification = confirm_email_verification(token=token)
    except ValidationError as error:
        return JsonResponse({"errors": error.messages}, status=400)

    return JsonResponse({
        "verified": True,
        "email": verification.email,
    })
