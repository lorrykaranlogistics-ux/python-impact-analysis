from __future__ import annotations

import asyncio

from microservices.order_flow import OrderMicroserviceOrchestrator, OrderWorkflowError


async def main() -> None:
    orchestrator = OrderMicroserviceOrchestrator(mock_delay=0.02)
    items = [
        {"sku": "users-widgets", "quantity": 2, "price": 27.5},
        {"sku": "notifications-card", "quantity": 1, "price": 15.0},
    ]
    try:
        result = await orchestrator.process_order(
            order_id="demo-2026-03",
            user_id="user-001",
            items=items,
            channel="email",
        )
        print("Order workflow completed:")
        for label, value in result.items():
            print(f"  {label}: {value}")
    except OrderWorkflowError as exc:
        print("Order workflow failed:", exc)
        if exc.status:
            print("  Details:", exc.status)
    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
