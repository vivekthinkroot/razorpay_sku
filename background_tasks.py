import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select
from db import async_session
from models import UserSKU
from razorpay_client import RazorpayClient
import os

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


async def poll_payment_status_every_n_seconds(n: int = 60):
    client = RazorpayClient()

    while True:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(UserSKU).where(UserSKU.status.notin_(["paid", "expired"]))
                )
                links = result.scalars().all()
                now = datetime.now(timezone.utc)

                for link in links:
                    # Fetch latest status from Razorpay
                    razorpay_status = await client.check_payment_status(session, link.payment_link_id)

                    if razorpay_status == "paid":
                        link.status = "paid"
                    elif razorpay_status == "expired":
                        link.status = "expired"
                    elif link.created_at and now - link.created_at > timedelta(minutes=18):
                        # Internal expiry: more than 18 mins and still not paid
                        link.status = "expired"

                    session.add(link)

                await session.commit()
                print(f"✅ Checked {len(links)} links at {now.isoformat()}")

        except Exception as e:
            print(f"⚠️ Background task error: {e}")

        await asyncio.sleep(n)
