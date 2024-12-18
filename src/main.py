import asyncio
from typing import List, Dict
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
import logging
import json
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

class PaginationCallback(CallbackData, prefix="page"):
    action: str
    page: int

# Add these constants
USERS_PER_PAGE = 6


async def create_users_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()

    # Get user info for all users
    user_info = []
    for user_id in users:
        try:
            chat = await bot.get_chat(user_id)
            username = chat.username or f"User {user_id}"
            user_info.append((username, user_id))
        except Exception as e:
            logging.error(f"Error getting user info for {user_id}: {e}")
            continue

    # Calculate pagination
    total_pages = (len(user_info) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    start_idx = page * USERS_PER_PAGE
    end_idx = start_idx + USERS_PER_PAGE

    # Add user buttons for current page
    for username, user_id in user_info[start_idx:end_idx]:
        keyboard.add(InlineKeyboardButton(
            text=username,
            url=f"tg://user?id={user_id}"
        ))

    # Add navigation buttons if needed
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=PaginationCallback(action="prev", page=page - 1).pack()
        ))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=PaginationCallback(action="next", page=page + 1).pack()
        ))
    if row:
        keyboard.row(*row)

    return keyboard.as_markup()





logging.basicConfig(level=logging.INFO)

BOT_TOKEN = '7868672003:AAG_vj3ilteR036Bohazk3lLl1wIMSyuMBg'
CHANNEL_ID = '@gymtony1'
ADMIN_IDS = [583416877, 776113835]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def load_users():
    try:
        with open('users.json', 'r') as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()

def save_users():
    with open('users.json', 'w') as file:
        json.dump(list(users), file)

users = load_users()
media_groups: Dict[str, Dict] = {}


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id in users:
        await message.answer("Вы уже подписаны на рассылку! @gymtony1 📫")
    else:
        users.add(message.from_user.id)
        save_users()
        await message.answer("Добро пожаловать! Вы будете получать обновления из канала @gymtony1 📩")


def create_input_media(message: types.Message) -> types.InputMedia:
    if message.photo:
        return types.InputMediaPhoto(media=message.photo[-1].file_id)
    elif message.video:
        return types.InputMediaVideo(media=message.video.file_id)
    elif message.document:
        return types.InputMediaDocument(media=message.document.file_id)
    return None


async def send_content(user_id: int, message: types.Message, media_group: List[types.InputMedia] = None) -> bool:
    try:
        if media_group:
            # Split caption if it's too long
            caption = message.caption if message.caption else ""
            if len(caption) > 1024:  # Telegram's limit for media captions
                await bot.send_message(user_id, caption, parse_mode=ParseMode.HTML)
                media_group[0].caption = "Полное описание выше ⬆️"
            await bot.send_media_group(user_id, media_group)
        elif message.photo:
            # Для одиночных фото отправляем с caption
            await bot.send_photo(
                user_id,
                message.photo[-1].file_id,
                caption=message.caption,
                parse_mode=ParseMode.HTML
            )
        elif message.video:
            # Для одиночных видео отправляем с caption
            await bot.send_video(
                user_id,
                message.video.file_id,
                caption=message.caption,
                parse_mode=ParseMode.HTML
            )
        elif message.document:
            # Для одиночных документов отправляем с caption
            await bot.send_document(
                user_id,
                message.document.file_id,
                caption=message.caption,
                parse_mode=ParseMode.HTML
            )
        elif message.text:
            await bot.send_message(user_id, message.text, parse_mode=ParseMode.HTML)
        return True
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        return False


async def process_media_group(media_group_id: str):
    if media_group_id not in media_groups:
        return

    group_data = media_groups[media_group_id]
    media_list = group_data['media']
    message = group_data['message']

    # Set caption only for the first media item
    if media_list and message.caption:
        media_list[0].caption = message.caption
        media_list[0].parse_mode = ParseMode.HTML

    successful_deliveries = 0
    total_recipients = len(users)

    for user_id in users:
        success = await send_content(user_id, message, media_list)
        if success:
            successful_deliveries += 1

    stats_message = (
        "📊 Статистика рассылки:\n\n"
        f"👥 Всего получателей: {total_recipients}\n"
        f"✅ Успешно доставлено: {successful_deliveries}"
    )

    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, stats_message)

    del media_groups[media_group_id]

# Add the callback query handler for pagination
@dp.callback_query(PaginationCallback.filter())
async def process_pagination(callback: types.CallbackQuery, callback_data: PaginationCallback):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа к этой команде")
        return

    new_keyboard = await create_users_keyboard(callback_data.page)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer()


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    keyboard = await create_users_keyboard()
    await message.answer("Список получивших рассылку:", reply_markup=keyboard)


@dp.channel_post()
async def handle_channel_post(message: types.Message):
    if message.chat.username != CHANNEL_ID.replace('@', ''):
        return

    if message.media_group_id:
        if message.media_group_id not in media_groups:
            media_groups[message.media_group_id] = {
                'media': [],
                'message': message,
                'timer': None
            }

        group_data = media_groups[message.media_group_id]
        media = create_input_media(message)
        if media:
            group_data['media'].append(media)

        # Cancel existing timer if any
        if group_data['timer']:
            group_data['timer'].cancel()

        # Set new timer
        group_data['timer'] = asyncio.create_task(
            asyncio.sleep(0.5)
        )
        try:
            await group_data['timer']
            await process_media_group(message.media_group_id)
        except asyncio.CancelledError:
            pass


    else:  # Single message handling

        successful_deliveries = 0

        total_recipients = len(users)

        for user_id in users:

            success = await send_content(user_id, message, None)  # Передаем None вместо media

            if success:
                successful_deliveries += 1

        stats_message = (
            "📊 Статистика рассылки:\n\n"
            f"👥 Всего получателей: {total_recipients}\n"
            f"✅ Успешно доставлено: {successful_deliveries}"
        )

        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, stats_message)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())