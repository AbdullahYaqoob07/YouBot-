import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from database import analytics
from database.models import AnalyticsAlertEvent, TenantAnalyticsDaily, TenantAnalyticsHourly


def test_alert_condition_matching_logic():
    assert analytics.alert_condition_met(10, "gt", 5) is True
    assert analytics.alert_condition_met(10, "gte", 10) is True
    assert analytics.alert_condition_met(3, "lt", 5) is True
    assert analytics.alert_condition_met(5, "lte", 5) is True

    with pytest.raises(ValueError):
        analytics.alert_condition_met(5, "eq", 5)


def test_export_tenant_analytics_csv_rejects_invalid_domain():
    with pytest.raises(ValueError):
        asyncio.run(
            analytics.export_tenant_analytics_csv(
                tenant_id="tenant_test",
                workspace_id="workspace_test",
                days=7,
                domain="invalid-domain",
            )
        )


def test_export_tenant_analytics_csv_overview_domain(monkeypatch):
    async def fake_overview(_tenant_id, _workspace_id, _days):
        return {
            "health_score": 99.2,
            "total_conversations": 18,
        }

    monkeypatch.setattr(analytics, "get_tenant_overview_metrics", fake_overview)

    content = asyncio.run(
        analytics.export_tenant_analytics_csv(
            tenant_id="tenant_test",
            workspace_id="workspace_test",
            days=30,
            domain="overview",
        )
    )

    assert "domain,metric,value" in content
    assert "overview,health_score,99.2" in content


def test_run_tenant_analytics_aggregation_job_persists_rollups(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

    fake_session = FakeSession()

    @asynccontextmanager
    async def fake_get_async_session():
        yield fake_session

    async def fake_overview(tenant_id, workspace_id, days):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        assert days == 1
        return {
            "total_conversations": 25,
            "ai_resolved_count": 17,
            "handoff_count": 5,
            "avg_response_time_ms": 820.5,
        }

    governance_calls = {}

    async def fake_governance_job(tenant_id, workspace_id, days=30, dedupe_hours=24):
        governance_calls["tenant_id"] = tenant_id
        governance_calls["workspace_id"] = workspace_id
        governance_calls["days"] = days
        governance_calls["dedupe_hours"] = dedupe_hours
        return {
            "status": "success",
            "generated_events": 2,
        }

    monkeypatch.setattr(analytics, "get_async_session", fake_get_async_session)
    monkeypatch.setattr(analytics, "get_tenant_overview_metrics", fake_overview)
    monkeypatch.setattr(analytics, "run_governance_alert_generation_job", fake_governance_job)

    result = asyncio.run(
        analytics.run_tenant_analytics_aggregation_job(
            tenant_id="tenant_test",
            workspace_id="workspace_test",
        )
    )

    assert result["status"] == "success"
    assert fake_session.committed is True
    assert len(fake_session.added) == 2
    assert isinstance(fake_session.added[0], TenantAnalyticsHourly)
    assert isinstance(fake_session.added[1], TenantAnalyticsDaily)
    assert fake_session.added[0].total_conversations == 25
    assert fake_session.added[1].ai_resolved_conversations == 17
    assert result["governance_alerts"]["status"] == "success"
    assert result["governance_alerts"]["generated_events"] == 2
    assert governance_calls["tenant_id"] == "tenant_test"
    assert governance_calls["workspace_id"] == "workspace_test"


def test_run_governance_alert_generation_job_creates_rule_and_quota_events(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

    fake_session = FakeSession()

    @asynccontextmanager
    async def fake_get_async_session():
        yield fake_session

    async def fake_build_catalog(tenant_id, workspace_id, days):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        assert days == 30
        return (
            {
                "sla_breach_rate": 7.5,
                "monthly_events_pct": 120.0,
            },
            {
                "utilization": {
                    "monthly_events_pct": 120.0,
                    "monthly_conversations_pct": 95.0,
                    "active_alert_rules_pct": 60.0,
                }
            },
        )

    async def fake_load_rules(_session, _tenant_id, _workspace_id):
        return [
            SimpleNamespace(
                id=11,
                rule_name="SLA Breach Guard",
                metric_name="sla_breach_rate",
                threshold_value=5.0,
                condition="gt",
            ),
            SimpleNamespace(
                id=12,
                rule_name="Unknown Metric Rule",
                metric_name="not_available_metric",
                threshold_value=1.0,
                condition="gt",
            ),
        ]

    async def fake_recent_rule_event(**_kwargs):
        return False

    async def fake_recent_system_event(**_kwargs):
        return False

    monkeypatch.setattr(analytics, "get_async_session", fake_get_async_session)
    monkeypatch.setattr(analytics, "_build_alert_metric_catalog", fake_build_catalog)
    monkeypatch.setattr(analytics, "_load_active_alert_rules", fake_load_rules)
    monkeypatch.setattr(analytics, "_has_recent_rule_event", fake_recent_rule_event)
    monkeypatch.setattr(analytics, "_has_recent_system_quota_event", fake_recent_system_event)

    result = asyncio.run(
        analytics.run_governance_alert_generation_job(
            tenant_id="tenant_test",
            workspace_id="workspace_test",
        )
    )

    assert result["status"] == "success"
    assert result["evaluated_rules"] == 2
    assert result["generated_rule_events"] == 1
    assert result["generated_quota_events"] == 1
    assert result["generated_events"] == 2
    assert "Unknown Metric Rule" in result["missing_metric_rules"]
    assert "monthly_events_pct" in result["breached_quota_metrics"]

    assert fake_session.committed is True
    assert len(fake_session.added) == 2
    assert all(isinstance(event, AnalyticsAlertEvent) for event in fake_session.added)
    assert any(event.rule_id == 11 for event in fake_session.added)
    assert any(event.rule_id is None for event in fake_session.added)
