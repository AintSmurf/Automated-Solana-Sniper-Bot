# notification/discord_bot.py
import discord
import asyncio
import os
import pandas as pd
from discord.ext import commands
from utilities.credentials_utility import CredentialsUtility
from utilities.excel_utility import ExcelUtility
from datetime import datetime
from helpers.logging_manager import LoggingHandler

logger = LoggingHandler.get_logger()


class Discord_Bot:
    def __init__(self):
        self.credentials_utility = CredentialsUtility()
        self.token = None

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.bot_ready = asyncio.Event()

        self.excel_utility = None
        self.last_row_counts = {}
        self.background_tasks: list[asyncio.Task] = []

        @self.bot.event
        async def on_ready():
            self.bot_ready.set()
            logger.info(f"✅ Discord bot logged in as {self.bot.user}")

    async def setup_hook(self):
        """
        discord.py async initialization hook.
        Runs inside the bot’s own loop before connecting.
        """
        self.excel_utility = ExcelUtility()
        watcher = asyncio.create_task(self.watch_excel_for_updates())
        self.background_tasks.append(watcher)
        logger.info("📊 Excel watcher task started")
    # --------- Public send API used by NotificationManager ---------
    async def send_message_to_discord(self, channel_name, content: str):
        await self.bot_ready.wait()
        channel = discord.utils.get(self.bot.get_all_channels(), name=channel_name)
        if channel:
            await channel.send(content)
        else:
            logger.warning(f"❌ Discord channel '{channel_name}' not found")

    async def send_message_from_sniper(self, token_mint, investment, choice, dexscreener_link):
        await self.bot_ready.wait()
        if choice == 1:
            msg = (
                f"🚨 **Passed first test - HoneyPot & mint authority** 🚨\n"
                f"🔹 **Mint:** `{token_mint}`\n"
                f"🔹 **Investment:** `{investment}`\n"
                f"🔹 **DexScreener**: <{dexscreener_link}>\n"
                f"⚠️ *More checks pending*"
            )
        else:
            msg = (
                f"🚀 **New Token Passed all tests** 🚀\n"
                f"🔹 **Mint:** `{token_mint}`\n"
                f"🔹 **Investment:** `{investment}`\n"
                f"🔹 **DexScreener**: <{dexscreener_link}>"
            )
        await self.send_message_to_discord("solana_tokens", msg)
    # ---------------- Background work ----------------
    async def watch_excel_for_updates(self):
        try:
            while True:
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                csv_name = f"discord_{date_str}.csv"
                await self._check_and_send_new_entries(self.excel_utility.BOUGHT_TOKENS, csv_name, 1)
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("🛑 Excel watcher task cancelled")

    async def _check_and_send_new_entries(self, folder, filename, message_type):
        path = os.path.join(folder, filename)
        required = ["Token_bought", "SentToDiscord"]

        # Wait until CSV exists + has required columns
        while True:
            if not os.path.exists(path):
                await asyncio.sleep(1)
                continue
            try:
                df = pd.read_csv(path)
                if not all(c in df.columns for c in required):
                    await asyncio.sleep(1)
                    continue
                break
            except Exception:
                await asyncio.sleep(1)

        df["SentToDiscord"] = df["SentToDiscord"].fillna(False).astype(bool)
        last = self.last_row_counts.get(path, 0)
        total = len(df)

        if total > last:
            new_rows = df.loc[~df["SentToDiscord"]]
            for index, row in new_rows.iterrows():
                try:
                    token_mint = row["Token_bought"]
                    investment = row.get("USD", "N/A")
                    link = f"https://dexscreener.com/solana/{token_mint}"
                    await self.send_message_from_sniper(token_mint, investment, message_type, link)
                    df.loc[index, "SentToDiscord"] = True
                except Exception as e:
                    logger.error(f"⚠️ Discord row {index} send error: {e}")

            df.to_csv(path, index=False)
            self.last_row_counts[path] = total
    # ---------------- Lifecycle ----------------
    async def run(self):
        self.token = self.credentials_utility.get_discord_token()
        await self.bot.start(self.token["DISCORD_TOKEN"])

    async def shutdown(self):
        logger.info("👋 Shutting down Discord bot...")
        for t in self.background_tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        await self.bot.close()
