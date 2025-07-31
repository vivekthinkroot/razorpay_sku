from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    RAZORPAY_API_KEY: str
    RAZORPAY_API_SECRET: str
    TELEGRAM_BOT_TOKEN: str
    RAZORPAY_BASE_URL: str = "https://api.razorpay.com/v1"
    PAYMENT_CALLBACK_URL: str = "https://819acd42ed65.ngrok-free.app/payment_callback"
    DATABASE_URL: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
