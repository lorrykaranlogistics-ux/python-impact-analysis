from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Iterable, List

import httpx

from utils.logger import setup_logger

logger = setup_logger("impact.micro.orders")

OrderItem = Dict[str, Any]
MockHandler = Callable[[Dict[str, Any]], Dict[str, Any]]

DEFAULT_SERVICE_ENDPOINTS: Dict[str, str] = {
    "orders": "mock://orders",
    "inventory": "mock://inventory",
    "payments": "mock://payments",
    "notifications": "mock://notifications",
    "users": "mock://users",
}


def _mock_order_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "created",
        "order_id": payload.get("order_id"),
        "total": payload.get("total"),
        "items": payload.get("items", []),
    }


def _mock_inventory_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "reserved",
        "reserve_id": f"reserve-{payload.get('order_id')}",
        "items": payload.get("items", []),
    }


def _mock_payments_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("simulate_failure"):
        status = "declined"
    else:
        status = "charged"
    return {
        "status": status,
        "transaction_id": f"txn-{payload.get('order_id')}",
        "amount": payload.get("amount"),
        "method": payload.get("method"),
    }


def _mock_notifications_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "sent",
        "order_id": payload.get("order_id"),
        "user_id": payload.get("user_id"),
        "channel": payload.get("channel"),
        "message": payload.get("message"),
    }


def _mock_users_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "recorded",
        "user_id": payload.get("user_id"),
        "order_id": payload.get("order_id"),
        "event": payload.get("event"),
    }


DEFAULT_MOCK_HANDLERS: Dict[str, MockHandler] = {
    "orders": _mock_order_handler,
    "inventory": _mock_inventory_handler,
    "payments": _mock_payments_handler,
    "notifications": _mock_notifications_handler,
    "users": _mock_users_handler,
}


class OrderWorkflowError(Exception):
    def __init__(self, message: str, status: Dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status or {}


class OrderMicroserviceOrchestrator:
    def __init__(
        self,
        *,
        endpoints: Dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        mock_delay: float = 0.05,
    ) -> None:
        self.endpoints: Dict[str, str] = {**DEFAULT_SERVICE_ENDPOINTS, **(endpoints or {})}
        self.client = client or httpx.AsyncClient(timeout=5.0)
        self._mock_handlers: Dict[str, MockHandler] = DEFAULT_MOCK_HANDLERS.copy()
        self.mock_delay = mock_delay
        self._owns_client = client is None

    async def process_order(
        self,
        order_id: str,
        user_id: str,
        items: Iterable[OrderItem],
        *,
        total_amount: float | None = None,
        payment_method: str = "card",
        channel: str = "email",
        fail_payment: bool = False,
    ) -> Dict[str, Any]:
        items_list: List[OrderItem] = [dict(item) for item in items]
        total = (
            total_amount
            if total_amount is not None
            else self._calculate_total(items_list)
        )

        logger.info("Starting order workflow %s for user %s", order_id, user_id)

        order_payload = {
            "order_id": order_id,
            "user_id": user_id,
            "items": items_list,
            "total": total,
        }
        order_response = await self._call_service("orders", "/create", order_payload)

        inventory_payload = {
            "order_id": order_id,
            "items": items_list,
        }
        inventory_response = await self._call_service("inventory", "/reserve", inventory_payload)

        payment_payload = {
            "order_id": order_id,
            "amount": total,
            "method": payment_method,
            "simulate_failure": fail_payment,
        }
        payment_response = await self._call_service("payments", "/charge", payment_payload)

        if payment_response.get("status") != "charged":
            failure_notification = await self._notify_user(
                order_id,
                user_id,
                channel,
                success=False,
                message="Order could not complete because payment was declined.",
            )
            raise OrderWorkflowError(
                "Payment failed while processing order",
                status={
                    "order": order_response,
                    "inventory": inventory_response,
                    "payment": payment_response,
                    "notification": failure_notification,
                },
            )

        notification_response = await self._notify_user(
            order_id,
            user_id,
            channel,
            success=True,
            message="Order completed successfully; we will notify you about delivery status.",
        )

        user_event_payload = {
            "order_id": order_id,
            "user_id": user_id,
            "event": "order_created",
            "details": {
                "items": items_list,
                "total": total,
            },
        }
        user_response = await self._call_service("users", "/events", user_event_payload)

        workflow_result = {
            "order": order_response,
            "inventory": inventory_response,
            "payment": payment_response,
            "notifications": notification_response,
            "user_events": user_response,
        }
        logger.info("Order workflow %s completed", order_id)
        return workflow_result

    async def _call_service(self, service: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = self.endpoints[service].rstrip("/")
        url = f"{endpoint}{path}"
        logger.debug("Contacting %s via %s", service, url)
        if endpoint.startswith("mock://"):
            return await self._mock_response(service, payload)
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def _mock_response(self, service: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(self.mock_delay)
        handler = self._mock_handlers.get(service)
        response = handler(payload) if handler else {"status": "mocked", "service": service}
        logger.debug("Mocked %s response: %s", service, response)
        return response

    async def _notify_user(
        self,
        order_id: str,
        user_id: str,
        channel: str,
        *,
        success: bool,
        message: str,
    ) -> Dict[str, Any]:
        payload = {
            "order_id": order_id,
            "user_id": user_id,
            "channel": channel,
            "success": success,
            "message": message,
        }
        return await self._call_service("notifications", "/notify", payload)

    @staticmethod
    def _calculate_total(items: List[OrderItem]) -> float:
        total = 0.0
        for item in items:
            quantity = item.get("quantity", 1)
            price = item.get("price", 0)
            try:
                quantity_value = int(quantity)
            except (TypeError, ValueError):
                quantity_value = 1
            try:
                price_value = float(price)
            except (TypeError, ValueError):
                price_value = 0.0
            total += quantity_value * price_value
        return total

    async def shutdown(self) -> None:
        if self._owns_client:
            await self.client.aclose()
