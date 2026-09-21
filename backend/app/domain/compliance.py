"""达标率 / 超标率统一取数口径.

明细列表、运行概览看板、聚合统计(报表)与 CSV 导出共用本模块, 任何一处都不得
再自行编写"超标数 / 总数"式的除法, 避免口径分叉。

口径约定(一律基于筛选后的完整数据集合计算, 与分页页码/每页条数无关):

- ``total``               筛选命中的全部监测数据(含无限值、已标记无效)。
- ``rateable_count``      参评数据量: 该因子/周期存在限值(``limit_value`` 非空)
                          且其超标记录未被人工标注为"已忽略(ignored)"。
- ``unrateable_count``    无限值数据量: 如 PM2.5/PM10 的小时值, 仅记录数值,
                          既不算达标也不算超标, 不进入率的分子分母。
- ``invalid_count``       已标记无效的数据量: 超标记录被标注为"已忽略"
                          (设备异常/校准期等); 原始数据保留可查, 但不计入
                          率的分子与分母。
- ``exceeded_count``      参评且判定超标的数据量(即有效超标数)。
- ``exceed_rate``         超标率 = exceeded_count / rateable_count。
- ``compliance_rate``     达标率 = 1 - exceed_rate
                          = (rateable_count - exceeded_count) / rateable_count。

``rateable_count`` 为 0(该范围内没有可参评数据)时两个率均为 ``None``,
由前端展示为 "-", 而不是误导性的 0%。
"""
from sqlalchemy import case, exists, func

from ..models import Exceedance, Measurement

# 超标记录被人工标注为该状态时, 视为"原始数据已标记无效"
INVALID_STATUSES = ("ignored",)


def _ignored_exists():
    """Correlated EXISTS: the measurement's exceedance row is marked invalid."""
    return (
        exists()
        .where(
            Exceedance.measurement_id == Measurement.id,
            Exceedance.status.in_(INVALID_STATUSES),
        )
        .correlate(Measurement)
    )


def _unrateable():
    """SQL expression: row has no limit for its pollutant/period."""
    return Measurement.limit_value.is_(None)


def _ignored():
    """SQL expression: the row's exceedance record is annotated as ignored."""
    return _ignored_exists()


def aggregate_expressions(prefix=""):
    """Canonical aggregate expressions over a (filtered) Measurement query.

    Returns a dict mapping ``<prefix><name>`` to labelled SQLAlchemy
    expressions: total / rateable / unrateable / invalid / exceeded.
    ``prefix`` disambiguates names when a query already selects same-named
    columns. The ignored-detection uses a correlated EXISTS, so callers do
    NOT need to join ``Exceedance``.
    """
    p = ("%s_" % prefix) if prefix else ""
    finite_limit = Measurement.limit_value.isnot(None)
    not_ignored = ~_ignored()
    return {
        "%stotal" % p: func.count(Measurement.id).label("%stotal" % p),
        "%srateable" % p: func.coalesce(
            func.sum(case((finite_limit & not_ignored, 1), else_=0)), 0
        ).label("%srateable" % p),
        "%sunrateable" % p: func.coalesce(
            func.sum(case((_unrateable(), 1), else_=0)), 0
        ).label("%sunrateable" % p),
        "%sinvalid" % p: func.coalesce(
            func.sum(case((_ignored(), 1), else_=0)), 0
        ).label("%sinvalid" % p),
        # is_exceeded 为真的行必然有限值; 再排除"已忽略"无效单即为有效超标数
        "%sexceeded" % p: func.coalesce(
            func.sum(
                case(
                    (Measurement.is_exceeded.is_(True) & not_ignored, 1),
                    else_=0,
                )
            ),
            0,
        ).label("%sexceeded" % p),
    }


def _round_rate(value):
    return round(float(value), 4) if value is not None else None


def build_rate_payload(total, rateable, unrateable, invalid, exceeded):
    """Assemble canonical counters/rates from scalar aggregate values."""
    total = int(total or 0)
    rateable = int(rateable or 0)
    unrateable = int(unrateable or 0)
    invalid = int(invalid or 0)
    exceeded = int(exceeded or 0)
    return {
        "total": total,
        "rateable_count": rateable,
        "unrateable_count": unrateable,
        "invalid_count": invalid,
        "exceeded_count": exceeded,
        "exceed_rate": _round_rate(exceeded / rateable) if rateable else None,
        "compliance_rate": _round_rate((rateable - exceeded) / rateable) if rateable else None,
    }


def _percent(value):
    return "-" if value is None else "%.2f%%" % (value * 100)


def csv_trailer(stats):
    """Canonical summary block appended to every measurement CSV export."""
    return (
        "达标率统计(口径: 无限值仅记录不参评; 已标记无效即超标单标注为已忽略的记录不计入分子分母)",
        [
            ("数据总量", stats["total"]),
            ("参评数据量", stats["rateable_count"]),
            ("其中: 达标数据量", stats["rateable_count"] - stats["exceeded_count"]),
            ("其中: 超标数据量", stats["exceeded_count"]),
            ("无限值仅记录(不参评)", stats["unrateable_count"]),
            ("已标记无效(不参评)", stats["invalid_count"]),
            ("达标率", _percent(stats["compliance_rate"])),
            ("超标率", _percent(stats["exceed_rate"])),
        ],
    )
