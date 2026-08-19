import asyncio
import datetime
import logging
import urllib.parse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from openai import OpenAI

# OpenRouter API kaliti va Telegram bot tokeni
OPENROUTER_API_KEY = "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"
TELEGRAM_BOT_TOKEN = "8272858800:AAECj2teujjhoUWknCNFzRoBZThPTXaZpTk"

USER_DAILY_LIMIT = 500
user_usage = {}
user_histories = {}
user_roles = {}
secret_used_dates = {}  # Promo-kod kuniga 1 marta ishlatilganini saqlash uchun
user_blocks = {}        # Vaqtinchalik bloklangan foydalanuvchilar uchun

ADMIN_IDS = [7973480439]
total_bot_requests = 0

# So'kinish so'zlar ro'yxati
BAD_WORDS = ["tentak", "ahmoq", "durak", "skur", "blat", "blya", "suka", "ebal", "xuy"]

BASE_SYSTEM_INSTRUCTION = (
    "Sening isming AI yordamchi. Sen SH.Jahongir tomonidan yaratilgan o'ta aqlli va professional yordamchisan. "
    "Foydalanuvchi qaysi tilda yozsa, o'sha tilda mukammal va ravon javob ber. "
    "Foydalanuvchi biror sayt yoki ilovadan narsa qidirishni yoki kirishni so'rasa, unga yordam ber."
)

ROLE_INSTRUCTIONS = {
    "default": "Do'stona va yordamga tayyor sun'iy intellekt.",
    "coder": "Siz tajribali dasturchisiz. Kodlarni xatosiz yozasiz va tushuntirasiz.",
    "math": "Siz matematik olimsiz. Misol va masalalarni qadam-baqadam mukammal yechib berasiz.",
    "translator": "Siz Professional tarjimonsiz. Matnlarni ma'nosini buzmasdan mukammal tarjima qilasiz."
}

logging.basicConfig(level=logging.ERROR)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def check_user_limit(user_id: int) -> tuple[bool, int]:
    today = datetime.date.today()
    if user_id not in user_usage or user_usage[user_id]["date"] != today:
        user_usage[user_id] = {"count": 0, "date": today}

    current_count = user_usage[user_id]["count"]
    if current_count < USER_DAILY_LIMIT:
        return True, USER_DAILY_LIMIT - current_count
    return False, 0

def increment_user_limit(user_id: int):
    global total_bot_requests
    if user_id in user_usage:
        user_usage[user_id]["count"] += 1
    total_bot_requests += 1

def fetch_ai_response(user_id: int, text: str) -> str:
    if user_id not in user_histories:
        user_histories[user_id] = []
        
    current_role = user_roles.get(user_id, "default")
    system_text = f"{BASE_SYSTEM_INSTRUCTION} Hozirgi rejim: {ROLE_INSTRUCTIONS[current_role]}"

    messages = [{"role": "system", "content": system_text}]
    for h in user_histories[user_id][-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": text})

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct",
            messages=messages,
            max_tokens=1500,
            temperature=0.4,
        )
        reply_text = response.choices[0].message.content
        if reply_text:
            user_histories[user_id].append({"role": "user", "content": text})
            user_histories[user_id].append({"role": "assistant", "content": reply_text})
            return reply_text
        return "Javob olinmadi."
    except Exception as e:
        return f"API xatoligi: {str(e)}"

