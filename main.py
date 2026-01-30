import os
import logging
import asyncio
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- CONFIG ---
TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_HOSTNAME') 
PORT = int(os.getenv('PORT', 5000))

WEBHOOK_PATH = f"/webhook/{TOKEN}"
BASE_URL = f"https://{RENDER_URL}"

# Images (Ссылки на твои скриншоты)
# Если ссылка перестанет работать, замени на актуальную
IMG_MAIN = "https://i.ibb.co/68v8zYp/1000081152.jpg" 
IMG_EARN = "https://i.ibb.co/zXyFfL6/1000081150.jpg"
IMG_WITHDRAW = "https://i.ibb.co/fGPn0W1/1000081155.jpg"
IMG_PROFILE = "https://i.ibb.co/L5rK5Q5/1000081151.jpg"
IMG_BONUS = "https://i.ibb.co/gP5WqFz/1000081154.jpg"
IMG_PROMO = "https://i.ibb.co/f2P6g8d/1000081153.jpg"
IMG_TOP = "https://i.ibb.co/vXpS6y0/1000081149.jpg"

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- KEYBOARDS ---
def get_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌟 Заработать звёзд", callback_data="earn"),
         InlineKeyboardButton(text="📥 Вывести звёзды", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="bonus")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo"),
         InlineKeyboardButton(text="🏆 Топ рефеводов", callback_data="top")]
    ])

def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ])

# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer_photo(
        photo=IMG_MAIN,
        caption="✅ Все проверки пройдены!\n\n✨ Добро пожаловать в <b>MumiStars</b>!",
        parse_mode="HTML",
        reply_markup=get_main_kb()
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(media=IMG_MAIN, caption="✨ Добро пожаловать в <b>MumiStars</b>!", parse_mode="HTML"),
            reply_markup=get_main_kb()
        )
    except Exception:
        await callback.answer()

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    text = (f"👤 Имя: <b>{callback.from_user.full_name}</b> 👑\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>\n"
            f"💰 Баланс: 4.50 ⭐\n"
            f"👥 Приглашено: 2")
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMG_PROFILE, caption=text, parse_mode="HTML"),
        reply_markup=get_back_kb()
    )

@dp.callback_query(F.data == "earn")
async def earn(callback: types.CallbackQuery):
    text = ("<b>ТВОЯ ССЫЛКА</b>\n\n"
            "За каждого друга ты получаешь +8.5⭐!\n\n"
            f"🔗 Твоя ссылка:\n<code>https://t.me/MumiStarsBot?start={callback.from_user.id}</code>\n\n"
            "🎉 Приглашай друзей и зарабатывай!")
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMG_EARN, caption=text, parse_mode="HTML"),
        reply_markup=get_back_kb()
    )

@dp.callback_query(F.data == "withdraw")
async def withdraw(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="25 ⭐", callback_data="w"), InlineKeyboardButton(text="50 ⭐", callback_data="w")],
        [InlineKeyboardButton(text="100 ⭐", callback_data="w"), InlineKeyboardButton(text="300 ⭐", callback_data="w")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMG_WITHDRAW, caption="<b>ВЫВОД ЗВЕЗДОЧЕК</b> ⭐\n\nВыберите сумму вывода:", parse_mode="HTML"),
        reply_markup=kb
    )

@dp.callback_query(F.data == "bonus")
async def bonus(callback: types.CallbackQuery):
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMG_BONUS, caption="<b>ВЫ ПОЛУЧИЛИ БОНУС</b> 🎁\n\n🎉 Вам начислено 0.5 ⭐ бонуса!", parse_mode="HTML"),
        reply_markup=get_back_kb()
    )

@dp.callback_query(F.data == "promo")
async def promo(callback: types.CallbackQuery):
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMG_PROMO, caption="<b>ВВЕДИ ПРОМОКОД</b> 🎁\n\n✏️ Введите промокод:", parse_mode="HTML"),
        reply_markup=get_back_kb()
    )

@dp.callback_query(F.data == "top")
async def top(callback: types.CallbackQuery):
    text = ("<b>ТОП ПО ПРИГЛАШЕНИЯМ</b> 🏆\n\n"
            "🫂 Топ по рефералам за сегодня (МСК):\n\n"
            "1. ✨°•мария_чалкова•°✨ - 1 реф.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 За все время", callback_data="top_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMG_TOP, caption=text, parse_mode="HTML"),
        reply_markup=kb
    )

# --- WEBHOOK LOGIC ---
async def on_startup(bot: Bot) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(f"{BASE_URL}{WEBHOOK_PATH}")

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
