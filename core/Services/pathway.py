
from collections import defaultdict
from core.models import ServiceDependency
from core.models import ServiceActivity


def order_services_by_dependencies(services):
    """
    Order services so prerequisites appear first.
    """

    services_by_code = {
        service.code: service
        for service in services
    }

    selected_codes = set(services_by_code)

    dependencies = ServiceDependency.objects.filter(
        service__code__in=selected_codes
    ).select_related("service", "prerequisite")

    graph = defaultdict(list)
    indegree = {code: 0 for code in selected_codes}
    missing_dependencies = []

    for dependency in dependencies:
        service_code = dependency.service.code
        prerequisite_code = dependency.prerequisite.code

        if prerequisite_code not in selected_codes:
            missing_dependencies.append(
                (service_code, prerequisite_code)
            )
            continue

        graph[prerequisite_code].append(service_code)
        indegree[service_code] += 1

    # Start with services that have no prerequisites
    ready = sorted(
        code for code, degree in indegree.items()
        if degree == 0
    )

    ordered_codes = []

    while ready:
        code = ready.pop(0)
        ordered_codes.append(code)

        for dependent_code in sorted(graph[code]):
            indegree[dependent_code] -= 1

            if indegree[dependent_code] == 0:
                ready.append(dependent_code)
                ready.sort()

    if len(ordered_codes) != len(selected_codes):
        raise ValueError(
            "Circular dependency detected in selected services."
        )

    ordered_services = [
        services_by_code[code]
        for code in ordered_codes
    ]

    return {
        "ordered_services": ordered_services,
        "missing_dependencies": missing_dependencies,
    }


from core.service_eligibility import (
    get_applicable_services,
    get_service_mandatory_status,
)


def generate_business_pathway(business_profile):
    """
    Generate an eligibility-based pathway for a business.
    """

    
    # Step 1: Evaluate service eligibility
    eligibility = get_applicable_services(business_profile)

    # Step 2: Get services linked to the selected cafe type
    allowed_service_codes = set(
        ServiceActivity.objects.filter(
            activity=business_profile.activity
        ).values_list("service__code", flat=True)
    )

    # Step 3: Keep applicable services for this cafe type
    applicable_services = [
        service
        for service in eligibility["applicable"]
        if service.code in allowed_service_codes
    ]

    # Step 4: Order services by dependencies
    result = order_services_by_dependencies(
        applicable_services
    )


    # Step 3: Prepare pathway steps
    steps = []

    for position, service in enumerate(
        result["ordered_services"], start=1
    ):
        steps.append({
            "order": position,
            "service_code": service.code,
            "service_name_ar": service.name_ar,
            "service_name_en": service.name_en,
            "mandatory_status": get_service_mandatory_status(
                service, business_profile
            ),
            "official_url": service.official_url,
        })

    
    # Identify unresolved prerequisites
    missing_dependencies = result["missing_dependencies"]

    # Temporary project decision:
    # R18 remains a guidance step until its dependency is reviewed.
    guidance_services = {"R18"}

    for step in steps:
        step["step_type"] = (
            "GUIDANCE"
            if step["service_code"] in guidance_services
            else "SERVICE"
        )

        step["warnings"] = []

        for service_code, prerequisite_code in missing_dependencies:
            if service_code == step["service_code"]:
                step["warnings"].append(
                    f"Unresolved prerequisite: {prerequisite_code}"
                )

        if step["service_code"] == "R18":
            step["warnings"].append(
                "Guidance only: R18 applicability and "
                "dependency on R16 require review."
            )

    return {
        "steps": steps,
       
        "unknown_services": [
            service.code
            for service in eligibility["unknown"]
            if service.code in allowed_service_codes
        ],
        "not_applicable_services": sorted(set(
            service.code
            for service in eligibility["not_applicable"]
        ) | {
            service.code
            for group in eligibility.values()
            for service in group
            if service.code not in allowed_service_codes
        }),

        "missing_dependencies": missing_dependencies,
        "has_unresolved_dependencies": bool(missing_dependencies),
    }

