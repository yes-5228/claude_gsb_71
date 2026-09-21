"""监测数据查询: 过滤条件解析, 统计聚合与导出数据准备."""
from datetime import datetime, time

from sqlalchemy import case, func, or_

from ..domain.compliance import compliance_counts
from ..domain.compliance_sql import (
    applicable_expression,
    integer_sum,
    invalid_exceedance_expression,
    valid_exceeded_expression,
)
from ..domain.constants import (
    DATA_SOURCE_LABELS,
    EXCEEDANCE_STATUS_LABELS,
    PERIOD_LABELS,
    STATION_TYPE_LABELS,
)
from ..domain.standards import POLLUTANT_CODES, get_pollutant
from ..errors import ValidationError
from ..extensions import db
from ..models import Exceedance, Measurement, Station
from ..models.base import iso
from ..utils.validation import parse_date

GROUP_BY_CHOICES = ("station", "area", "pollutant", "period", "day", "month", "data_source")
METRIC_CHOICES = ("avg", "max", "min", "count", "sum")
SORT_CHOICES = ("measured_at", "value", "exceed_ratio", "pollutant", "station_code", "created_at")


def _split(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _int_list(args, name):
    values = []
    for item in _split(args.get(name)):
        try:
            values.append(int(item))
        except ValueError:
            raise ValidationError("%s 参数必须为整数" % name, fields={name: "invalid_integer"})
    return values


def _float_arg(args, name):
    raw = args.get(name)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValidationError("%s 参数必须为数字" % name, fields={name: "invalid_number"})


def _bool_arg(args, name):
    raw = args.get(name)
    if raw in (None, ""):
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _date_arg(args, name, end_of_day=False):
    raw = args.get(name)
    if raw in (None, ""):
        return None
    parsed = parse_date(raw, name)
    return datetime.combine(parsed, time.max if end_of_day else time.min)


def parse_filters(args):
    """Translate request args into a normalised filter dictionary."""
    pollutants = [item.upper() for item in _split(args.get("pollutant"))]
    unknown = [item for item in pollutants if item not in POLLUTANT_CODES]
    if unknown:
        raise ValidationError(
            "未知监测因子: %s" % ", ".join(unknown), fields={"pollutant": "unknown"}
        )

    periods = _split(args.get("period"))
    for period in periods:
        if period not in PERIOD_LABELS:
            raise ValidationError("未知数据周期: %s" % period, fields={"period": "unknown"})

    filters = {
        "station_ids": _int_list(args, "station_id"),
        "areas": _split(args.get("area")),
        "station_types": _split(args.get("station_type")),
        "pollutants": pollutants,
        "periods": periods,
        "data_sources": _split(args.get("data_source")),
        "is_exceeded": _bool_arg(args, "is_exceeded"),
        "exceedance_status": _split(args.get("exceedance_status")),
        "date_from": _date_arg(args, "date_from"),
        "date_to": _date_arg(args, "date_to", end_of_day=True),
        "min_value": _float_arg(args, "min_value"),
        "max_value": _float_arg(args, "max_value"),
        "keyword": (args.get("keyword") or "").strip(),
        "recorder": (args.get("recorder") or "").strip(),
    }
    if filters["date_from"] and filters["date_to"] and filters["date_from"] > filters["date_to"]:
        raise ValidationError(
            "开始时间不能晚于结束时间", fields={"date_from": "range_invalid"}
        )
    if (
        filters["min_value"] is not None
        and filters["max_value"] is not None
        and filters["min_value"] > filters["max_value"]
    ):
        raise ValidationError("最小值不能大于最大值", fields={"min_value": "range_invalid"})
    return filters


def apply_filters(query, filters):
    query = query.join(Station, Measurement.station_id == Station.id)
    if filters["exceedance_status"]:
        # The right side statuses are used as both an explicit row filter and the
        # invalid-data marker. Keep one join so filtering and rate labels agree.
        query = query.join(Exceedance, Exceedance.measurement_id == Measurement.id).filter(
            Exceedance.status.in_(filters["exceedance_status"])
        )
    else:
        query = query.outerjoin(Exceedance, Exceedance.measurement_id == Measurement.id)
    if filters["station_ids"]:
        query = query.filter(Measurement.station_id.in_(filters["station_ids"]))
    if filters["areas"]:
        query = query.filter(Station.area.in_(filters["areas"]))
    if filters["station_types"]:
        query = query.filter(Station.station_type.in_(filters["station_types"]))
    if filters["pollutants"]:
        query = query.filter(Measurement.pollutant.in_(filters["pollutants"]))
    if filters["periods"]:
        query = query.filter(Measurement.period.in_(filters["periods"]))
    if filters["data_sources"]:
        query = query.filter(Measurement.data_source.in_(filters["data_sources"]))
    if filters["is_exceeded"] is not None:
        query = query.filter(Measurement.is_exceeded.is_(filters["is_exceeded"]))
    if filters["date_from"]:
        query = query.filter(Measurement.measured_at >= filters["date_from"])
    if filters["date_to"]:
        query = query.filter(Measurement.measured_at <= filters["date_to"])
    if filters["min_value"] is not None:
        query = query.filter(Measurement.value >= filters["min_value"])
    if filters["max_value"] is not None:
        query = query.filter(Measurement.value <= filters["max_value"])
    if filters["recorder"]:
        query = query.filter(Measurement.recorder.like("%" + filters["recorder"] + "%"))
    if filters["keyword"]:
        like = "%" + filters["keyword"] + "%"
        query = query.filter(
            or_(Station.name.like(like), Station.code.like(like), Station.address.like(like))
        )
    return query


def apply_sort(query, sort=None, order="desc"):
    sort = sort if sort in SORT_CHOICES else "measured_at"
    column = {
        "measured_at": Measurement.measured_at,
        "value": Measurement.value,
        "exceed_ratio": Measurement.exceed_ratio,
        "pollutant": Measurement.pollutant,
        "station_code": Station.code,
        "created_at": Measurement.created_at,
    }[sort]
    primary = column.desc() if (order or "desc").lower() == "desc" else column.asc()
    return query.order_by(primary, Measurement.id.desc())


def measurement_query(args):
    filters = parse_filters(args)
    query = apply_filters(db.session.query(Measurement), filters)
    return apply_sort(query, args.get("sort"), args.get("order")), filters


def measurement_export_columns():
    """CSV columns shared by the list and advanced query exports."""
    return [
        ("站点编码", lambda row: row.station.code if row.station else ""),
        ("站点名称", lambda row: row.station.name if row.station else ""),
        ("所属区域", lambda row: row.station.area if row.station else ""),
        ("监测因子", lambda row: row.pollutant_label()),
        ("数据周期", lambda row: PERIOD_LABELS.get(row.period, row.period)),
        ("监测值", "value"),
        ("单位", "unit"),
        ("限值", "limit_value"),
        ("自动超标判定", lambda row: "是" if row.is_exceeded else "否"),
        ("达标状态", lambda row: row.compliance_label()),
        ("超标倍数", "exceed_ratio"),
        ("标注状态", lambda row: EXCEEDANCE_STATUS_LABELS.get(row.exceedance.status, "")
            if row.exceedance else ""),
        ("标注说明", lambda row: row.exceedance.note if row.exceedance else ""),
        ("监测时间", lambda row: row.measured_at.strftime("%Y-%m-%d %H:%M")),
        ("数据来源", lambda row: DATA_SOURCE_LABELS.get(row.data_source, row.data_source)),
        ("录入人", "recorder"),
        ("备注", "remark"),
    ]


def _percent(value):
    return None if value is None else "{:.2f}%".format(value * 100)


def compliance_summary_rows(summary, exported_count=None, max_export_rows=None):
    """Human-readable counters appended to CSV exports from one shared summary."""
    rows = [
        ("筛选结果总数", summary["total"]),
        ("达标参评记录数(分母)", summary["evaluated_count"]),
        ("达标记录数(分子)", summary["qualified_count"]),
        ("有效超标记录数", summary["exceeded_count"]),
        ("达标率", _percent(summary["compliance_rate"])),
        ("已标记无效记录数(不参评)", summary["invalid_count"]),
        ("无限值记录数(不参评)", summary["not_applicable_count"]),
    ]
    if exported_count is not None:
        rows.append(("本次导出行数", exported_count))
        if max_export_rows and summary["total"] > exported_count:
            rows.append(("导出说明", "仅导出前 %d 行; 统计仍按全部 %d 条筛选结果计算"
                         % (max_export_rows, summary["total"])))
    return rows


def summary(filters):
    """Aggregate counters shown above detail tables and on the dashboard.

    Pagination is intentionally not applied here; every caller passes only
    business filters, so these numbers always cover the complete filtered set.
    """
    query = apply_filters(
        db.session.query(
            func.count(Measurement.id),
            integer_sum(applicable_expression()),
            integer_sum(invalid_exceedance_expression()),
            integer_sum(valid_exceeded_expression()),
            func.count(func.distinct(Measurement.station_id)),
            func.min(Measurement.measured_at),
            func.max(Measurement.measured_at),
            func.avg(case((~invalid_exceedance_expression(), Measurement.value))),
        ),
        filters,
    )
    total, applicable, invalid, exceeded, stations, first_at, last_at, avg_value = query.one()
    payload = compliance_counts(total, applicable, invalid, exceeded)
    payload.update(
        {
            "station_count": int(stations or 0),
            "first_measured_at": iso(first_at),
            "last_measured_at": iso(last_at),
            "avg_value": round(float(avg_value), 2) if avg_value is not None else None,
        }
    )
    return payload


def _metric_expression(metric):
    invalid = invalid_exceedance_expression()
    expressions = {
        "avg": func.avg(case((~invalid, Measurement.value))),
        "max": func.max(case((~invalid, Measurement.value))),
        "min": func.min(case((~invalid, Measurement.value))),
        "count": func.count(Measurement.id),
        "sum": func.sum(case((~invalid, Measurement.value))),
    }
    return expressions[metric]


def statistics(args):
    """Grouped aggregation used by the query page statistics panel."""
    filters = parse_filters(args)
    group_by = args.get("group_by") or "pollutant"
    metric = args.get("metric") or "avg"
    if group_by not in GROUP_BY_CHOICES:
        raise ValidationError(
            "group_by 仅支持: %s" % ", ".join(GROUP_BY_CHOICES), fields={"group_by": "unknown"}
        )
    if metric not in METRIC_CHOICES:
        raise ValidationError(
            "metric 仅支持: %s" % ", ".join(METRIC_CHOICES), fields={"metric": "unknown"}
        )

    value_expr = _metric_expression(metric).label("metric_value")
    count_expr = func.count(Measurement.id).label("row_count")
    applicable_expr = integer_sum(applicable_expression(), "applicable_count")
    invalid_expr = integer_sum(invalid_exceedance_expression(), "invalid_count")
    exceeded_expr = integer_sum(valid_exceeded_expression(), "exceeded_count")

    if group_by == "station":
        query = db.session.query(
            Station.id.label("station_id"),
            Station.code.label("station_code"),
            Station.name.label("station_name"),
            Station.area.label("area"),
            value_expr,
            count_expr,
            applicable_expr,
            invalid_expr,
            exceeded_expr,
        ).group_by(Station.id, Station.code, Station.name, Station.area)
        is_time_group = False
    elif group_by == "area":
        query = db.session.query(
            Station.area.label("area"), value_expr, count_expr, applicable_expr, invalid_expr,
            exceeded_expr
        ).group_by(Station.area)
        is_time_group = False
    elif group_by == "day":
        bucket = func.date(Measurement.measured_at).label("bucket")
        query = db.session.query(
            bucket, value_expr, count_expr, applicable_expr, invalid_expr, exceeded_expr
        ).group_by(bucket)
        is_time_group = True
    elif group_by == "month":
        year = func.extract("year", Measurement.measured_at).label("year")
        month = func.extract("month", Measurement.measured_at).label("month")
        query = db.session.query(
            year, month, value_expr, count_expr, applicable_expr, invalid_expr, exceeded_expr
        ).group_by(
            year, month
        )
        is_time_group = True
    else:
        column = {
            "pollutant": Measurement.pollutant,
            "period": Measurement.period,
            "data_source": Measurement.data_source,
        }[group_by]
        query = db.session.query(
            column.label("bucket"), value_expr, count_expr, applicable_expr, invalid_expr,
            exceeded_expr
        ).group_by(column)
        is_time_group = False

    query = apply_filters(query, filters)
    rows = query.all()

    items = []
    for row in rows:
        data = dict(row._mapping)
        count = int(data.get("row_count") or 0)
        applicable = int(data.get("applicable_count") or 0)
        invalid = int(data.get("invalid_count") or 0)
        exceeded = int(data.get("exceeded_count") or 0)
        raw_value = data.get("metric_value")
        counters = compliance_counts(count, applicable, invalid, exceeded)
        counters.pop("labels", None)
        if group_by == "station":
            key = data.get("station_code")
            label = "%s %s" % (data.get("station_code"), data.get("station_name"))
        elif group_by == "area":
            key = label = data.get("area")
        elif group_by == "day":
            key = str(data.get("bucket"))
            label = key
        elif group_by == "month":
            key = "%04d-%02d" % (int(data.get("year")), int(data.get("month")))
            label = key
        elif group_by == "pollutant":
            key = data.get("bucket")
            meta = get_pollutant(key)
            label = meta["label"] if meta else key
        elif group_by == "period":
            key = data.get("bucket")
            label = PERIOD_LABELS.get(key, key)
        else:
            key = data.get("bucket")
            label = DATA_SOURCE_LABELS.get(key, key)

        items.append(
            {
                "key": key,
                "label": label,
                "value": round(float(raw_value), 2) if raw_value is not None else None,
                "count": count,
                **counters,
            }
        )

    if is_time_group:
        items.sort(key=lambda item: item["key"])
    else:
        items.sort(key=lambda item: (item["value"] is None, -(item["value"] or 0)))

    totals = compliance_counts(
        total=sum(item["total"] for item in items),
        applicable=sum(item["applicable_count"] for item in items),
        invalid=sum(item["invalid_count"] for item in items),
        exceeded=sum(item["exceeded_count"] for item in items),
    )
    return {
        "group_by": group_by,
        "metric": metric,
        "items": items,
        "totals": totals,
    }


def option_payload():
    return {
        "group_by": list(GROUP_BY_CHOICES),
        "metric": list(METRIC_CHOICES),
        "sort": list(SORT_CHOICES),
        "exceedance_status": [
            {"value": key, "label": label} for key, label in EXCEEDANCE_STATUS_LABELS.items()
        ],
        "station_type": [
            {"value": key, "label": label} for key, label in STATION_TYPE_LABELS.items()
        ],
    }
