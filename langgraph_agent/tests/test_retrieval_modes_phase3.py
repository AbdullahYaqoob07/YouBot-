import pytest

from database.retrieval_modes import normalize_allowed_modes, recommend_retrieval_mode

knowledge_base_module = pytest.importorskip("tools.knowledge_base")
build_kb_namespace = knowledge_base_module.build_kb_namespace


def test_normalize_allowed_modes_defaults_to_rag():
    assert normalize_allowed_modes([]) == ["rag"]
    assert normalize_allowed_modes(["invalid"]) == ["rag"]


def test_recommend_page_index_for_compliance_heavy_profile():
    profile = {
        "compliance_criticality": 0.9,
        "average_document_pages": 60,
        "query_complexity": 0.5,
        "latency_budget_ms": 3000,
        "cost_sensitivity": 0.5,
    }
    result = recommend_retrieval_mode("check contract clause for policy compliance", profile)
    assert result["recommended_mode"] == "page_index"


def test_recommend_rag_for_low_latency_simple_query():
    profile = {
        "compliance_criticality": 0.3,
        "average_document_pages": 5,
        "query_complexity": 0.2,
        "latency_budget_ms": 1200,
        "cost_sensitivity": 0.5,
    }
    result = recommend_retrieval_mode("visa processing time", profile)
    assert result["recommended_mode"] == "rag"


def test_build_kb_namespace_with_tenant_workspace():
    namespace = build_kb_namespace("tenant-one", "workspace/main")
    assert namespace == "t_tenant-one__w_workspace_main"


def test_build_kb_namespace_falls_back_to_default():
    assert build_kb_namespace(None, None) == "sweden_relocators_v3"
