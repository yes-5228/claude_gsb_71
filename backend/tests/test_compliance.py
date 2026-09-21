"""达标率统一取数口径测试.

覆盖明细列表 summary、看板 overview、聚合统计 statistics 与 CSV 导出四处,
验证它们对同一批数据给出同一个结果, 并且:

1. 超标单被标注为"已忽略(ignored)"的记录视为已标记无效, 不进率的分子分母;
2. 无限值的因子(如 PM2.5/PM10 小时值)仅记录, 不参评, 不按达标处理;
3. 统计恒为筛选后的完整集合, 与分页页码/每页条数无关。
"""
import pytest

from app.models import Exceedance


def _make_daily_set(client, station, entry_payload):
    """6 条日均值: 3 超标 3 达标, 全部有限值可参评。"""
    for day, so2, no2 in (
        ("2026-09-01 10:00", 900.0, 40.0),   # SO2 超标
        ("2026-09-02 10:00", 900.0, 40.0),   # SO2 超标
        ("2026-09-03 10:00", 900.0, 40.0),   # SO2 超标
    ):
        client.post(
            "/api/measurements/entries",
            json=entry_payload(
                station.id,
                measured_at=day,
                period="daily",
                entries=[{"pollutant": "SO2", "value": so2}, {"pollutant": "NO2", "value": no2}],
            ),
        )


def _ignore_one_so2_exceedance():
    exceedance = Exceedance.query.filter_by(pollutant="SO2").order_by(Exceedance.id.asc()).first()
    exceedance.status = "ignored"
    exceedance.note = "仪器校准期间异常值, 原始数据标记无效"
    exceedance.annotator = "李静"
    from datetime import datetime

    exceedance.annotated_at = datetime.now()
    from app.extensions import db

    db.session.commit()


def test_ignored_record_is_excluded_from_rate_everywhere(client, station, entry_payload):
    _make_daily_set(client, station, entry_payload)
    _ignore_one_so2_exceedance()

    # 明细列表 summary
    summary = client.get("/api/measurements").get_json()["summary"]
    assert summary["total"] == 6
    assert summary["invalid_count"] == 1
    assert summary["rateable_count"] == 5
    assert summary["exceeded_count"] == 2
    assert summary["exceed_rate"] == pytest.approx(0.4)
    assert summary["compliance_rate"] == pytest.approx(0.6)

    # 看板 overview 与明细同一批数据、同一个结果
    overview = client.get("/api/meta/overview").get_json()["measurements"]
    for key in ("total", "invalid_count", "rateable_count", "exceeded_count",
                "exceed_rate", "compliance_rate"):
        assert overview[key] == summary[key]

    # 报表聚合统计: 合计与明细/看板一致; SO2 分组内同样剔除无效单
    statistics = client.get("/api/query/statistics?group_by=pollutant&metric=count").get_json()
    assert statistics["totals"]["total"] == 6
    assert statistics["totals"]["invalid_count"] == 1
    assert statistics["totals"]["rateable_count"] == 5
    assert statistics["totals"]["exceeded_count"] == 2
    assert statistics["totals"]["compliance_rate"] == pytest.approx(0.6)
    so2 = next(item for item in statistics["items"] if item["key"] == "SO2")
    assert so2["total"] == 3
    assert so2["invalid_count"] == 1
    assert so2["rateable_count"] == 2
    assert so2["exceeded_count"] == 2
    assert so2["compliance_rate"] == 0.0

    # CSV 导出统计块同样口径
    text = client.get("/api/measurements/export").get_data(as_text=True)
    rows = {
        label: value
        for label, comma, value in (line.partition(",") for line in text.splitlines())
        if comma and label in {
            "数据总量", "参评数据量", "其中: 超标数据量", "已标记无效(不参评)", "达标率",
        }
    }
    assert rows["数据总量"] == "6"
    assert rows["参评数据量"] == "5"
    assert rows["其中: 超标数据量"] == "2"
    assert rows["已标记无效(不参评)"] == "1"
    assert rows["达标率"] == "60.00%"
    # 被忽略的那一行在明细里标"无效", 不再与"超标"混淆
    ignored_line = next(line for line in text.splitlines() if "无效" in line and line.startswith("TEST-"))
    assert ignored_line.split(",")[8] == "无效"


def test_records_without_limit_are_not_counted_as_compliant(client, station, entry_payload):
    # PM2.5/PM10 小时值无限值: 10 条数值哪怕再高也只记录, 不参评
    entries = []
    for i in range(10):
        entries = [
            {"pollutant": "PM25", "value": 500.0},
            {"pollutant": "PM10", "value": 800.0},
        ]
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 08:00",
            period="hourly",
            entries=entries,
        ),
    )
    summary = client.get("/api/measurements").get_json()["summary"]
    assert summary["total"] == 2
    assert summary["rateable_count"] == 0
    assert summary["unrateable_count"] == 2
    assert summary["exceeded_count"] == 0
    # 没有可参评数据时率为 None, 而不是被错误地报为 100% 达标
    assert summary["exceed_rate"] is None
    assert summary["compliance_rate"] is None

    statistics = client.get("/api/query/statistics?group_by=pollutant").get_json()
    for item in statistics["items"]:
        assert item["rateable_count"] == 0
        assert item["compliance_rate"] is None
    assert statistics["totals"]["rateable_count"] == 0
    assert statistics["totals"]["unrateable_count"] == 2


def test_mixed_limits_and_invalid_share_one_denominator(client, station, entry_payload):
    # 4 条数据: 1 条无限值(不参评) + 1 条超标 + 1 条达标 + 1 条超标但标记无效
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 08:00",
            period="hourly",
            entries=[{"pollutant": "PM25", "value": 500.0}],
        ),
    )
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 09:00",
            period="hourly",
            entries=[{"pollutant": "SO2", "value": 900.0}],
        ),
    )
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 10:00",
            period="hourly",
            entries=[{"pollutant": "SO2", "value": 100.0}],
        ),
    )
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 11:00",
            period="hourly",
            entries=[{"pollutant": "SO2", "value": 900.0}],
        ),
    )
    _ignore_one_so2_exceedance()  # 忽略最早一条 SO2 超标(09:00)

    summary = client.get("/api/query/measurements").get_json()["summary"]
    assert summary["total"] == 4
    assert summary["unrateable_count"] == 1
    assert summary["invalid_count"] == 1
    assert summary["rateable_count"] == 2
    assert summary["exceeded_count"] == 1
    assert summary["compliance_rate"] == 0.5


def test_rate_is_computed_over_full_filter_set_not_current_page(
    client, second_station, station, entry_payload
):
    _make_daily_set(client, station, entry_payload)
    _ignore_one_so2_exceedance()

    # 每页只取 2 条时, summary 仍覆盖全部 6 条数据(不受 page/page_size 影响)
    paged = client.get("/api/measurements?page=1&page_size=2").get_json()
    assert len(paged["items"]) == 2
    summary = paged["summary"]
    assert summary["total"] == 6
    assert summary["rateable_count"] == 5
    assert summary["exceeded_count"] == 2

    page_two = client.get("/api/measurements?page=2&page_size=2").get_json()
    assert page_two["summary"] == summary

    # 翻页后的导出统计块仍是完整集合, 而不是当前页 2 条
    text = client.get("/api/measurements/export").get_data(as_text=True)
    rows = {
        label: value
        for label, comma, value in (line.partition(",") for line in text.splitlines())
        if comma and label in {"数据总量", "参评数据量"}
    }
    assert rows["数据总量"] == "6"
    assert rows["参评数据量"] == "5"
