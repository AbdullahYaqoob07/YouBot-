import pytest
from fastapi.testclient import TestClient


ADMIN_HEADERS = {
    "X-Admin-Key": "test-admin-key",
    "X-Tenant-Id": "tenant_test",
    "X-Workspace-Id": "workspace_test",
}


@pytest.fixture
def app_client(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module.settings, "ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setattr(app_module.settings, "REQUIRE_TENANT_CONTEXT", False)

    original_startup = list(app_module.app.router.on_startup)
    original_shutdown = list(app_module.app.router.on_shutdown)
    app_module.app.router.on_startup = []
    app_module.app.router.on_shutdown = []

    client = TestClient(app_module.app)
    try:
        yield client, app_module
    finally:
        client.close()
        app_module.app.router.on_startup = original_startup
        app_module.app.router.on_shutdown = original_shutdown


def test_phase5_analytics_endpoints_contract(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_overview(**_kwargs):
        return {"health_score": 91.0, "total_conversations": 30}

    async def fake_user(**_kwargs):
        return {"completion_rate": 82.5, "repeat_contact_rate_24h": 8.0}

    async def fake_ai(**_kwargs):
        return {"auto_resolution_rate": 68.0, "fallback_rate": 22.0}

    async def fake_team(**_kwargs):
        return {"sla_breach_rate": 3.0, "avg_handling_time_minutes": 5.2}

    async def fake_kb(**_kwargs):
        return {"retrieval_hit_rate": 77.0, "knowledge_freshness_score": 88.0}

    async def fake_channel(**_kwargs):
        return {
            "channels": [
                {"channel": "webhook", "events": 10, "p95_response_latency_ms": 1200.0}
            ]
        }

    async def fake_export(**_kwargs):
        return "domain,metric,value\noverview,health_score,91\n"

    async def fake_create_rule(**kwargs):
        return {
            "id": 1,
            "rule_name": kwargs["rule_name"],
            "metric_name": kwargs["metric_name"],
            "condition": kwargs["condition"],
            "threshold_value": kwargs["threshold_value"],
            "is_active": kwargs["is_active"],
        }

    async def fake_get_alert_events(**_kwargs):
        return {
            "count": 1,
            "events": [
                {
                    "id": 10,
                    "rule_id": 1,
                    "rule_name": "SLA Breach Guard",
                    "metric_value": 6.5,
                    "status": "new",
                }
            ],
        }

    async def fake_usage_governance(**_kwargs):
        return {
            "tenant_plan": "starter",
            "status": "warning",
            "usage": {
                "rolling_30d_events": 8500,
                "rolling_30d_conversations": 1700,
                "active_alert_rules": 4,
            },
            "quota": {
                "monthly_events": 10000,
                "monthly_conversations": 2000,
                "active_alert_rules": 5,
            },
            "utilization": {
                "monthly_events_pct": 85.0,
                "monthly_conversations_pct": 85.0,
                "active_alert_rules_pct": 80.0,
            },
        }

    async def fake_quota_governance(**_kwargs):
        return {
            "tenant_plan": "starter",
            "status": "warning",
            "forecast": {
                "events_days_until_quota": 5.5,
                "conversations_days_until_quota": 6.1,
                "alert_rule_slots_remaining": 1,
            },
        }

    async def fake_run_aggregation_job(**_kwargs):
        return {
            "status": "success",
            "governance_alerts": {
                "status": "success",
                "generated_events": 2,
            },
        }

    monkeypatch.setattr(app_module, "get_tenant_overview_metrics", fake_overview)
    monkeypatch.setattr(app_module, "get_user_performance_metrics", fake_user)
    monkeypatch.setattr(app_module, "get_ai_performance_metrics", fake_ai)
    monkeypatch.setattr(app_module, "get_team_performance_metrics", fake_team)
    monkeypatch.setattr(app_module, "get_kb_performance_metrics", fake_kb)
    monkeypatch.setattr(app_module, "get_channel_performance_metrics", fake_channel)
    monkeypatch.setattr(app_module, "export_tenant_analytics_csv", fake_export)
    monkeypatch.setattr(app_module, "create_alert_rule", fake_create_rule)
    monkeypatch.setattr(app_module, "get_alert_events", fake_get_alert_events)
    monkeypatch.setattr(app_module, "get_usage_governance_metrics", fake_usage_governance)
    monkeypatch.setattr(app_module, "get_quota_governance_metrics", fake_quota_governance)
    monkeypatch.setattr(app_module, "run_phase5_aggregation_job", fake_run_aggregation_job)

    overview_resp = client.get("/tenant-analytics/overview?days=30", headers=ADMIN_HEADERS)
    assert overview_resp.status_code == 200
    assert overview_resp.json()["data"]["health_score"] == 91.0

    user_resp = client.get("/tenant-analytics/user-performance?days=30", headers=ADMIN_HEADERS)
    assert user_resp.status_code == 200
    assert user_resp.json()["data"]["completion_rate"] == 82.5

    ai_resp = client.get("/tenant-analytics/ai-performance?days=30", headers=ADMIN_HEADERS)
    assert ai_resp.status_code == 200
    assert ai_resp.json()["data"]["auto_resolution_rate"] == 68.0

    team_resp = client.get("/tenant-analytics/team-performance?days=30", headers=ADMIN_HEADERS)
    assert team_resp.status_code == 200
    assert team_resp.json()["data"]["sla_breach_rate"] == 3.0

    kb_resp = client.get("/tenant-analytics/kb-performance?days=30", headers=ADMIN_HEADERS)
    assert kb_resp.status_code == 200
    assert kb_resp.json()["data"]["retrieval_hit_rate"] == 77.0

    channel_resp = client.get("/tenant-analytics/channel-performance?days=30", headers=ADMIN_HEADERS)
    assert channel_resp.status_code == 200
    assert channel_resp.json()["data"]["channels"][0]["channel"] == "webhook"

    export_resp = client.get("/tenant-analytics/export.csv?days=30&domain=overview", headers=ADMIN_HEADERS)
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    assert "domain,metric,value" in export_resp.text

    create_rule_resp = client.post(
        "/tenant-analytics/alerts/rules",
        headers=ADMIN_HEADERS,
        json={
            "ruleName": "SLA Breach Guard",
            "metricName": "sla_breach_rate",
            "condition": "gt",
            "thresholdValue": 5,
            "isActive": True,
        },
    )
    assert create_rule_resp.status_code == 200
    assert create_rule_resp.json()["rule"]["metric_name"] == "sla_breach_rate"

    alert_events_resp = client.get("/tenant-analytics/alerts/events?days=7&limit=20", headers=ADMIN_HEADERS)
    assert alert_events_resp.status_code == 200
    assert alert_events_resp.json()["data"]["count"] == 1

    governance_usage_resp = client.get("/tenant-analytics/governance/usage?days=30", headers=ADMIN_HEADERS)
    assert governance_usage_resp.status_code == 200
    assert governance_usage_resp.json()["data"]["usage"]["rolling_30d_events"] == 8500

    governance_quota_resp = client.get("/tenant-analytics/governance/quota?days=30", headers=ADMIN_HEADERS)
    assert governance_quota_resp.status_code == 200
    assert governance_quota_resp.json()["data"]["forecast"]["events_days_until_quota"] == 5.5

    aggregate_job_resp = client.post("/tenant-analytics/jobs/aggregate", headers=ADMIN_HEADERS)
    assert aggregate_job_resp.status_code == 200
    assert aggregate_job_resp.json()["data"]["governance_alerts"]["generated_events"] == 2


def test_phase5_admin_key_required(app_client):
    client, _ = app_client

    resp = client.get("/tenant-analytics/overview")
    assert resp.status_code == 403


def test_phase5_alert_rule_validation_rejects_bad_condition(app_client):
    client, _ = app_client

    resp = client.post(
        "/tenant-analytics/alerts/rules",
        headers=ADMIN_HEADERS,
        json={
            "ruleName": "Bad Rule",
            "metricName": "sla_breach_rate",
            "condition": "equals",
            "thresholdValue": 5,
            "isActive": True,
        },
    )
    assert resp.status_code == 422
