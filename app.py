from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from db import get_session
from razorpay_client import RazorpayClient
from models import SKU, PaymentLinkResponse, PaymentStatusResponse, PaymentLinkRequest
from telegram import Update
from telegram_bot import telegram_app
from config import settings
import traceback

app = FastAPI()
razorpay_client = RazorpayClient()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/webhook")
async def telegram_webhook(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data, telegram_app.bot)
    await telegram_app.initialize()
    await telegram_app.process_update(update)
    return {"ok": True}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

from sqlmodel import select

@app.post("/create-payment-link", response_model=PaymentLinkResponse)
async def create_payment_link(
    request: PaymentLinkRequest, session: AsyncSession = Depends(get_session)
):
    print(f"Received request: {request}")
    try:
        query = select(SKU).where(SKU.sku_id == request.sku_id)
        result = await session.execute(query)
        sku = result.scalar_one_or_none()

        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")

        response = await razorpay_client.create_payment_link(
            user_id=request.user_id,
            sku_id=request.sku_id,
            amount=sku.amount,
            session=session
        )
        return response

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{payment_link_id}", response_model=PaymentStatusResponse)
async def check_status(
    payment_link_id: str, session: AsyncSession = Depends(get_session)
):
    try:
        return await razorpay_client.check_payment_status(session, payment_link_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


