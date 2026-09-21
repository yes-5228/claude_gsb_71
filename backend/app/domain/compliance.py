"""达标率统计口径.

同一份口径同时供明细列表、看板、聚合报表和 CSV 导出使用:

* ``ignored``: 超标记录被人工标注为“已忽略”的监测数据。明细和导出仍保留,
  但不计入超标数、达标数或达标率分母。
* ``not_applicable``: 该因子在该数据周期没有限值。明细和导出中标记为“不参评”,
  同样不计入达标率分母, 也不能按达标处理。
* ``qualified`` / ``exceeded``: 有限值且未被标记无效的记录, 二者组成达标率分母。
"""

COMPLIANCE_STATE_LABELS = {
    "qualified": "达标",
    "exceeded": "超标",
    "ignored": "无效(不参评)",
    "not_applicable": "无限值(不参评)",
}

COMPLIANCE_STATUS_LABELS = {
    "qualified": "达标",
    "exceeded": "有效超标",
    "ignored": "已标记无效",
    "not_applicable": "不参评",
}

IGNORED_EXCEEDANCE_STATUS = "ignored"


def state_for_row(row):
    """Return the compliance state for a Measurement model instance."""
    if row.limit_value is None:
        return "not_applicable"
    if bool(row.is_exceeded) and row.exceedance is not None and row.exceedance.status == "ignored":
        return "ignored"
    return "exceeded" if bool(row.is_exceeded) else "qualified"


def state_for_payload(payload):
    """Return the compliance state for a serialized Measurement payload."""
    if payload.get("limit_value") is None:
        return "not_applicable"
    if payload.get("is_exceeded") and payload.get("exceedance_status") == IGNORED_EXCEEDANCE_STATUS:
        return "ignored"
    return "exceeded" if payload.get("is_exceeded") else "qualified"


def compliance_counts(total=0, applicable=0, invalid=0, exceeded=0):
    """Build the single compliance counter shape used by every API surface."""
    total = int(total or 0)
    applicable = int(applicable or 0)
    invalid = int(invalid or 0)
    evaluated = max(applicable - invalid, 0)
    exceeded = min(int(exceeded or 0), evaluated)
    qualified = max(evaluated - exceeded, 0)
    not_applicable = max(total - applicable, 0)
    compliance_rate = round(qualified / evaluated, 4) if evaluated else None
    exceed_rate = round(exceeded / evaluated, 4) if evaluated else None
    return {
        "total": total,
        "applicable_count": applicable,
        "evaluated_count": evaluated,
        "qualified_count": qualified,
        "exceeded_count": exceeded,
        "invalid_count": invalid,
        "not_applicable_count": not_applicable,
        "compliance_rate": compliance_rate,
        "exceed_rate": exceed_rate,
        "labels": {
            "compliance_state": dict(COMPLIANCE_STATE_LABELS),
            "compliance_status": dict(COMPLIANCE_STATUS_LABELS),
        },
    }
