from analysis.change_classifier import ChangeClassifier, ChangeCategory


def test_sensitive_detection():
    classifier = ChangeClassifier(["routes/", "models/"])
    assert classifier.sensitive_changes(["routes/order.py"]) == ["routes/order.py"]
    assert classifier.classify("tests/test_orders.py") == ChangeCategory.TEST
    assert classifier.classify("controllers/payment.py") == ChangeCategory.API
    assert classifier.classify("models/order.py") == ChangeCategory.DATABASE
