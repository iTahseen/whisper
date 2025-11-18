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
history_db = db["history"]


async def convert_target(target: str):
    if target.isdigit():
        try:
            chat = await bot.get_chat(int(target))
            if chat.username:
                return f"@{chat.username}"
            else:
                name = chat.first_name or "User"
                return f"{name} ({target})"
        except:
            return target
    return target


@dp.message(F.text == "/start")
async def start_cmd(message):
    await message.answer(
        "👋 <b>Whisper Bot Ready!</b>\n\n"
        "Use inline mode:\n"
        "<code>@whositbot your message @username</code>\n\n"
        "<b>Only the target person can read it.</b>"
    )


@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    user_id = query.from_user.id

    if text == "":
        help_result = InlineQueryResultArticle(
            id="help",
            title="How to send a whisper",
            description="Usage: @whositbot your message @username",
            input_message_content=InputTextMessageContent(
                message_text=(
                    "<b>How to use:</b>\n"
                    "<code>@whositbot your secret message @username</code>"
                )
            ),
        )
        return await query.answer([help_result], cache_time=0)

    if text.endswith("@"):
        record = await history_db.find_one({"owner": user_id})

        if not record or len(record["targets"]) == 0:
            empty = InlineQueryResultArticle(
                id="no_history",
                title="No previous recipients",
                description="You haven't sent any whispers yet",
                input_message_content=InputTextMessageContent(
                    message_text="No whisper history available."
                ),
            )
            return await query.answer([empty], cache_time=0)

        message_without_at = text[:-1].strip()
        results = []

        # FIX: remove duplicates while preserving order
        unique_targets = list(dict.fromkeys(record["targets"]))

        for target in unique_targets:
            secret_id = str(uuid.uuid4())

            await collection.insert_one(
                {"_id": secret_id, "text": message_without_at, "target": target}
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Open Message", callback_data=f"open:{secret_id}")]
                ]
            )

            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=f"Send to {target}",
                    description=f"Whisper for {target}",
                    input_message_content=InputTextMessageContent(
                        message_text="<b>A secret message</b>"
                    ),
                    reply_markup=keyboard,
                )
            )

        return await query.answer(results, cache_time=0)

    parts = text.split()
    last = parts[-1]

    is_username = last.startswith("@") and len(last) > 1
    is_userid = last.isdigit()

    if is_username or is_userid:
        target_raw = last
        secret_message = " ".join(parts[:-1])
    else:
        if query.chat_type == "sender":
            target_raw = str(user_id)
            secret_message = text
        else:
            err = InlineQueryResultArticle(
                id="err",
                title="Missing username",
                description="Correct format: @whositbot your message @username",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Please add <b>@username</b> at the end."
                ),
            )
            return await query.answer([err], cache_time=0)

    target = await convert_target(target_raw)

    record = await history_db.find_one({"owner": user_id})

    if record:
        hist = record["targets"]
        if target in hist:
            hist.remove(target)
        hist.insert(0, target)
        hist = hist[:10]
        await history_db.update_one(
            {"owner": user_id},
            {"$set": {"targets": hist}}
        )
    else:
        await history_db.insert_one({"owner": user_id, "targets": [target]})

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
        return await callback.answer("Whisper expired or deleted.", show_alert=True)

    text = record["text"]
    target = record["target"]
    user = callback.from_user

    allowed = False

    if target.startswith("@") and user.username:
        if target.lower() == f"@{user.username}".lower():
            allowed = True

    if target.endswith(f"({user.id})"):
        allowed = True

    if target == str(user.id):
        allowed = True

    if not allowed:
        return await callback.answer(
            f"This is meant for {target}, not for you.",
            show_alert=True
        )

    popup = text[:200] + "..." if len(text) > 200 else text
    await callback.answer(popup, show_alert=True)


async def main():
    print("Whisper bot running with full history support…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
