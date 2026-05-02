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

load_dotenv()

# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPER_MANAGER_ID = int(os.getenv("MANAGER_ADMIN_ID", 0))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AdminState(StatesGroup):
    waiting_for_price = State()
    waiting_for_admin_id = State()
    waiting_for_admin_role = State()

# --- ADMINLARNI TEKSHIRISH ---
async def get_admin_role(user_id):
    if user_id == SUPER_MANAGER_ID: return "super_manager"
    res = supabase.table("admins").select("role").eq("id", user_id).execute()
    return res.data[0]['role'] if res.data else None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    role = await get_admin_role(message.from_user.id)
    if role in ["super_manager", "manager"]:
        kb = [[types.KeyboardButton(text="💰 Narxlarni o'zgartirish")]]
        if role == "super_manager":
            kb.append([types.KeyboardButton(text="👤 Adminlarni boshqarish")])
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer(f"Xush kelibsiz {role.replace('_', ' ').capitalize()}!", reply_markup=keyboard)
    elif role == "lead_admin":
        await message.answer("Xush kelibsiz Lead Admin! Yangi murojaatlar sizga avtomatik keladi.")
    else:
        await message.answer(f"Sizning ID: {message.from_user.id}\nRuxsat yo'q.")

# --- ADMINLARNI BOSHQARISH (Faqat Super Manager uchun) ---
@dp.message(F.text == "👤 Adminlarni boshqarish")
async def manage_admins(message: types.Message):
    if await get_admin_role(message.from_user.id) != "super_manager": return
    res = supabase.table("admins").select("*").execute()
    admins = res.data
    text = "Hozirgi xodimlar:\n"
    kb = []
    for a in admins:
        role_label = "Menejer (Lead)" if a['role'] == "lead_admin" else "Manager (Narx)"
        text += f"- ID: {a['id']} ({role_label})\n"
        kb.append([types.InlineKeyboardButton(text=f"❌ Lavozimdan ozod qilish {a['id']}", callback_data=f"del_admin:{a['id']}")])
    kb.append([types.InlineKeyboardButton(text="➕ Yangi xodim qo'shish", callback_data="add_admin")])
    await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "add_admin")
async def ask_admin_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Yangi xodimning Telegram ID raqamini kiriting:")
    await state.set_state(AdminState.waiting_for_admin_id)

@dp.message(AdminState.waiting_for_admin_id)
async def ask_admin_role(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqam kiriting!")
        return
    await state.update_data(new_admin_id=int(message.text))
    kb = [
        [types.InlineKeyboardButton(text="📞 Lead Admin (Faqat lead oladi)", callback_data="set_role:lead_admin")],
        [types.InlineKeyboardButton(text="💰 Manager (Faqat narx o'zgartiradi)", callback_data="set_role:manager")]
    ]
    await message.answer("Lavozimni tanlang:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AdminState.waiting_for_admin_role)

@dp.callback_query(F.data.startswith("set_role:"), AdminState.waiting_for_admin_role)
async def process_add_admin(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]
    data = await state.get_data()
    admin_id = data['new_admin_id']
    try:
        supabase.table("admins").insert({"id": admin_id, "role": role}).execute()
        await callback.message.answer(f"✅ Xodim (ID: {admin_id}) {role} lavozimiga tayinlandi.")
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")
    await state.clear()

@dp.callback_query(F.data.startswith("del_admin:"))
async def process_del_admin(callback: types.CallbackQuery):
    if await get_admin_role(callback.from_user.id) != "super_manager": return
    admin_id = int(callback.data.split(":")[1])
    supabase.table("admins").delete().eq("id", admin_id).execute()
    await callback.message.answer(f"✅ Xodim (ID: {admin_id}) lavozimidan ozod qilindi.")

# --- NARXLARNI O'ZGARTIRISH (Faqat Manager va Super Manager uchun) ---
@dp.message(F.text == "💰 Narxlarni o'zgartirish")
async def show_packages(message: types.Message):
    role = await get_admin_role(message.from_user.id)
    if role not in ["super_manager", "manager"]: return
    res = supabase.table("packages").select("*").execute()
    kb = [[types.InlineKeyboardButton(text=f"{p['display_name']} (${p['price']})", callback_data=f"edit:{p['key_name']}")] for p in res.data]
    await message.answer("Paketni tanlang:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("edit:"))
async def process_edit(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(pkg_key=callback.data.split(":")[1])
    await callback.message.answer("Yangi narx:")
    await state.set_state(AdminState.waiting_for_price)

@dp.message(AdminState.waiting_for_price)
async def update_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    supabase.table("packages").update({"price": message.text}).eq("key_name", data['pkg_key']).execute()
    await message.answer("✅ Saytda narx o'zgardi.")
    await state.clear()

# --- LEADLARNI TEKSHIRISH ---
async def check_leads():
    last_id = 0
    res = supabase.table("leads").select("id").order("id", desc=True).limit(1).execute()
    if res.data: last_id = res.data[0]['id']
    
    while True:
        try:
            new_leads = supabase.table("leads").select("*").gt("id", last_id).execute()
            if new_leads.data:
                # FAQAT Lead Adminlarni olamiz
                admins = supabase.table("admins").select("id").eq("role", "lead_admin").execute()
                admin_ids = [a['id'] for a in admins.data]
                
                for lead in new_leads.data:
                    text = f"🔔 YANGI MUROJAAT!\n👤 {lead['name']}\n📞 {lead['phone']}\n📦 {lead['package']}"
                    for aid in admin_ids:
                        try: await bot.send_message(chat_id=aid, text=text)
                        except: pass
                    last_id = max(last_id, lead['id'])
        except Exception as e: logging.error(e)
        await asyncio.sleep(10)

async def main():
    asyncio.create_task(check_leads())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