async def send_message_with_dynamic_links(update: Update, text: str, footer: str = ""):
    full_text = text + (f"\n\n{footer}" if footer else "")
    raw_msg = update.message.text or ""
    msg_lower = raw_msg.lower()
    
    reply_markup = None
    keyboard = []

    if "youtube" in msg_lower or "yt" in msg_lower:
        query = raw_msg.lower().replace("youtube", "").replace("yt", "").replace("da", "").replace("dan", "").replace("qidir", "").replace("top", "").strip()
        if query:
            encoded_query = urllib.parse.quote(query)
            keyboard.append([InlineKeyboardButton(f"🔍 YouTube'da '{query}' ni qidirish", url=f"https://www.youtube.com/results?search_query={encoded_query}")])
        else:
            keyboard.append([InlineKeyboardButton("▶️ YouTube'ni ochish", url="https://www.youtube.com")])
    elif "google" in msg_lower:
        query = raw_msg.lower().replace("google", "").replace("dan", "").replace("qidir", "").replace("top", "").strip()
        if query:
            encoded_query = urllib.parse.quote(query)
            keyboard.append([InlineKeyboardButton(f"🔍 Google'da '{query}' ni qidirish", url=f"https://www.google.com/search?q={encoded_query}")])
        else:
            keyboard.append([InlineKeyboardButton("🌐 Google'ni ochish", url="https://www.google.com")])
    elif "wikipedia" in msg_lower or "wiki" in msg_lower:
        query = raw_msg.lower().replace("wikipedia", "").replace("wiki", "").replace("dan", "").replace("qidir", "").replace("top", "").strip()
        if query:
            encoded_query = urllib.parse.quote(query)
            keyboard.append([InlineKeyboardButton(f"📚 Wikipedia'dan topish", url=f"https://uz.wikipedia.org/wiki/{encoded_query}")])
        else:
            keyboard.append([InlineKeyboardButton("📚 Wikipedia", url="https://uz.wikipedia.org")])

    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)

    if len(full_text) <= 4000:
        await update.message.reply_text(full_text, reply_markup=reply_markup)
    else:
        for i in range(0, len(full_text), 4000):
            await update.message.reply_text(full_text[i:i+4000], reply_markup=reply_markup if i == 0 else None)
            await asyncio.sleep(0.3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💻 Dasturchi", callback_data="role_coder"),
         InlineKeyboardButton("📐 Matematik", callback_data="role_math")],
        [InlineKeyboardButton("🌐 Tarjimon", callback_data="role_translator"),
         InlineKeyboardButton("🤖 Odatiy", callback_data="role_default")],
        [InlineKeyboardButton("🎨 Rasm yaratish", callback_data="feature_image"),
         InlineKeyboardButton("🎬 Video yaratish (20-25s)", callback_data="feature_video")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Salom! Men SH.Jahongir yaratgan mukammal AI yordamchisiman. Istalgan tilda yozavering, o'sha tilda javob beraman!\n\n"
        "⚠️ Eslatma: Botda so'kinish yoki haqoratli so'zlar ishlatilsa, bot sizni 1 kunga blok qilishi mumkin!\n\n"
        "💡 Limitingiz tugasa, kuniga 1 marta `/jahongir_0924` buyrug'i orqali qo'shimcha limit olishingiz mumkin.",
        reply_markup=reply_markup
    )

