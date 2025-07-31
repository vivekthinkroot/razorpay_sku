import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from telegram_bot import setup_bot
from app import app as fastapi_app
from background_tasks import poll_payment_status_every_n_seconds

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔁 App starting up...")
    bot_task = None
    background_task = None
    try:
        bot_task = asyncio.create_task(setup_bot())
        background_task = asyncio.create_task(poll_payment_status_every_n_seconds(60))
    except Exception as e:
        print(f"❌ Failed to start background tasks: {e}")
    
    yield

    print("🛑 App shutting down...")
    for task in (bot_task, background_task):
        if task:
            task.cancel()
    try:
        if bot_task:
            await bot_task
        if background_task:
            await background_task
    except asyncio.CancelledError:
        print("✅ Background tasks shutdown cleanly.")

fastapi_app.router.lifespan_context = lifespan
app = fastapi_app
