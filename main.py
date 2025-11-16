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
from motor.motor_asyncio import AsyncIOMotorClient

BOT_TOKEN = "6817290645:AAGG27rLGAIR6IWwO9zb2_lwpY2qzCXZ2cI"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

mongo_client = AsyncIOMotorClient(
    "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
db = mongo_client["whisperbot"]
collection = db["whispers"]


@dp.message(F.text == "/start")
async def start_cmd(message):
    await message.answer(
        "👋 **Whisper Bot Ready!**\n\n"
        "Use me in inline mode to send secret messages.\n\n"
        "`@whositbot your message @username`\n\n"
        "Only the target person can see the whisper.",
        parse_mode="Markdown",
    )


@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()

    # ------------------------------------
    # CHANGE 1 → Show instructions if empty
    # ------------------------------------
    if text == "":
        result = InlineQueryResultArticle(
            id="help",
            title="How to send a whisper",
            description="Usage: @whositbot your message @username",
            input_message_content=InputTextMessageContent(
                message_text=(
                    "**How to use:**\n"
                    "`@whositbot your secret message @username`\n\n"
                    "Example:\n"
                    "`@whositbot I love you @john`"
                ),
                parse_mode="Markdown",
            ),
        )
        return await query.answer([result], cache_time=0)

    parts = text.split()

    # ------------------------------------
    # CHANGE 2 → If in private chat & no username
    # ------------------------------------
    if len(parts) == 1:
        target = str(query.from_user.id)
        secret_message = parts[0]
    else:
        target = parts[-1]
        secret_message = " ".join(parts[:-1])

    secret_id = str(uuid.uuid4())

    await collection.insert_one(
        {"_id": secret_id, "text": secret_message, "target": target}
    )

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

    record = await collection.find_one({"_id": secret_id})

    if not record:
        return await callback.answer("Whisper not found.", show_alert=True)

    text = record["text"]
    target = record["target"]
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
    print("Whisper bot with MongoDB running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
