"""CSV export helper (UTF-8 BOM so Excel opens Chinese text correctly)."""
import csv
import io
from datetime import datetime

from flask import Response


def csv_response(rows, columns, filename_prefix, summary_rows=None):
    """columns: list of (header, key-or-callable).

    ``summary_rows`` is written after an empty row and is calculated before
    applying the export row limit, keeping reports aligned with the API summary.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for header, _ in columns])
    for row in rows:
        writer.writerow([_resolve(row, accessor) for _, accessor in columns])

    if summary_rows:
        writer.writerow([])
        writer.writerow(["统计口径", "数值"])
        for label, value in summary_rows:
            writer.writerow([label, "" if value is None else value])

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
