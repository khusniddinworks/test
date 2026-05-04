import logging
import asyncio
import os
import datetime
from datetime import timedelta, timezone

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from supabase import create_client, Client
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- GLOBALS ---
supabase: Client = None
bot: Bot = None
dp = Dispatcher()

class AdminState(StatesGroup):
    waiting_for_price = State()
    waiting_for_admin_id = State()
    waiting_for_admin_role = State()

# O'zbekiston vaqt zonasi (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))

# --- ADMINLARNI TEKSHIRISH ---
async def get_admin_role(user_id):
    if not supabase: return None
    try:
        res = supabase.table("admins").select("role").eq("id", user_id).execute()
        if res.data:
            return res.data[0]['role']
    except Exception as e:
        logging.error(f"Admin role tekshirishda xatolik: {e}")
    
    super_id = int(os.getenv("MANAGER_ADMIN_ID", 0))
    if user_id == super_id:
        return "super_manager"
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    role = await get_admin_role(message.from_user.id)
    if role in ["super_manager", "manager"]:
        kb = [[types.KeyboardButton(text="💰 Narxlarni o'zgartirish")]]
        if role == "super_manager":
            kb.append([types.KeyboardButton(text="👤 Adminlarni boshqarish")])
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer(f"Xush kelibsiz! Sizning lavozimingiz: {role.replace('_', ' ').upper()}", reply_markup=keyboard)
    elif role == "lead_admin":
        await message.answer("Xush kelibsiz Lead Admin! Yangi murojaatlar sizga avtomatik keladi.")
    else:
        await message.answer(f"Sizning ID: {message.from_user.id}\nRuxsat yo'q.")

# --- NARXLARNI O'ZGARTIRISH ---
@dp.message(F.text == "💰 Narxlarni o'zgartirish")
async def show_packages(message: types.Message):
    role = await get_admin_role(message.from_user.id)
    if role not in ["super_manager", "manager"]: return
    if not supabase:
        await message.answer("Baza bilan ulanish mavjud emas.")
        return
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
    if supabase:
        supabase.table("packages").update({"price": message.text}).eq("key_name", data['pkg_key']).execute()
        await message.answer("✅ Saytda narx o'zgardi.")
    await state.clear()

# --- ADMINLARNI BOSHQARISH ---
@dp.message(F.text == "👤 Adminlarni boshqarish")
async def manage_admins(message: types.Message):
    if await get_admin_role(message.from_user.id) != "super_manager": return
    if not supabase: return
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
        [types.InlineKeyboardButton(text="📞 Lead Admin", callback_data="set_role:lead_admin")],
        [types.InlineKeyboardButton(text="💰 Manager", callback_data="set_role:manager")]
    ]
    await message.answer("Lavozimni tanlang:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AdminState.waiting_for_admin_role)

@dp.callback_query(F.data.startswith("set_role:"), AdminState.waiting_for_admin_role)
async def process_add_admin(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]
    data = await state.get_data()
    admin_id = data['new_admin_id']
    try:
        if supabase:
            supabase.table("admins").insert({"id": admin_id, "role": role}).execute()
            await callback.message.answer(f"✅ Xodim (ID: {admin_id}) {role} lavozimiga tayinlandi.")
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")
    await state.clear()

@dp.callback_query(F.data.startswith("del_admin:"))
async def process_del_admin(callback: types.CallbackQuery):
    if await get_admin_role(callback.from_user.id) != "super_manager": return
    admin_id = int(callback.data.split(":")[1])
    if supabase:
        supabase.table("admins").delete().eq("id", admin_id).execute()
        await callback.message.answer(f"✅ Xodim (ID: {admin_id}) lavozimidan ozod qilindi.")

# --- STATUS ---
def get_status_kb(lead_id):
    kb = [[types.InlineKeyboardButton(text="✅ Bog'lanildi", callback_data=f"st:done:{lead_id}"), types.InlineKeyboardButton(text="⌛ O'ylayapti", callback_data=f"st:wait:{lead_id}")], [types.InlineKeyboardButton(text="❌ Rad etdi", callback_data=f"st:cancel:{lead_id}")]]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data.startswith("st:"))
async def process_status(callback: types.CallbackQuery):
    _, status, lead_id = callback.data.split(":")
    status_map = {"done": "✅ Bog'lanildi", "wait": "⌛ O'ylayapti", "cancel": "❌ Rad etdi"}
    if supabase:
        supabase.table("leads").update({"status": status}).eq("id", lead_id).execute()
        await callback.answer(f"Status yangilandi: {status_map[status]}")
        await callback.message.edit_text(callback.message.text + f"\n\n📍 STATUS: {status_map[status]}")

# --- LEAD CHECK ---
async def check_leads():
    last_id = 0
    try:
        res = supabase.table("leads").select("id").order("id", desc=True).limit(1).execute()
        if res.data: last_id = res.data[0]['id']
    except: pass
    
    while True:
        try:
            new_leads = supabase.table("leads").select("*").gt("id", last_id).execute()
            if new_leads.data:
                admins_res = supabase.table("admins").select("id").eq("role", "lead_admin").execute()
                lead_admins = admins_res.data
                if lead_admins:
                    for lead in new_leads.data:
                        admin_id = lead_admins[lead['id'] % len(lead_admins)]['id']
                        text = f"🎯 **MIJOZ:**\n📦 {lead['package']}\n👤 {lead['name']}\n📞 {lead['phone']}\n🏠 {lead['room']}"
                        await bot.send_message(chat_id=admin_id, text=text, reply_markup=get_status_kb(lead['id']))
                        last_id = max(last_id, lead['id'])
        except: pass
        await asyncio.sleep(15)

# --- WEB SERVER ---
async def handle(request):
    return web.json_response({"status": "ok", "bot": "running"})

async def main():
    global supabase, bot
    
    # 1. Web serverni darhol ishga tushiramiz (Render uchun)
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🚀 Web server started on port {port}")

    # 2. Envlarni tekshirish va ulanish
    s_url = os.getenv("SUPABASE_URL")
    s_key = os.getenv("SUPABASE_KEY")
    b_token = os.getenv("BOT_TOKEN")

    if not all([s_url, s_key, b_token]):
        logging.error("❌ CRITICAL: Environment variables missing!")
        while True: await asyncio.sleep(3600) # To'xtab qolmasligi uchun

    try:
        supabase = create_client(s_url, s_key)
        bot = Bot(token=b_token)
        logging.info("✅ Connected to Supabase and Bot initialized")
    except Exception as e:
        logging.error(f"❌ Connection error: {e}")
        while True: await asyncio.sleep(3600)

    # 3. Fon vazifalarini boshlash
    asyncio.create_task(check_leads())
    
    # 4. Polling boshlash
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
