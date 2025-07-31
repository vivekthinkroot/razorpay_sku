from config import settings
import httpx
from sqlalchemy.future import select
from sqlmodel.ext.asyncio.session import AsyncSession
from models import UserSKU
from models import PaymentLinkResponse, PaymentStatusResponse
from db import async_session
from datetime import datetime, timedelta, timezone


class RazorpayClient:
    def __init__(self):
        self.auth = (settings.RAZORPAY_API_KEY, settings.RAZORPAY_API_SECRET)
        self.base_url = settings.RAZORPAY_BASE_URL

    async def expire_previous_links(self, session: AsyncSession, user_id: str):
        result = await session.execute(
            select(UserSKU).where(
                UserSKU.user_id == user_id,
                UserSKU.status.in_(["created", "pending"])
            )
        )
        unpaid_links = result.scalars().all()

        async with httpx.AsyncClient(auth=self.auth, timeout=10.0) as client:
            for link in unpaid_links:
                try:
                    await client.post(f"{self.base_url}/payment_links/{link.payment_link_id}/cancel")
                    link.status = "expired"
                    session.add(link)
                except httpx.HTTPStatusError as e:
                    print(f"Failed to expire link {link.payment_link_id}: {e}")

        await session.commit()

    async def create_payment_link(
        self, user_id: str, sku_id: str, amount: int, session: AsyncSession
    ) -> PaymentLinkResponse:
        
        # Expire all previous unpaid links
        await self.expire_previous_links(session, user_id)

        expire_by = int((datetime.now(timezone.utc) + timedelta(minutes=18)).timestamp())

        payload = {
            "amount": amount * 100,  # Convert to paise
            "currency": "INR",
            "customer": {"name": user_id or "anonymous"},
            "notify": {"sms": True, "email": True},
            "callback_url": settings.PAYMENT_CALLBACK_URL,
            "callback_method": "get",
            "expire_by": expire_by,
        }

        async with httpx.AsyncClient(auth=self.auth, timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/payment_links", json=payload)
            response.raise_for_status()
            data = response.json()

        user_sku = UserSKU(
            user_id=user_id,
            sku_id=sku_id,
            amount=amount,
            payment_link_id=data["id"],
            status=data["status"]
        )
        session.add(user_sku)
        await session.commit()

        return PaymentLinkResponse(
            payment_url=data["short_url"],
            payment_link_id=data["id"],
            status=data["status"]
        )

    async def get_payment_link_status(self, payment_link_id: str) -> dict:
        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.get(f"{self.base_url}/payment_links/{payment_link_id}")
            response.raise_for_status()
            return response.json()

    async def check_payment_status(
        self, session: AsyncSession, payment_link_id: str
    ) -> PaymentStatusResponse:
        data = await self.get_payment_link_status(payment_link_id)

        result = await session.execute(
            select(UserSKU).where(UserSKU.payment_link_id == payment_link_id)
        )
        user_sku = result.scalar_one_or_none()
        if not user_sku:
            raise ValueError("Payment link not found in database")

        if user_sku.status != data["status"]:
            user_sku.status = data["status"]
            session.add(user_sku)
            await session.commit()

        short_url = data.get("short_url") or data.get("url") or "N/A"

        return PaymentStatusResponse(
            status=data["status"],
            payment_link_id=payment_link_id,
            payment_url=short_url
        )


# Utility wrapper
async def create_payment_link_for_user(
    user_id: str, sku_id: str, amount: int
) -> PaymentLinkResponse:
    async with async_session() as session:
        client = RazorpayClient()
        return await client.create_payment_link(user_id, sku_id, amount, session)


async def get_payment_status(payment_link_id: str) -> PaymentStatusResponse:
    async with async_session() as session:
        client = RazorpayClient()
        return await client.check_payment_status(session, payment_link_id)
