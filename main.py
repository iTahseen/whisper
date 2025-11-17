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


async def normalize_and_validate_target(raw: str):
    """
    Try to validate/normalize raw target.
    Returns:
      - "@username"  (if username exists)
      - "12345678"   (raw numeric id) — accepted even if bot can't fetch user
      - None         (invalid username)
    Notes:
      - For numeric IDs we try get_chat; if it succeeds we convert to @username or keep as "User (ID)".
      - If get_chat fails for a numeric ID, we still accept the numeric ID (because validation may be impossible).
    """
    raw = raw.strip()
    if not raw:
        return None

    # If the user gave a username-like value " @name "
    if raw.startswith("@"):
        username = raw[1:].strip()
        if not username:
            return None
        try:
            chat = await bot.get_chat(username)
            if getattr(chat, "username", None):
                return f"@{chat.username}"
            else:
                # If chat exists but has no username, return ID string (we'll display name later)
                return str(chat.id)
        except Exception:
            # username truly invalid or inaccessible
            return None

    # If numeric ID
    if raw.isdigit():
        try:
            chat = await bot.get_chat(int(raw))
            if getattr(chat, "username", None):
                return f"@{chat.username}"
            else:
                # convert to raw id string (we can also display name later if needed)
                return str(chat.id)
        except Exception:
            # Can't verify with Telegram — accept raw numeric id anyway.
            return raw

    # If user passed "Name (ID)" pattern, extract ID and accept it (try to verify)
    m = re.match(r".+\((\d+)\)$", raw)
    if m:
        idstr = m.group(1)
        try:
            chat = await bot.get_chat(int(idstr))
            if getattr(chat, "username", None):
                return f"@{chat.username}"
            else:
                return str(chat.id)
        except Exception:
            # Accept raw ID inside the parentheses
            return idstr

    return None


async def display_target_label(target: str):
    """
    Return a friendly label for display in suggestions/errors:
      - If target starts with '@' -> '@username'
      - If target is numeric string -> try to get real name, else 'User (ID)'
    """
    if not target:
        return target
    if target.startswith("@"):
        return target
    if target.isdigit():
        try:
            chat = await bot.get_chat(int(target))
            if getattr(chat, "username", None):
                return f"@{chat.username}"
            else:
                name = chat.first_name or "User"
                return f"{name} ({target})"
        except Exception:
            # can't fetch name, return fallback
            return f"User ({target})"
    # fallback, already normalized
    return target


async def save_history_entry(owner_id: int, target_normalized: str):
    if not target_normalized:
        return
    rec = await history_db.find_one({"owner": owner_id})
    if rec:
        targets = rec.get("targets", [])
        targets = [t for t in targets if t != target_normalized]
        targets.insert(0, target_normalized)
        targets = targets[:10]
        await history_db.update_one({"owner": owner_id}, {"$set": {"targets": targets}})
    else:
        await history_db.insert_one({"owner": owner_id, "targets": [target_normalized]})


async def prune_and_get_history(owner_id: int):
    rec = await history_db.find_one({"owner": owner_id})
    if not rec:
        return []
    cleaned = []
    for t in rec.get("targets", []):
        v = await normalize_and_validate_target(t)
        if v and v not in cleaned:
            cleaned.append(v)
    if cleaned != rec.get("targets", []):
        await history_db.update_one({"owner": owner_id}, {"$set": {"targets": cleaned}})
    return cleaned


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

    # HISTORY SUGGESTIONS (trailing @)
    if text.endswith("@"):
        cleaned = await prune_and_get_history(user_id)
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
            await collection.insert_one(
                {"_id": secret_id, "text": message_without_at, "target": target}
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Open Message", callback_data=f"open:{secret_id}")]
                ]
            )

            label = await display_target_label(target)

            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=f"Send to {label}",
                    description=label,
                    input_message_content=InputTextMessageContent(
                        message_text="<b>A secret message</b>"
                    ),
                    reply_markup=kb,
                )
            )

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

        if normalized is None:
            # username is provably invalid
            err = InlineQueryResultArticle(
                id="invalid_target",
                title="Invalid username or ID",
                description="The username/ID you provided looks invalid",
                input_message_content=InputTextMessageContent(
                    message_text="❌ The username or ID you provided seems invalid. Make sure it exists on Telegram."
                ),
            )
            return await query.answer([err], cache_time=0)

        # normalized contains @username or raw numeric id string
        target = normalized

    else:
        # Only allow self-target when using Saved Messages (chat_type == "sender")
        if query.chat_type == "sender":
            secret_message = text
            # normalize self id if possible, else leave as raw id string
            normalized_self = await normalize_and_validate_target(str(user_id))
            target = normalized_self if normalized_self else str(user_id)
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

    # Save whisper + update history
    secret_id = str(uuid.uuid4())
    await collection.insert_one({"_id": secret_id, "text": secret_message, "target": target})
    await save_history_entry(user_id, target)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Message", callback_data=f"open:{secret_id}")]
        ]
    )

    label = await display_target_label(target)

    result = InlineQueryResultArticle(
        id=secret_id,
        title=f"Send Whisper to {label}",
        description=label,
        input_message_content=InputTextMessageContent(message_text="<b>A secret message</b>"),
        reply_markup=kb,
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

    m = re.match(r".+\((\d+)\)$", await display_target_label(target))
    if m:
        tid = m.group(1)
        if str(user.id) == tid:
            allowed = True

    if target == str(user.id):
        allowed = True

    if not allowed:
        label = await display_target_label(target)
        return await callback.answer(
            f"🚫 This whisper is meant for <b>{label}</b>, not for you 👀",
            show_alert=True
        )

    popup = text[:200] + "..." if len(text) > 200 else text
    await callback.answer(popup, show_alert=True)


async def main():
    print("Whisper bot running with tolerant ID handling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
