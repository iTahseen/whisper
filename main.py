import asyncio
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
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

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

mongo_client = AsyncIOMotorClient(
    "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
db = mongo_client["whisperbot"]
collection = db["whispers"]


@dp.message(F.text == "/start")
async def start_cmd(message):
    await message.answer(
        "👋 <b>Whisper Bot Ready!</b>\n\n"
        "Use me in inline mode:\n"
        "<code>@whositbot your message @username</code>\n\n"
        "<b>No one else can read your whisper.</b>"
    )


@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()

    # Empty → show instructions
    if text == "":
        help_result = InlineQueryResultArticle(
            id="help",
            title="How to send a whisper",
            description="Usage: @whositbot your message @username",
            input_message_content=InputTextMessageContent(
                message_text=(
                    "<b>How to use:</b>\n"
                    "<code>@whositbot your secret message @username</code>\n\n"
                    "Example:\n"
                    "<code>@whositbot I love you @john</code>"
                )
            ),
        )
        return await query.answer([help_result], cache_time=0)

    parts = text.split()
    last = parts[-1]

    is_username = last.startswith("@") and len(last) > 1
    is_userid = last.isdigit()

    # Proper target
    if is_username or is_userid:
        target = last
        secret_message = " ".join(parts[:-1])
    else:
        # NO TARGET GIVEN → Only allowed in Saved Messages
        if query.chat_type == "sender":
            target = str(query.from_user.id)
            secret_message = text
        else:
            error_result = InlineQueryResultArticle(
                id="err",
                title="Missing username",
                description="Correct: @whositbot your message @username",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Please add <b>@username</b> at the end."
                ),
            )
            return await query.answer([error_result], cache_time=0)

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
            message_text="<b>A secret message</b>"
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

    # Check target
    if target.isdigit():
        if int(target) == user.id:
            allowed = True
    elif target.startswith("@") and user.username:
        if target.lower() == f"@{user.username}".lower():
            allowed = True

    if not allowed:
        return await callback.answer("Not for you.", show_alert=True)

    popup = text
    if len(popup) > 200:
        popup = popup[:197] + "..."

    await callback.answer(popup, show_alert=True)


async def main():
    print("Whisper bot running…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
