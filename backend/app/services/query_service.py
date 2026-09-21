"""监测数据查询: 过滤条件解析, 统计聚合与导出数据准备."""
from datetime import datetime, time

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import joinedload

from ..domain import compliance
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
    if filters["exceedance_status"]:
        # 用 EXISTS 半连接按标注状态过滤, 不产生重复行(一个数据最多一条超标单,
        # 但半连接在任何查询形态下都安全), 也不影响统一口径里的相关 EXISTS。
        query = query.filter(
            exists().where(
                Exceedance.measurement_id == Measurement.id,
                Exceedance.status.in_(filters["exceedance_status"]),
            )
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


def measurement_stats(filters, include_extras=False):
    """Canonical rate aggregation for the filtered measurement set.

    Used by the detail list, the overview dashboard and the CSV exports so
    they always report the same numbers for the same filters. The aggregation
    covers the whole filtered set and never depends on pagination.
    """
    expressions = compliance.aggregate_expressions()
    columns = list(expressions.values())
    if include_extras:
        columns.extend(
            [
                func.count(func.distinct(Measurement.station_id)).label("station_count"),
                func.min(Measurement.measured_at).label("first_at"),
                func.max(Measurement.measured_at).label("last_at"),
                func.avg(Measurement.value).label("avg_value"),
            ]
        )
    query = apply_filters(db.session.query(*columns), filters)
    row = query.one()
    data = dict(row._mapping)
    payload = compliance.build_rate_payload(
        data.get("total"),
        data.get("rateable"),
        data.get("unrateable"),
        data.get("invalid"),
        data.get("exceeded"),
    )
    if include_extras:
        payload["station_count"] = int(data.get("station_count") or 0)
        payload["first_measured_at"] = iso(data.get("first_at"))
        payload["last_measured_at"] = iso(data.get("last_at"))
        avg_value = data.get("avg_value")
        payload["avg_value"] = round(float(avg_value), 2) if avg_value is not None else None
    return payload


def summary(filters):
    """Aggregate counters shown above the detail/query result tables."""
    return measurement_stats(filters, include_extras=True)


def _metric_expression(metric):
    return {
        "avg": func.avg(Measurement.value),
        "max": func.max(Measurement.value),
        "min": func.min(Measurement.value),
        "count": func.count(Measurement.id),
        "sum": func.sum(Measurement.value),
    }[metric]


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
    rate_exprs = compliance.aggregate_expressions(prefix="rate")

    if group_by == "station":
        query = db.session.query(
            Station.id.label("station_id"),
            Station.code.label("station_code"),
            Station.name.label("station_name"),
            Station.area.label("area"),
            value_expr,
            *rate_exprs.values(),
        ).group_by(Station.id, Station.code, Station.name, Station.area)
        is_time_group = False
    elif group_by == "area":
        query = db.session.query(
            Station.area.label("area"), value_expr, *rate_exprs.values()
        ).group_by(Station.area)
        is_time_group = False
    elif group_by == "day":
        bucket = func.date(Measurement.measured_at).label("bucket")
        query = db.session.query(bucket, value_expr, *rate_exprs.values()).group_by(bucket)
        is_time_group = True
    elif group_by == "month":
        year = func.extract("year", Measurement.measured_at).label("year")
        month = func.extract("month", Measurement.measured_at).label("month")
        query = db.session.query(year, month, value_expr, *rate_exprs.values()).group_by(
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
            column.label("bucket"), value_expr, *rate_exprs.values()
        ).group_by(column)
        is_time_group = False

    query = apply_filters(query, filters)
    rows = query.all()

    items = []
    for row in rows:
        data = dict(row._mapping)
        rates = compliance.build_rate_payload(
            data.get("rate_total"),
            data.get("rate_rateable"),
            data.get("rate_unrateable"),
            data.get("rate_invalid"),
            data.get("rate_exceeded"),
        )
        raw_value = data.get("metric_value")
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
                **rates,
                # 兼容旧字段名: count/row_count 与超限展示保持可用
                "count": rates["total"],
                "row_count": rates["total"],
            }
        )

    if is_time_group:
        items.sort(key=lambda item: item["key"])
    else:
        items.sort(key=lambda item: (item["value"] is None, -(item["value"] or 0)))

    totals = compliance.build_rate_payload(
        sum(item["total"] for item in items),
        sum(item["rateable_count"] for item in items),
        sum(item["unrateable_count"] for item in items),
        sum(item["invalid_count"] for item in items),
        sum(item["exceeded_count"] for item in items),
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


# ---- CSV 导出: 明细列表页与高级查询页共用同一套列与统计口径 ----

def _row_judgement(row):
    """单行判定, 取值与 compliance 率口径严格对应, 供导出/展示对账。"""
    status = row.exceedance.status if row.exceedance else None
    if status == "ignored":
        return "无效"
    if row.limit_value is None:
        return "仅记录"
    return "超标" if row.is_exceeded else "达标"


def measurement_export(args, max_rows):
    """Return (rows, columns, stats, truncated) for measurement CSV exports.

    ``stats`` uses the same full-filter aggregation as the list cards and the
    dashboard; it is not affected by the row cap (only the detail rows are).
    """
    query, filters = measurement_query(args)
    rows = (
        query.options(
            joinedload(Measurement.station),
            joinedload(Measurement.exceedance),
        )
        .limit(max_rows + 1)
        .all()
    )
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    columns = [
        ("站点编码", lambda row: row.station.code if row.station else ""),
        ("站点名称", lambda row: row.station.name if row.station else ""),
        ("所属区域", lambda row: row.station.area if row.station else ""),
        ("监测因子", lambda row: row.pollutant_label()),
        ("数据周期", lambda row: PERIOD_LABELS.get(row.period, row.period)),
        ("监测值", "value"),
        ("单位", "unit"),
        ("限值", "limit_value"),
        ("判定", _row_judgement),
        ("原始超标标志", lambda row: "是" if row.is_exceeded else "否"),
        ("超标倍数", "exceed_ratio"),
        ("标注状态", lambda row: EXCEEDANCE_STATUS_LABELS.get(row.exceedance.status, "")
            if row.exceedance else ""),
        ("监测时间", lambda row: row.measured_at.strftime("%Y-%m-%d %H:%M")),
        ("数据来源", lambda row: DATA_SOURCE_LABELS.get(row.data_source, row.data_source)),
        ("录入人", "recorder"),
        ("备注", "remark"),
    ]
    stats = measurement_stats(filters)
    return rows, columns, stats, truncated
