"""数据查询与统计接口测试."""

SUMMARY_LABELS = {
    "数据总量",
    "参评数据量",
    "其中: 达标数据量",
    "其中: 超标数据量",
    "无限值仅记录(不参评)",
    "已标记无效(不参评)",
    "达标率",
    "超标率",
}


def _seed_two_days(client, station, entry_payload):
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-01 10:00",
            period="daily",
            entries=[{"pollutant": "PM25", "value": 60.0}, {"pollutant": "SO2", "value": 900.0}],
        ),
    )
    client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id,
            measured_at="2026-09-02 10:00",
            period="daily",
            entries=[{"pollutant": "PM25", "value": 100.0}, {"pollutant": "SO2", "value": 100.0}],
        ),
    )


def _summary_section(text):
    section = {}
    for line in text.splitlines():
        label, comma, value = line.partition(",")
        if comma and label in SUMMARY_LABELS:
            section[label] = value
    return section


def test_query_by_date_range_and_values(client, station, entry_payload):
    _seed_two_days(client, station, entry_payload)

    all_rows = client.get("/api/query/measurements").get_json()
    assert all_rows["total"] == 4
    assert all_rows["summary"]["exceed_rate"] == 0.5
    assert all_rows["summary"]["compliance_rate"] == 0.5

    day_range = client.get(
        "/api/query/measurements?date_from=2026-09-02&date_to=2026-09-02"
    ).get_json()
    assert day_range["total"] == 2

    value_range = client.get("/api/query/measurements?min_value=200").get_json()
    assert value_range["total"] == 1

    filters = client.get("/api/query/measurements?is_exceeded=true").get_json()
    assert filters["summary"]["exceeded_count"] == 2
    assert filters["summary"]["exceed_rate"] == 1.0
    assert filters["applied_filters"]["pollutants"] == []


def test_query_rejects_invalid_filters(client):
    assert client.get("/api/query/measurements?pollutant=XX").status_code == 422
    assert client.get("/api/query/measurements?date_from=not-a-date").status_code == 422
    assert (
        client.get(
            "/api/query/measurements?date_from=2026-09-05&date_to=2026-09-01"
        ).status_code
        == 422
    )
    assert client.get("/api/query/statistics?group_by=unknown").status_code == 422


def test_statistics_by_pollutant_and_metric(client, station, entry_payload):
    _seed_two_days(client, station, entry_payload)
    body = client.get("/api/query/statistics?group_by=pollutant&metric=avg").get_json()
    assert body["group_by"] == "pollutant"
    values = {item["key"]: item["value"] for item in body["items"]}
    assert values["PM25"] == 80.0
    assert values["SO2"] == 500.0

    counts = client.get("/api/query/statistics?group_by=pollutant&metric=count").get_json()
    assert {item["key"]: item["value"] for item in counts["items"]} == {"PM25": 2.0, "SO2": 2.0}

    exceeded = {item["key"]: item["exceeded_count"] for item in counts["items"]}
    assert exceeded == {"PM25": 1, "SO2": 1}


def test_statistics_by_day_is_chronological(client, station, entry_payload):
    _seed_two_days(client, station, entry_payload)
    body = client.get("/api/query/statistics?group_by=day&metric=avg").get_json()
    assert [item["key"] for item in body["items"]] == ["2026-09-01", "2026-09-02"]
    assert body["totals"]["total"] == 4


def test_statistics_by_station_uses_station_labels(client, station, second_station, entry_payload):
    _seed_two_days(client, station, entry_payload)
    client.post(
        "/api/measurements/entries",
        json=entry_payload(second_station.id, entries=[{"pollutant": "PM25", "value": 30.0}]),
    )
    body = client.get("/api/query/statistics?group_by=station&metric=count").get_json()
    labels = {item["key"]: item["label"] for item in body["items"]}
    assert labels["TEST-002"] == "TEST-002 工业园监测点"


def test_query_export_respects_filters(client, station, entry_payload):
    _seed_two_days(client, station, entry_payload)
    response = client.get("/api/query/export?pollutant=PM25")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    lines = text.strip().splitlines()
    assert "站点编码" in lines[0]
    data_rows = [line for line in lines if line.startswith(("TEST-", "SZ-"))]
    assert len(data_rows) == 2
    assert all("PM2.5" in line for line in data_rows)
    summary = _summary_section(text)
    assert summary["数据总量"] == "2"
    # PM2.5 日均值两条, 1 条超标; 统计块与明细行、列表卡片同一口径
    assert summary["参评数据量"] == "2"
    assert summary["其中: 超标数据量"] == "1"
    assert summary["达标率"] == "50.00%"


def test_query_options_payload(client):
    body = client.get("/api/query/options").get_json()
    assert "day" in body["group_by"]
    assert {item["value"] for item in body["pollutants"]} == {"PM25", "PM10", "SO2", "NO2", "CO", "O3"}
