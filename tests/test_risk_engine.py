from risk.risk_engine import RiskEngine
from main import detect_core_service_impact


def test_risk_levels():
    engine = RiskEngine()
    low = engine.evaluate(
        files_changed=1,
        sensitive_changes=[],
        api_change=False,
        db_model_change=False,
        impacted_repos=[],
        regression_failures=[],
        category_counts={"UI change": 1},
    )
    assert low["level"] == "LOW"

    medium = engine.evaluate(
        files_changed=10,
        sensitive_changes=["routes/api"],
        api_change=True,
        db_model_change=False,
        impacted_repos=["service"],
        regression_failures=[],
        category_counts={"API change": 2, "test change": 1},
    )
    assert medium["level"] == "MEDIUM"


def test_risk_level_high_for_db_and_regression():
    engine = RiskEngine()
    result = engine.evaluate(
        files_changed=5,
        sensitive_changes=["models/user"],
        api_change=False,
        db_model_change=True,
        impacted_repos=["users", "orders"],
        regression_failures=["orders"],
        category_counts={"database model change": 2},
    )
    assert result["level"] in ("HIGH", "CRITICAL")


def test_detect_core_service_impact():
    services = ["org/users", "org/orders", "microservice-notifications", "external/foo"]
    impacted = detect_core_service_impact(services)
    assert impacted == ["notifications", "orders", "users"]


def test_pr_analyzer_payload_response_detects_url_changes():
    from github.pr_analyzer import PRAnalyzer
    from config import Settings

    analyzer = PRAnalyzer(Settings())
    files = [
        {
            "filename": "routes/users.py",
            "additions": 3,
            "deletions": 1,
            "patch": "@@ -1,3 +1,5 @@\n+\"payload\": {\n+  \"userId\": \"string\"\n+}\n",
        }
    ]
    result = analyzer.analyze(files)
    assert result.payload_response_changes
    assert result.changed_urls == set()
