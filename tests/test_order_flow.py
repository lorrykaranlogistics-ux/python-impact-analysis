from __future__ import annotations

import asyncio
from typing import Any

import pytest

from microservices.order_flow import OrderMicroserviceOrchestrator, OrderWorkflowError


TEST_ITEMS = [
    {"sku": "widget-alpha", "quantity": 1, "price": 49.99},
    {"sku": "widget-beta", "quantity": 2, "price": 25},
]


def _run_orchestrator(*, fail_payment: bool = False) -> dict[str, Any]:
    orchestrator = OrderMicroserviceOrchestrator(mock_delay=0)

    async def runner():
        try:
            return await orchestrator.process_order(
                order_id="test-order-1",
                user_id="test-user",
                items=TEST_ITEMS,
                fail_payment=fail_payment,
            )
        finally:
            await orchestrator.shutdown()

    return asyncio.run(runner())


def test_order_workflow_success():
    result = _run_orchestrator()
    assert result["order"]["status"] == "created"
    assert result["payment"]["status"] == "charged"
    assert result["notifications"]["status"] == "sent"
    assert result["user_events"]["status"] == "recorded"


def test_order_workflow_payment_failure():
    with pytest.raises(OrderWorkflowError) as excinfo:
        _run_orchestrator(fail_payment=True)
    status = excinfo.value.status
    assert status["payment"]["status"] == "declined"
    assert status["notification"]["status"] == "sent"
