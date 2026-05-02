import { Telegraf, Markup } from 'telegraf';
import { createClient } from '@supabase/supabase-js';

// --- SOZLAMALAR ---
const BOT_TOKEN = '8616950644:AAHVfNntuOEpFt2xQSHNORRF0yZpd7F7-CA';
const SUPABASE_URL = 'https://hddpzctigsjqljtooogq.supabase.co';
const SUPABASE_KEY = 'sb_publishable_pmUWBgFmG9mmPgJ0T8rEPw_OYV4ukd4';

const bot = new Telegraf(BOT_TOKEN);
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const userState = {};

// Asosiy menyu
const mainKeyboard = Markup.inlineKeyboard([
    [Markup.button.callback('💰 Narxlarni tahrirlash', 'menu_prices')],
    [Markup.button.callback('📝 Matnlarni tahrirlash', 'menu_texts')],
    [Markup.button.callback('🖼 Galereyani ko\'rish', 'view_gallery')],
]);

// Narxlar menyusi
const priceKeyboard = Markup.inlineKeyboard([
    [Markup.button.callback('Standart Narxi', 'set_val_price_standard')],
    [Markup.button.callback('Komfort Narxi', 'set_val_price_comfort')],
    [Markup.button.callback('LUX Narxi', 'set_val_price_lux')],
    [Markup.button.callback('LUX Premium Narxi', 'set_val_price_lux_premium')],
    [Markup.button.callback('14 Kunlik Narxi', 'set_val_price_14day')],
    [Markup.button.callback('⬅️ Orqaga', 'main_menu')]
]);

// Matnlar menyusi
const textKeyboard = Markup.inlineKeyboard([
    [Markup.button.callback('📦 Paket Nomlari', 'submenu_titles')],
    [Markup.button.callback('📄 Paket Tavsiflari', 'submenu_descs')],
    [Markup.button.callback('⬅️ Orqaga', 'main_menu')]
]);

// Paket nomlari menyusi
const titlesKeyboard = Markup.inlineKeyboard([
    [Markup.button.callback('Standart Nomi', 'set_val_title_standard')],
    [Markup.button.callback('Komfort Nomi', 'set_val_title_comfort')],
    [Markup.button.callback('LUX Nomi', 'set_val_title_lux')],
    [Markup.button.callback('LUX Premium Nomi', 'set_val_title_lux_premium')],
    [Markup.button.callback('⬅️ Orqaga', 'menu_texts')]
]);

// Paket tavsiflari menyusi
const descsKeyboard = Markup.inlineKeyboard([
    [Markup.button.callback('Standart Tavsifi', 'set_val_desc_standard')],
    [Markup.button.callback('Komfort Tavsifi', 'set_val_desc_comfort')],
    [Markup.button.callback('LUX Tavsifi', 'set_val_desc_lux')],
    [Markup.button.callback('LUX Premium Tavsifi', 'set_val_desc_lux_premium')],
    [Markup.button.callback('⬅️ Orqaga', 'menu_texts')]
]);

bot.start((ctx) => ctx.reply('Assalomu alaykum! Saytni boshqarish bo\'limiga xush kelibsiz:', mainKeyboard));

bot.action('main_menu', (ctx) => ctx.editMessageText('Asosiy menyu:', mainKeyboard));
bot.action('menu_prices', (ctx) => ctx.editMessageText('Qaysi narxni o\'zgartiramiz?', priceKeyboard));
bot.action('menu_texts', (ctx) => ctx.editMessageText('Matnlarni tahrirlash:', textKeyboard));
bot.action('submenu_titles', (ctx) => ctx.editMessageText('Qaysi paket nomini o\'zgartiramiz?', titlesKeyboard));
bot.action('submenu_descs', (ctx) => ctx.editMessageText('Qaysi paket tavsifini o\'zgartiramiz?', descsKeyboard));

// Qiymatni o'zgartirishni boshlash
bot.action(/^set_val_(.+)$/, (ctx) => {
    const key = ctx.match[1];
    userState[ctx.from.id] = { action: 'awaiting_value', key: key };
    ctx.reply(`✍️ ${key} uchun yangi matn yoki raqamni yuboring:`);
});

bot.on('text', async (ctx) => {
    const state = userState[ctx.from.id];
    if (state && state.action === 'awaiting_value') {
        const newValue = ctx.message.text.trim();

        const { error } = await supabase
            .from('site_settings')
            .update({ value: newValue })
            .eq('key', state.key);

        if (error) {
            ctx.reply('❌ Xatolik: ' + error.message);
        } else {
            ctx.reply(`✅ Tayyor! "${state.key}" yangilandi.`, mainKeyboard);
        }
        delete userState[ctx.from.id];
    }
});

// Galereya logikasi
bot.on('photo', async (ctx) => {
    const photo = ctx.message.photo[ctx.message.photo.length - 1];
    const fileLink = await ctx.telegram.getFileLink(photo.file_id);
    await supabase.from('gallery').insert([{ url: fileLink.href, type: 'image' }]);
    ctx.reply('📸 Rasm galereyaga qo\'shildi!', mainKeyboard);
});

bot.launch();
console.log('Bot ESM formatida ishga tushdi...');

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
