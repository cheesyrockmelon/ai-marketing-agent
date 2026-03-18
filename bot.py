"""
AI Marketing Brief Bot — Telegram entry point.

Send /brief to @AImktg_bot to get the latest AI marketing trends brief.

Run locally:  python bot.py
Deploy:       Push to GitHub → connect on Railway → set env vars
"""

import asyncio
import logging
import os
import time

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from agent import run_research

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Prevent hammering — one request per 60s
_last_run: float = 0
COOLDOWN_SECONDS = 60


async def brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _last_run

    now = time.time()
    if now - _last_run < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - _last_run))
        await update.message.reply_text(f"Still cooling down. Try again in {remaining}s.")
        return

    _last_run = now
    await update.message.reply_text("Researching AI marketing trends across X, Reddit, Instagram, YouTube, and the web... (~30 sec)")

    try:
        brief = await asyncio.get_event_loop().run_in_executor(None, run_research)
        # Split into ≤4000-char chunks
        chunks = [brief[i : i + 4000] for i in range(0, len(brief), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="HTML", disable_web_page_preview=False)
        log.info("Brief delivered (%d chunk(s))", len(chunks))
    except Exception as e:
        log.exception("Research failed")
        await update.message.reply_text(f"Research failed: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "AI Marketing Brief Bot ready.\n\nSend /brief to get today's trending AI marketing topics."
    )


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("brief", brief_command))
    log.info("Bot started. Send /brief to @AImktg_bot")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
