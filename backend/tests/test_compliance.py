"""Unified compliance-rate caliber tests."""

from app.extensions import db
from app.models import Exceedance
from app.services import exceedance_service


def test_compliance_rate_excludes_ignored_and_no_limit_records(client, station, entry_payload):
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            entries=[
                {"pollutant": "PM25", "value": 30.0},      # hourly: no limit, not evaluated
                {"pollutant": "CO", "value": 1.0},        # qualified
                {"pollutant": "SO2", "value": 900.0},     # exceeded then marked invalid
                {"pollutant": "NO2", "value": 300.0},     # effective exceedance
            ],
        ),
    )
    invalid_id = Exceedance.query.filter_by(pollutant="SO2").one().id
    exceedance_service.annotate(
        db.session.get(Exceedance, invalid_id),
        status="ignored",
        note="仪器校准异常值",
        annotator="李静",
    )

    summary = client.get("/api/query/measurements").get_json()["summary"]
    assert summary["total"] == 4
    assert summary["applicable_count"] == 3
    assert summary["invalid_count"] == 1
    assert summary["not_applicable_count"] == 1
    assert summary["evaluated_count"] == 2
    assert summary["qualified_count"] == 1
    assert summary["exceeded_count"] == 1
    assert summary["compliance_rate"] == 0.5

    statistics = client.get("/api/query/statistics?group_by=pollutant&metric=count").get_json()
    totals = statistics["totals"]
    assert totals["total"] == 4
    assert totals["evaluated_count"] == 2
    assert totals["qualified_count"] == 1
    assert totals["exceeded_count"] == 1
    assert totals["compliance_rate"] == 0.5

    overview = client.get("/api/meta/overview").get_json()["measurements"]
    assert overview["total"] == 4
    assert overview["evaluated_count"] == 2
    assert overview["qualified_count"] == 1
    assert overview["exceeded_count"] == 1
    assert overview["compliance_rate"] == 0.5


def test_summary_is_not_limited_to_current_page(client, station, entry_payload):
    for hour in (8, 9, 10):
        client.post(
            "/api/measurements/entries",
            json=entry_payload(
                station.id,
                measured_at="2026-09-01 %02d:00" % hour,
                entries=[{"pollutant": "CO", "value": 1.0}],
            ),
        )

    first_page = client.get("/api/query/measurements?page=1&page_size=1").get_json()
    assert len(first_page["items"]) == 1
    assert first_page["summary"]["total"] == 3
    assert first_page["summary"]["evaluated_count"] == 3


def test_export_uses_full_filtered_summary_and_shows_state_columns(client, station, entry_payload):
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            entries=[
                {"pollutant": "PM25", "value": 30.0},
                {"pollutant": "CO", "value": 1.0},
                {"pollutant": "SO2", "value": 900.0},
            ],
        ),
    )
    invalid_id = Exceedance.query.filter_by(pollutant="SO2").one().id
    exceedance_service.annotate(
        db.session.get(Exceedance, invalid_id), status="ignored", note="异常值", annotator="测试"
    )

    response = client.get("/api/query/export")
    text = response.get_data(as_text=True)
    assert "达标状态" in text
    assert "达标参评记录数(分母)" in text
    assert "无限值记录数(不参评),1" in text
    assert "已标记无效记录数(不参评),1" in text
    assert "达标率,50.00%" in text


def test_detail_row_exposes_invalid_and_not_applicable_states(client, station, entry_payload):
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            entries=[
                {"pollutant": "PM25", "value": 30.0},
                {"pollutant": "SO2", "value": 900.0},
            ],
        ),
    )
    invalid_id = Exceedance.query.filter_by(pollutant="SO2").one().id
    exceedance_service.annotate(
        db.session.get(Exceedance, invalid_id), status="ignored", note="异常值", annotator="测试"
    )

    states = {
        row["pollutant"]: row["compliance_state"]
        for row in client.get("/api/query/measurements").get_json()["items"]
    }
    assert states == {"PM25": "not_applicable", "SO2": "ignored"}
