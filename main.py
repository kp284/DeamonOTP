import asyncio, logging
from bot_system import BotSystem
from web_api import create_app
import uvicorn

# ---------- CONFIG ----------
API_ID = 32208414
API_HASH = "628f11c05a44c8dda4b006e66f4bf7df"
BOT_TOKEN = "8671527017:AAGnEOcXU4vXKNSywCXM_A1MjpbJEVpQFd4"
ADMIN_ID = 8640418772
LOG_CHANNEL_ID = -1003970256704
CHECK_CHANNELS = ["-1003350590878"]
JOIN_URLS = ["https://t.me/+urJLHFV-jp1mMDVl", "https://t.me/+urJLHFV-jp1mMDVl"]
TERMS_URL = "https://golden-sms-ro-bot.vercel.app/"
SESSION_NAME = f"bot_session_{BOT_TOKEN.split(':')[0]}"

async def main():
    # Initialize bot system
    bot = BotSystem(
        session_name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        admin_id=ADMIN_ID,
        log_channel=LOG_CHANNEL_ID,
        check_channels=CHECK_CHANNELS,
        join_urls=JOIN_URLS,
        terms_url=TERMS_URL
    )

    # Start telethon client
    await bot.client.start(bot_token=BOT_TOKEN)
    logging.info("Telegram bot started")

    # Create FastAPI app with bot reference (for notifications)
    app = create_app(bot)

    # Configure uvicorn server
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)

    # Run both concurrently
    await asyncio.gather(
        bot.client.run_until_disconnected(),
        server.serve()
    )

if __name__ == "__main__":
    asyncio.run(main())
