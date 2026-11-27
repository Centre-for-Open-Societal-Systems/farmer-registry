"""OAN year and date bounds, independent of the core code-list validator."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def check_domain_bounds(records, mnemonic, field_rules, say, today=None):
    today = today or date.today()
    field = (
        "year_of_acquisition"
        if mnemonic == "Land"
        else "collected_date"
        if mnemonic == "Livestock"
        else None
    )
    if field is None:
        return []
    label = say.label(field_rules.get(field, {}).get("label"), field)
    problems = []
    for record in records:
        value = record.get(field)
        if value is None or isinstance(value, str) and not value.strip():
            continue
        if mnemonic == "Land":
            try:
                number = Decimal(str(value))
                year = (
                    int(number)
                    if number.is_finite() and number == number.to_integral_value()
                    else None
                )
            except (InvalidOperation, ValueError, TypeError):
                year = None
            if year is None or not 1900 <= year <= today.year:
                problems.append(
                    say("rule_year_range", label=label, year=today.year)
                )
        else:
            if isinstance(value, datetime):
                parsed = value.date()
            elif isinstance(value, date):
                parsed = value
            else:
                try:
                    parsed = date.fromisoformat(str(value))
                except ValueError:
                    parsed = None
            if parsed is None:
                problems.append(say("rule_date", label=label, value=value))
            elif parsed > today:
                problems.append(say("rule_future_date", label=label))
    return problems
