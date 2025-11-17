import asyncio
import re
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

# Helpers

async def normalize_and_validate_target(raw: str):
    """
    Accepts raw target (e.g. "@john", "12345", or "Name (12345)").
    Returns normalized target string if valid, else None.
    Normalized form:
      - "@username"  (if username exists)
      - "First (12345)" (if no username but get_chat succeeded)
      - "12345" (if numeric id exists but get_chat failed? we'll return None)
    """
    raw = raw.strip()
    # already normalized pattern: Name (ID) -> consider it valid if ID exists
    m = re.match(r"^(.+)\s+\((\d+)\)$", raw)
    if m:
        name, idstr = m.group(1), m.group(2)
        try:
            chat = await bot.get_chat(int(idstr))
            # return same display (freshen name if possible)
            if chat.username:
                return f"@{chat.username}"
            else:
                display_name = chat.first_name or name or "User"
                return f"{display_name} ({idstr})"
        except:
            return None

    # @username
    if raw.startswith("@"):
        username = raw[1:]
        if not username:
            return None
        try:
            chat = await bot.get_chat(username)
            if chat.username:
                return f"@{chat.username}"
            else:
                # improbable: get_chat succeeded but no username; use name(ID)
                name = chat.first_name or "User"
                return f"{name} ({chat.id})"
        except:
            return None

    # numeric id
    if raw.isdigit():
        try:
            chat = await bot.get_chat(int(raw))
            if chat.username:
                return f"@{chat.username}"
            else:
                name = chat.first_name or "User"
                return f"{name} ({raw})"
        except:
            return None

    return None


async def save_history_entry(owner_id: int, target_normalized: str):
    """
    Insert/update history for owner_id.
    Keep most recent first, unique, limit 10.
    """
    if not target_normalized:
        return

    rec = await history_db.find_one({"owner": owner_id})
    if rec:
        targets = rec.get("targets", [])
        # remove existing instance if present
        targets = [t for t in targets if t != target_normalized]
        targets.insert(0, target_normalized)
        targets = targets[:10]
        await history_db.update_one({"owner": owner_id}, {"$set": {"targets": targets}})
    else:
        await history_db.insert_one({"owner": owner_id, "targets": [target_normalized]})


async def prune_history_invalid(owner_id: int):
    """
    Validate saved history targets and remove invalid ones.
    Returns cleaned list.
    """
    rec = await history_db.find_one({"owner": owner_id})
    if not rec:
        return []
    kept = []
    for t in rec.get("targets", []):
        valid = await normalize_and_validate_target(t)
        if valid:
            if valid not in kept:
                kept.append(valid)
    if kept != rec.get("targets", []):
        # update DB with cleaned normalized list
        await history_db.update_one({"owner": owner_id}, {"$set": {"targets": kept}})
    return kept


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

    # HISTORY SUGGESTIONS (when user types trailing @)
    if text.endswith("@"):
        # clean and fetch history, removing invalid targets
        cleaned = await prune_history_invalid(user_id)
        if not cleaned:
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
        seen = set()

        for target in cleaned:
            if target in seen:
                continue
            seen.add(target)

            # create a real whisper for this suggestion
            secret_id = str(uuid.uuid4())
            # If message_without_at empty, store empty message (user can edit after sending)
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

            # limit suggestions to 10 (should already be <=10)
            if len(results) >= 10:
                break

        return await query.answer(results, cache_time=0)

    # NORMAL FLOW: parse potential target at end
    parts = text.split()
    last = parts[-1]
    is_username = last.startswith("@") and len(last) > 1
    is_userid = last.isdigit()

    if is_username or is_userid:
        target_raw = last
        secret_message = " ".join(parts[:-1])
        normalized = await normalize_and_validate_target(target_raw)
        if not normalized:
            # invalid target provided by user
            err = InlineQueryResultArticle(
                id="invalid_target",
                title="Invalid target",
                description="The username or ID you provided seems invalid",
                input_message_content=InputTextMessageContent(
                    message_text="❌ The username or ID you provided looks invalid."
                ),
            )
            return await query.answer([err], cache_time=0)

        target = normalized

    else:
        # only allow self-target when in Saved Messages (chat_type == "sender")
        if query.chat_type == "sender":
            target = str(user_id)
            secret_message = text
            # normalize self as display
            normalized_self = await normalize_and_validate_target(target)
            if normalized_self:
                target = normalized_self
        else:
            err = InlineQueryResultArticle(
                id="need_username",
                title="Missing username",
                description="Add @username at the end",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Please add <b>@username</b> at the end."
                ),
            )
            return await query.answer([err], cache_time=0)

    # Save whisper and history (history uses normalized target)
    secret_id = str(uuid.uuid4())
    await collection.insert_one({"_id": secret_id, "text": secret_message, "target": target})
    await save_history_entry(user_id, target)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Message", callback_data=f"open:{secret_id}")]
        ]
    )

    result = InlineQueryResultArticle(
        id=secret_id,
        title="Send Whisper",
        description=f"Secret message for {target}",
        input_message_content=InputTextMessageContent(message_text="<b>A secret message</b>"),
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
    # allowed if target is @username and matches user's username
    if target.startswith("@") and user.username:
        if target.lower() == f"@{user.username}".lower():
            allowed = True
    # allowed if target is "Name (id)"
    m = re.match(r".+\((\d+)\)$", target)
    if m:
        tid = m.group(1)
        if str(user.id) == tid:
            allowed = True
    # allowed if target is raw numeric string
    if target == str(user.id):
        allowed = True

    if not allowed:
        return await callback.answer(
            f"🚫 This whisper is meant for <b>{target}</b>, not for you 👀",
            show_alert=True
        )

    popup = text[:200] + "..." if len(text) > 200 else text
    await callback.answer(popup, show_alert=True)


async def main():
    print("Whisper bot running with deduped & validated history…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
