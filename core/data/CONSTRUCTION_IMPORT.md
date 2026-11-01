# Construction pathway data

R06 was a combined construction/restoration placeholder. It is retained in the
28-service source catalogue and old snapshots for traceability, but import
commands mark it inactive and remove its pathway links. New pathways use
`BUILDING_PERMIT`, `BUILDING_RENOVATION`, or `BUILDING_MODIFICATION`.

The R06 dependency on R05 was removed. R05 is the documented commercial lease,
not an engineering-office prerequisite. The construction addition does not
specify prerequisites for the replacement services, so none are seeded.

The replacement services retain R06's four cafe activity links
(`CAFE_A`, `CAFE_B`, `CAFE_C`, and `CAFE_K`); the addition workbook does not
distinguish cafe types. Review this mapping if the services are later offered
outside the current cafe activities.

Construction question IDs use Q111–Q118 because Q103–Q105 are already assigned
to other active questions. Keep the addition-only source workbook unchanged.

After migrations and authority setup, apply the data in this order:

1. `python manage.py import_government_services --apply`
2. `python manage.py import_pathway_reference_data`
3. `python manage.py import_questions core/data/TAMMEM_Master_Questions_By_Scope.xlsx`
4. `python manage.py import_question_translations`
5. `python manage.py import_construction_reference_data --apply`
6. `python manage.py import_construction_question_rules --apply`
7. `python manage.py import_service_rules --apply`
8. `python manage.py import_service_dependencies --apply`

The service rules identify potential pathways. Their mandatory status remains
`UNDECIDED` until the permit triggers are verified with the authority.
