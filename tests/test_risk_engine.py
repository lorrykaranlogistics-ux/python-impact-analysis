from risk.risk_engine import RiskEngine


def test_risk_levels():
    engine = RiskEngine()
    low = engine.evaluate(1, [], False, False, [], [])
    assert low["level"] == "LOW"
    medium = engine.evaluate(10, ["routes/api"], True, False, ["service"], [])
    assert medium["level"] == "MEDIUM"
