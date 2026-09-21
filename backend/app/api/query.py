"""数据查询 API: 条件检索 / 聚合统计 / 导出."""
from flask import Blueprint, current_app, request

from ..domain.constants import DATA_SOURCE_LABELS, PERIOD_LABELS, STATION_TYPE_LABELS
from ..domain.standards import POLLUTANTS
from ..services import query_service
from ..utils.pagination import paginate_query

bp = Blueprint("query", __name__)


@bp.get("/measurements")
def query_measurements():
    query, filters = query_service.measurement_query(request.args)
    result = paginate_query(query, lambda row: row.to_dict(include_station=True))
    result["summary"] = query_service.summary(filters)
    result["applied_filters"] = filters
    return result


@bp.get("/statistics")
def query_statistics():
    return query_service.statistics(request.args)


@bp.get("/export")
def query_export():
    from ..utils.csv_export import csv_response

    query, filters = query_service.measurement_query(request.args)
    max_rows = current_app.config["MAX_EXPORT_ROWS"]
    rows = query.limit(max_rows).all()
    return csv_response(
        rows,
        query_service.measurement_export_columns(),
        "monitoring_query",
        summary_rows=query_service.compliance_summary_rows(
            query_service.summary(filters), exported_count=len(rows), max_export_rows=max_rows
        ),
    )


@bp.get("/options")
def query_options():
    payload = query_service.option_payload()
    payload["pollutants"] = [
        {"value": item["code"], "label": item["label"], "unit": item["unit"],
         "limits": item["limits"]}
        for item in POLLUTANTS.values()
    ]
    payload["periods"] = [{"value": key, "label": label} for key, label in PERIOD_LABELS.items()]
    payload["station_types"] = [
        {"value": key, "label": label} for key, label in STATION_TYPE_LABELS.items()
    ]
    payload["data_sources"] = [
        {"value": key, "label": label} for key, label in DATA_SOURCE_LABELS.items()
    ]
    return payload
