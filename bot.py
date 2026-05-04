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

# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPER_MANAGER_ID = int(os.getenv("MANAGER_ADMIN_ID", 0))

# Tekshirish
if not all([BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    logging.error("❌ XATOLIK: BOT_TOKEN, SUPABASE_URL yoki SUPABASE_KEY topilmadi!")
    logging.error(f"BOT_TOKEN: {'OK' if BOT_TOKEN else 'MISSING'}")
    logging.error(f"SUPABASE_URL: {'OK' if SUPABASE_URL else 'MISSING'}")
    logging.error(f"SUPABASE_KEY: {'OK' if SUPABASE_KEY else 'MISSING'}")

# O'zbekiston vaqt zonasi (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AdminState(StatesGroup):
    waiting_for_price = State()
    waiting_for_admin_id = State()
    waiting_for_admin_role = State()

# --- ADMINLARNI TEKSHIRISH ---
async def get_admin_role(user_id):
    try:
        res = supabase.table("admins").select("role").eq("id", user_id).execute()
        if res.data:
            return res.data[0]['role']
    except Exception as e:
        logging.error(f"Admin role tekshirishda xatolik: {e}")
    if user_id == SUPER_MANAGER_ID:
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

# --- STATUS TUGMALARI ---
def get_status_kb(lead_id):
    kb = [
        [
            types.InlineKeyboardButton(text="✅ Bog'lanildi", callback_data=f"st:done:{lead_id}"),
            types.InlineKeyboardButton(text="⌛ O'ylayapti", callback_data=f"st:wait:{lead_id}")
        ],
        [
            types.InlineKeyboardButton(text="❌ Rad etdi", callback_data=f"st:cancel:{lead_id}")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data.startswith("st:"))
async def process_status(callback: types.CallbackQuery):
    _, status, lead_id = callback.data.split(":")
    status_map = {"done": "✅ Bog'lanildi", "wait": "⌛ O'ylayapti", "cancel": "❌ Rad etdi"}
    
    supabase.table("leads").update({"status": status}).eq("id", lead_id).execute()
    await callback.answer(f"Status yangilandi: {status_map[status]}")
    await callback.message.edit_text(callback.message.text + f"\n\n📍 STATUS: {status_map[status]}")

# --- HAFTALIK HISOBOT ---
async def send_weekly_report():
    now = datetime.datetime.now(UZB_TZ)
    week_ago = (now - timedelta(days=7)).isoformat()
    
    res = supabase.table("leads").select("*").gte("created_at", week_ago).execute()
    leads = res.data
    
    if not leads:
        await bot.send_message(chat_id=SUPER_MANAGER_ID, text="📊 Bu hafta murojaatlar tushmadi.")
        return
    
    total = len(leads)
    done = len([l for l in leads if l.get('status') == 'done'])
    wait = len([l for l in leads if l.get('status') == 'wait'])
    cancel = len([l for l in leads if l.get('status') == 'cancel'])
    yangi = len([l for l in leads if l.get('status') in ('yangi', None, '')])
    
    # Manbalar (Instagram, Telegram va h.k.)
    sources = {}
    for l in leads:
        src = l.get('source', 'togriga')
        sources[src] = sources.get(src, 0) + 1
    
    src_text = "\n".join([f"🔹 {k.capitalize()}: {v} ta" for k, v in sources.items()])
    
    report = (f"📊 **HAFTALIK HISOBOT**\n"
              f"📅 {week_ago[:10]} dan boshlab\n\n"
              f"📥 Jami murojaatlar: {total} ta\n"
              f"━━━━━━━━━━━━━━━\n"
              f"✅ Bog'lanilgan: {done}\n"
              f"⌛ O'ylayapti: {wait}\n"
              f"❌ Rad etilgan: {cancel}\n"
              f"🆕 Hali ochilmagan: {yangi}\n\n"
              f"🌍 **MANBALAR:**\n{src_text}")
    
    await bot.send_message(chat_id=SUPER_MANAGER_ID, text=report)

async def scheduler():
    while True:
        now = datetime.datetime.now(UZB_TZ)
        # Shanba (5) soat 16:00 O'zbekiston vaqti
        if now.weekday() == 5 and now.hour == 16 and now.minute == 0:
            await send_weekly_report()
            await asyncio.sleep(60)  # Ikki marta yubormasligi uchun
        await asyncio.sleep(30)

# --- LEADLARNI TEKSHIRISH ---
async def check_leads():
    last_id = 0
    try:
        res = supabase.table("leads").select("id").order("id", desc=True).limit(1).execute()
        if res.data: last_id = res.data[0]['id']
    except Exception as e:
        logging.error(f"Boshlang'ich lead ID olishda xatolik: {e}")
    
    while True:
        try:
            new_leads = supabase.table("leads").select("*").gt("id", last_id).execute()
            if new_leads.data:
                admins_res = supabase.table("admins").select("id").eq("role", "lead_admin").order("id").execute()
                lead_admins = admins_res.data
                
                if lead_admins:
                    num_admins = len(lead_admins)
                    for lead in new_leads.data:
                        admin_index = lead['id'] % num_admins
                        target_admin_id = lead_admins[admin_index]['id']
                        
                        try:
                            time_str = datetime.datetime.fromisoformat(lead['created_at'].replace('Z', '+00:00')).astimezone(UZB_TZ).strftime('%H:%M, %d.%m.%Y')
                        except Exception:
                            time_str = lead.get('created_at', 'Noma\'lum')
                        
                        text = (f"🎯 **SIZGA MIJOZ BIRIKTIRILDI**\n\n"
                                f"📦 Paket: {lead['package']}\n"
                                f"👤 Ism: {lead['name']}\n"
                                f"📞 Tel: {lead['phone']}\n"
                                f"🏠 Xona: {lead['room']}\n"
                                f"🌍 Manba: {lead.get('source', 'togriga')}\n"
                                f"⏰ Vaqt: {time_str}")
                        
                        try:
                            await bot.send_message(chat_id=target_admin_id, text=text, reply_markup=get_status_kb(lead['id']))
                            logging.info(f"Lead #{lead['id']} -> Admin {target_admin_id} ga yuborildi")
                        except Exception as e:
                            logging.error(f"Lead #{lead['id']} yuborishda xatolik (Admin: {target_admin_id}): {e}")
                        
                        last_id = max(last_id, lead['id'])
                else:
                    logging.warning("Lead adminlar topilmadi! Supabase 'admins' jadvalini tekshiring.")
        except Exception as e:
            logging.error(f"Lead tekshirishda xatolik: {e}")
        await asyncio.sleep(10)

# --- KEEP ALIVE WEB SERVER (For Render) ---
async def handle(request):
    """Health check endpoint — Supabase ulanishini ham tekshiradi"""
    try:
        res = supabase.table("packages").select("key_name").limit(1).execute()
        db_status = "connected" if res.data is not None else "no data"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return web.json_response({
        "status": "running",
        "database": db_status,
        "timestamp": datetime.datetime.now(UZB_TZ).isoformat()
    })

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

async def main():
    # Web server va Botni parallel ishga tushiramiz
    await start_web_server()
    asyncio.create_task(check_leads())
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
