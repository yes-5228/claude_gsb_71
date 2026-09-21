"""CSV export helper (UTF-8 BOM so Excel opens Chinese text correctly)."""
import csv
import io
from datetime import datetime

from flask import Response


def csv_response(rows, columns, filename_prefix, trailer=None):
    """columns: list of (header, key-or-callable).

    ``trailer`` optionally appends a summary block after a blank line:
    (title, [ (label, value), ... ]). It is used to embed the canonical
    compliance counters so an exported file can be reconciled with the
    on-screen cards/dashboard for the exact same filter scope.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for header, _ in columns])
    for row in rows:
        writer.writerow([_resolve(row, accessor) for _, accessor in columns])

    if trailer:
        title, entries = trailer
        writer.writerow([])
        writer.writerow([title])
        for label, value in entries:
            writer.writerow([label, value])

    filename = "%s_%s.csv" % (filename_prefix, datetime.now().strftime("%Y%m%d%H%M%S"))
    payload = "\ufeff" + buffer.getvalue()
    return Response(
        payload,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=%s" % filename},
    )


def _resolve(row, accessor):
    """Read a column from a model instance, a mapping or a callable."""
    value = accessor(row) if callable(accessor) else getattr(row, accessor, None)
    return "" if value is None else value
