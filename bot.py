import logging
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import F
from supabase import create_client, Client
from dotenv import load_dotenv

# .env faylini yuklaymiz
load_dotenv()

# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MANAGER_ADMIN_ID = int(os.getenv("MANAGER_ADMIN_ID", 0))
LEAD_ADMIN_ID = int(os.getenv("LEAD_ADMIN_ID", 0))

# Supabase sozlamalari
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Logging (Faqat muhim xatolarni ko'rsatamiz)
logging.basicConfig(level=logging.WARNING)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class EditPackage(StatesGroup):
    waiting_for_price = State()

# --- ADMINLAR ---
def is_manager(user_id): return user_id == MANAGER_ADMIN_ID
def is_lead_admin(user_id): return user_id == LEAD_ADMIN_ID

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    if is_manager(uid):
        kb = [[types.KeyboardButton(text="💰 Narxlarni o'zgartirish")], [types.KeyboardButton(text="📊 Leadlarni ko'rish")]]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer("Xush kelibsiz Manager! Saytdagi narxlarni shu yerdan boshqaring.", reply_markup=keyboard)
    elif is_lead_admin(uid):
        await message.answer("Xush kelibsiz Lead Admin! Yangi murojaatlar sizga avtomatik keladi.")
    else:
        await message.answer(f"Sizning ID: {uid}\nBotdan foydalanish uchun ruxsat yo'q.")

@dp.message(F.text == "💰 Narxlarni o'zgartirish")
async def show_packages(message: types.Message):
    if not is_manager(message.from_user.id): return
    response = supabase.table("packages").select("*").execute()
    packages = response.data
    if not packages:
        await message.answer("Bazadan paketlar topilmadi.")
        return
    kb = []
    for pkg in packages:
        kb.append([types.InlineKeyboardButton(text=f"{pkg['display_name']} (${pkg['price']})", callback_data=f"edit:{pkg['key_name']}")])
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb)
    await message.answer("Qaysi paket narxini o'zgartiramiz?", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("edit:"))
async def process_edit(callback: types.CallbackQuery, state: FSMContext):
    pkg_key = callback.data.split(":")[1]
    await state.update_data(pkg_key=pkg_key)
    await callback.message.answer(f"Yangi narxni kiriting:")
    await state.set_state(EditPackage.waiting_for_price)

@dp.message(EditPackage.waiting_for_price)
async def update_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqam kiriting!")
        return
    data = await state.get_data()
    supabase.table("packages").update({"price": message.text}).eq("key_name", data['pkg_key']).execute()
    await message.answer(f"✅ Saytda narx {message.text} ga o'zgardi.")
    await state.clear()

# --- LEADLARNI TEKSHIRISH (POLLING) ---
async def check_leads():
    last_lead_id = 0
    # Eng oxirgi lead ID sini olib qo'yamiz (bot yoqilganda eski leadlar kelmasligi uchun)
    try:
        res = supabase.table("leads").select("id").order("id", desc=True).limit(1).execute()
        if res.data:
            last_lead_id = res.data[0]['id']
    except: pass

    while True:
        try:
            # Yangi leadlarni tekshirish
            res = supabase.table("leads").select("*").gt("id", last_lead_id).execute()
            for lead in res.data:
                logging.info(f"Yangi lead topildi: {lead['id']}")
                text = (f"🔔 YANGI MUROJAAT!\n\n"
                        f"👤 Ism: {lead['name']}\n"
                        f"📞 Tel: {lead['phone']}\n"
                        f"📦 Paket: {lead['package']}\n"
                        f"🏠 Xona: {lead['room']}")
                
                # DIQQAT: Faqat Lead Admin (Menejer) ga yuboramiz
                await bot.send_message(chat_id=LEAD_ADMIN_ID, text=text)
                
                last_lead_id = max(last_lead_id, lead['id'])
        except Exception as e:
            logging.error(f"Lead error: {e}")
        await asyncio.sleep(10) # Har 10 soniyada tekshiradi

async def main():
    # Leadlarni tekshirishni fonda ishga tushiramiz
    asyncio.create_task(check_leads())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


