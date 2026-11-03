import json
from pathlib import Path

from django.conf import settings


def get_expiry_tracking_service_codes():
    path = (
        Path(settings.BASE_DIR)
        / "core"
        / "data"
        / "expiry_tracking_services.json"
    )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not load expiry-tracking service data: {exc}"
        ) from exc

    codes = data.get("service_codes")
    if not isinstance(codes, list) or not all(
        isinstance(code, str) and code.strip()
        for code in codes
    ):
        raise ValueError(
            "Expiry-tracking data must contain a list of service codes."
        )

    return {code.strip() for code in codes}