async def secret_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = datetime.date.today()
    
    if user_id in secret_used_dates and secret_used_dates[user_id] == today:
        await update.message.reply_text("⏳ Bu maxfiy buyruqdan faqat kuniga 1 marta foydalanish mumkin! Ertaga yana urinib ko'ring.")
        return

    if user_id not in user_usage or user_usage[user_id]["date"] != today:
        user_usage[user_id] = {"count": 0, "date": today}
    
    current_count = user_usage[user_id]["count"]
    new_count = max(0, current_count - 20)
    user_usage[user_id]["count"] = new_count
    
    secret_used_dates[user_id] = today
    
    remaining = USER_DAILY_LIMIT - new_count
    await update.message.reply_text(
        f"🎉 Tabriklayman! Maxfiy kod qabul qilindi va sizga 20 ta limit qo'shildi.\n"
        f"Qolgan limitingiz: {remaining}/{USER_DAILY_LIMIT}"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    data = query.data
    if data.startswith("role_"):
        role = data.split("_")[1]
        user_roles[user_id] = role
        role_names = {"coder": "Dasturchi 💻", "math": "Matematik 📐", "translator": "Tarjimon 🌐", "default": "Odatiy rejim 🤖"}
        await query.edit_message_text(f"✅ Rejim o'zgartirildi: **{role_names.get(role, '')}**")
    elif data == "feature_image":
        await query.message.reply_text("🖼 Rasm yaratish uchun `/image` so'zidan keyin prompt (matn) yozib yuboring.\nMasalan: `/image A futuristic flying car`")
    elif data == "feature_video":
        await query.message.reply_text("🎬 20-25 sekundlik video yaratish uchun `/video` so'zidan keyin prompt yozib yuboring.\nMasalan: `/video Cinematic drone shot of mountains`")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("Bu buyruq faqat admin uchun!")
        return
    await update.message.reply_text(f"📊 **Bot Statistikasi:**\n\n• Jami so'rovlar: {total_bot_requests} ta\n• Faol foydalanuvchilar: {len(user_usage)} ta")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    raw_text = update.message.text or update.message.caption or ""
    
    if not raw_text:
        return

    # 1. 1 kunlik bloklanganini tekshirish
    if user_id in user_blocks:
        unlock_time = user_blocks[user_id]
        if datetime.datetime.now() < unlock_time:
            await update.message.reply_text("🚫 Siz so'kinish qoidasini buzganingiz uchun 1 kunga botdan foydalanishdan bloklangansiz!")
            return
        else:
            del user_blocks[user_id]

    text_lower = raw_text.lower()

    # 2. So'kinishni tekshirish
    is_general_cursed = any(word in text_lower for word in BAD_WORDS)
    today = datetime.date.today()
    if user_id not in user_usage or user_usage[user_id]["date"] != today:
        user_usage[user_id] = {"count": 0, "date": today}

    if is_general_cursed:
        user_blocks[user_id] = datetime.datetime.now() + datetime.timedelta(days=1)
        await update.message.reply_text("⚠️ Odobsiz so'zlar ishlatganingiz uchun botdan 1 kunga bloklandingiz!")
        return

    # 3. /image va /video buyruqlarini tekshirish
    if raw_text.startswith("/image"):
        prompt = raw_text.replace("/image", "").strip()
        if not prompt:
            await update.message.reply_text("⚠️ Iltimos, rasm yaratish uchun matn kiriting. Masalan: `/image Qishloq manzarasi`")
            return
        await update.message.reply_text(f"🎨 '{prompt' bo'yicha rasm generatsiya qilinmoqda...")
        # Bu yerga rasm API kodingizni qo'shishingiz mumkin
        return

    if raw_text.startswith("/video"):
        prompt = raw_text.replace("/video", "").strip()
        if not prompt:
            await update.message.reply_text("⚠️ Iltimos, video yaratish uchun prompt kiriting. Masalan: `/video Neon city`")
            return
        await update.message.reply_text(f"🎬 '{prompt' bo'yicha 20-25 sekundlik video tayyorlanmoqda, iltimos kuting...")
        # Bu yerga video API kodingizni qo'shishingiz mumkin
        return

    # 4. Limitni tekshirish
    allowed, remaining = check_user_limit(user_id)
    if not allowed:
        await update.message.reply_text(
            f"⚠️ Bugungi limitingiz tugadi!\n"
            f"Kuniga 1 marta beriladigan imkoniyat uchun `/jahongir_0924` buyrug'ini yuboring."
        )
        return

    # 5. AI orqali javob berish
    loop = asyncio.get_running_loop()
    response_text = await loop.run_in_executor(None, fetch_ai_response, user_id, raw_text)

    if not response_text.startswith("API xatoligi:"):
        increment_user_limit(user_id)
        remaining -= 1

    footer = f"📉 *Qolgan limit:* {remaining}/{USER_DAILY_LIMIT}"
    await send_message_with_dynamic_links(update, response_text, footer)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("jahongir_0924", secret_limit_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot barcha eski va yangi funksiyalar bilan to'liq ishga tushdi...")
    app.run_polling(poll_interval=0.0)