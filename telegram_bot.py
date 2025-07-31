import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import settings
import httpx
from sqlalchemy import select
from db import async_session
from models import UserSKU, SKU
from sqlalchemy import select


API_BASE_URL = "http://localhost:8000"
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


# SKUS = {
#     "sku-basic": ("Basic Plan - ₹100", 100),
#     "sku-premium": ("Premium Plan - ₹500", 500),
#     "sku-pro": ("Pro Plan - ₹1000", 1000),
# }
telegram_app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()


async def get_all_skus() -> list[SKU]:
    async with async_session() as session:
        result = await session.execute(select(SKU))
        skus = result.scalars().all()
        print("✅ Loaded SKUs from DB:")
        for sku in skus:
            print(f"  → {sku.id} | {sku.name} | {sku.amount} | {sku.validity}")
        return skus


# Optional: use this in polling
async def setup_bot():
    print("✅ Telegram bot polling started.")
    await telegram_app.run_polling()

# 👇 This is what FastAPI will import
__all__ = ["telegram_app"]

async def show_sku_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    skus = await get_all_skus()
    keyboard = [
        [InlineKeyboardButton(f"{sku.name} - ₹{sku.amount }", callback_data=str(sku.id))]
        for sku in skus
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("Choose a plan to buy:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Choose a plan to buy:", reply_markup=reply_markup)

async def get_first_chat_id():
    url = f"{TELEGRAM_API_BASE}/getUpdates"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        updates = response.json()
        # Extract the latest valid chat_id
        for result in reversed(updates.get("result", [])):
            message = result.get("message")
            if message and "chat" in message:
                return message["chat"]["id"]
    raise Exception("No chat_id found. Please send a message to the bot first.")

async def send_payment_link_to_telegram(link: str, name: str):
    chat_id = await get_first_chat_id()
    message = f"Hi {name}, please complete your payment:\n{link}"
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=payload)
        response.raise_for_status()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_sku_options(update, context)

async def greet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_sku_options(update, context)




async def handle_sku_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sku_id = query.data
    user_id = str(query.from_user.id)

    async with async_session() as session:
        # Convert string to int since model expects integer
        try:
            sku_id_int = int(sku_id)
        except ValueError:
            await query.message.reply_text("❌ Invalid plan selected.")
            return
            
        result = await session.execute(select(SKU).where(SKU.id == sku_id_int))
        sku = result.scalar_one_or_none()

        if not sku:
            await query.message.reply_text("❌ Invalid plan selected.")
            return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BASE_URL}/create-payment-link",
                json={"user_id": user_id, "sku_id": sku.sku_id},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            payment_url = data.get("payment_url") or data.get("short_url")

            if not payment_url:
                raise ValueError("No payment URL returned.")

            await query.message.reply_text(
                f"✅ {sku.name}\nHere is your Razorpay payment link:\n{payment_url} \nThe link will expire in 18 minutes"
            )

    except httpx.RequestError:
        await query.message.reply_text("❌ Error: Backend not reachable.")
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    FASTAPI_BASE_URL = API_BASE_URL  # Already defined as "http://localhost:8000"

    # 1. Fetch latest payment link for this user
    async with async_session() as session:
        result = await session.execute(
            select(UserSKU)
            .where(UserSKU.user_id == user_id)
            .order_by(UserSKU.created_at.desc())
            .limit(1)
        )
        user_sku = result.scalar_one_or_none()

        if not user_sku:
            await update.message.reply_text("❌ No payment record found.")
            return

        payment_link_id = user_sku.payment_link_id

    # 2. Call FastAPI to get status
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/status/{payment_link_id}")
            if response.status_code != 200:
                await update.message.reply_text("⚠️ Could not fetch payment status.")
                return

            data = response.json()
            status = data.get("status", "unknown").upper()
            # short_url = data.get("short_url", "N/A")

            masked_id = '*' * (len(payment_link_id) - 6) + payment_link_id[-6:]

            msg = (
                f"💳 *Payment Status*\n"
                f"🔗 Link ID: `{masked_id}`\n"
                f"💰 Amount: ₹{user_sku.amount}\n"
                f"🛍️ SKU: {user_sku.sku_id}\n"
                f"📄 Status: *{status}*"
            )

            if status == "PAID":
                msg += "\n\n✅ Payment received. Thank you!"
            elif status == "CREATED":
                msg += f"\n\n🕐 Payment pending."
            else:
                msg += "\n\n⚠️ Payment expired or failed."

            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text("❌ Internal error. Please try again later.")
        raise e


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^hello$"), greet))
telegram_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^plans$"), show_sku_options))
telegram_app.add_handler(CallbackQueryHandler(handle_sku_selection))
telegram_app.add_handler(CommandHandler("status", status_command))



