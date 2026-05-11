import asyncio, time, logging, re, os, sqlite3, aiohttp, html, shutil, zipfile
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.errors import ...
from telethon.tl.types import ...
from database import *

logger = logging.getLogger(__name__)

class BotSystem:
    def __init__(self, session_name, api_id, api_hash, bot_token, admin_id, log_channel, check_channels, join_urls, terms_url):
        self.API_ID = api_id
        self.API_HASH = api_hash
        self.BOT_TOKEN = bot_token
        self.ADMIN_ID = admin_id
        self.LOG_CHANNEL_ID = log_channel
        self.CHECK_CHANNELS = check_channels
        self.JOIN_URLS = join_urls
        self.TERMS_URL = terms_url

        # Session
        self.client = TelegramClient(session_name, self.API_ID, self.API_HASH)
        self.client.parse_mode = 'html'

        # Shared state
        self.active_orders = {}
        self.waiting_proof = {}
        self.deposit_input = {}
        self.admin_dep_state = {}
        self.user_spam_cooldown = {}
        self.session_buy_state = {}
        self.custom_dep_amt = {}
        self.user_locks = {}

        # Register handlers
        self.client.on(events.NewMessage(pattern=r"(?i)^/start"))(self.handle_start)
        self.client.on(events.NewMessage())(self.handle_all_messages)
        self.client.on(events.CallbackQuery)(self.handle_callback_query)

    # ---------- Handler implementations unchanged (use self.) ----------
    async def handle_start(self, event):
        # ... same code, all global references replaced with self. ...
        pass

    async def handle_all_messages(self, event):
        # ... same code ...
        pass

    async def handle_callback_query(self, event):
        # ... same code ...
        pass

    # ---------- Helper methods (process_referral_bonus, log_primary_deposit, etc.) ----------
    async def process_referral_bonus(self, uid, amount):
        # ... same code, using self.client.send_message ...
        pass

    # ... keep all other functions as methods ...

    async def start(self):
        await self.client.start(bot_token=self.BOT_TOKEN)
        # All handlers already registered
        logger.info("Bot started")
        await self.client.run_until_disconnected()