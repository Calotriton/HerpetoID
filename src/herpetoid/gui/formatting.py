"""How values are written on screen.

Only presentation lives here — nothing stored or exported is affected. Dates are shown day-first
(DD/MM/YYYY), the convention of the European fieldwork this application is built for; the database
keeps real ``date`` objects and the CSV/XLSX/PDF exports keep ISO-8601, which is what other software
expects to read.
"""

from __future__ import annotations

from datetime import date, datetime

#: Day-first date format as a Qt format string, for ``QDateEdit.setDisplayFormat``.
DATE_DISPLAY_FORMAT = "dd/MM/yyyy"

#: The same format spelled for :meth:`datetime.date.strftime`.
DATE_FORMAT = "%d/%m/%Y"


def format_date(value: date | datetime | None) -> str | None:
    """A date as DD/MM/YYYY, or ``None`` when there is nothing to show."""
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime(DATE_FORMAT)
    return str(value)
