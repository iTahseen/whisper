import asyncio
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

BOT_TOKEN = "6817290645:AAGG27rLGAIR6IWwO9zb2_lwpY2qzCXZ2cI"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
SECRET_DB = {}


@dp.message(F.text == "/start")
async def start_cmd(message):
    await message.answer(
        "👋 **Whisper Bot Ready!**\n\n"
        "Use me in *inline mode* to send secret messages.\n\n"
        "`@whositbot your secret message @username`\n\n"
        "Only the target user will be able to open the whisper.",
        parse_mode="Markdown",
    )


@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    if not text:
        return

    parts = text.split()
    if len(parts) < 2:
        return

    target = parts[-1]
    secret_message = " ".join(parts[:-1])
    secret_id = str(uuid.uuid4())

    SECRET_DB[secret_id] = {"text": secret_message, "target": target}

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Message", callback_data=f"open:{secret_id}")]
        ]
    )

    result = InlineQueryResultArticle(
        id=secret_id,
        title="Send Whisper",
        description=f"Secret message for {target}",
        input_message_content=InputTextMessageContent(
            message_text="**A secret message**",
            parse_mode="Markdown",
        ),
        reply_markup=keyboard,
    )

    await query.answer([result], cache_time=0)


@dp.callback_query(F.data.startswith("open"))
async def open_whisper(callback: CallbackQuery):
    _, secret_id = callback.data.split(":")

    if secret_id not in SECRET_DB:
        return await callback.answer("Whisper expired.", show_alert=True)

    data = SECRET_DB[secret_id]
    text = data["text"]
    target = data["target"]
    user = callback.from_user

    allowed = False

    if target.isdigit():
        if int(target) == user.id:
            allowed = True
    elif target.startswith("@") and user.username:
        if target.lower() == f"@{user.username}".lower():
            allowed = True

    if not allowed:
        return await callback.answer("Not for you.", show_alert=True)

    popup_text = text
    if len(popup_text) > 200:
        popup_text = popup_text[:197] + "..."

    await callback.answer(popup_text, show_alert=True)


async def main():
    print("Whisper bot running (Aiogram 3.x)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
