import os
import sys
import time
import asyncio
import aiohttp
import json
import shutil
from datetime import datetime, timedelta

# --- ترفند Library Jacking ---
try:
    import apscheduler.util
    apscheduler.util.astimezone = lambda obj: obj
except: pass

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# --- تنظیمات ---
BOT_TOKEN = "8380318663:AAG4TPoTiGNbXPiOsfqcGerxPohXM9ZTIEg"
OWNER_ID = 1601379026
DB_FILE = "database.json"
BACKUP_FOLDER = "backups"
COOLDOWN_SECONDS = 15

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

API_LIST = [
    {"url": "https://api.fast-creat.ir/instagram", "key": "1601379026:f1j6tXDKMIlbsmR@Api_ManagerRoBot"},
    {"url": "https://api.fast-creat.ir/instagram", "key": "1482706652:3Bv7ILCJudlDAZp@Api_ManagerRoBot"},
    {"url": "https://api.fast-creat.ir/instagram", "key": "1884905096:wtgU29Lknc36xDl@Api_ManagerRoBot"}
]

# --- API اصلی (RapidAPI) --- کلید در Railway Variables با نام RAPID_KEY
RAPID_URL = "https://instagram-downloader-download-instagram-stories-videos4.p.rapidapi.com/convert"
RAPID_HOST = "instagram-downloader-download-instagram-stories-videos4.p.rapidapi.com"
RAPID_KEY = os.environ.get("RAPID_KEY", "")

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "force_join" not in data:
                    data["force_join"] = {"channels": []}
                if "admins" not in data:
                    data["admins"] = {}
                if "banned" not in data:
                    data["banned"] = {}
                if "users" not in data:
                    data["users"] = {}
                if "broadcast" not in data:
                    data["broadcast"] = {"messages": []}
                if "cooldown" not in data:
                    data["cooldown"] = {}
                if "stats" not in data:
                    data["stats"] = {"total_downloads": 0}
                if "admins" in data and "admins" in data["admins"]:
                    del data["admins"]["admins"]
                save_db(data)
                return data
        except Exception as e:
            print(f"Error loading db: {e}")
    return {"users": {}, "banned": {}, "force_join": {"channels": []}, "admins": {}, "broadcast": {"messages": []}, "cooldown": {}, "stats": {"total_downloads": 0}}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving db: {e}")

db = load_db()

http_session = None

async def post_init(application):
    global http_session
    http_session = aiohttp.ClientSession()
    application.create_task(auto_backup())

async def post_shutdown(application):
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()

def is_admin(user_id):
    user_id = str(user_id)
    if user_id == str(OWNER_ID):
        return True
    return user_id in db.get("admins", {})

def has_permission(admin_id, permission):
    admin_id = str(admin_id)
    if admin_id == str(OWNER_ID):
        return True
    return db.get("admins", {}).get(admin_id, {}).get("permissions", {}).get(permission, False)

# --- بکاپ خودکار ---
async def auto_backup():
    while True:
        await asyncio.sleep(86400)
        try:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_path = os.path.join(BACKUP_FOLDER, backup_name)
            shutil.copy(DB_FILE, backup_path)
            print(f"✅ Backup created: {backup_name}")
            backups = sorted([f for f in os.listdir(BACKUP_FOLDER) if f.endswith('.json')])
            while len(backups) > 7:
                os.remove(os.path.join(BACKUP_FOLDER, backups.pop(0)))
        except Exception as e:
            print(f"Backup error: {e}")

# --- توابع کمکی ---
def get_user_list_keyboard(page=1):
    users = list(db["users"].items())
    per_page = 4
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    keyboard = []
    for uid, info in users[start_idx:end_idx]:
        name = info.get("name", "Unknown")[:10]
        username = info.get("username", "None")
        is_banned = uid in db["banned"]
        status_icon = "🚫" if is_banned else "👤"
        keyboard.append([InlineKeyboardButton(f"{status_icon} {name} (@{username}) | {uid}", callback_data="none", style="primary")])
        ban_btn_text = "✅ رفع بن" if is_banned else "🚫 بن کردن"
        ban_callback = f"unban_{uid}_{page}" if is_banned else f"askban_{uid}_{page}"
        keyboard.append([InlineKeyboardButton(ban_btn_text, callback_data=ban_callback, style="danger")])
        keyboard.append([InlineKeyboardButton("--------------------------", callback_data="none", style="primary")])
    if page > 1:
        keyboard.append([InlineKeyboardButton("⬅️ قبلی", callback_data=f"page_{page-1}", style="success")])
    if end_idx < len(users):
        keyboard.append([InlineKeyboardButton("بعدی ➡️", callback_data=f"page_{page+1}", style="success")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_admin", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_banned_list_keyboard(page=1):
    banned = list(db["banned"].items())
    per_page = 5
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    keyboard = []
    for uid, info in banned[start_idx:end_idx]:
        name = db["users"].get(uid, {}).get("name", "Unknown")
        reason = info.get("reason", "بدون دلیل")
        until = info.get("until", "نامشخص")
        keyboard.append([InlineKeyboardButton(f"🚫 {name} | {uid}", callback_data="none", style="danger")])
        keyboard.append([InlineKeyboardButton(f"📝 دلیل: {reason} | تا: {until}", callback_data="none", style="danger")])
        keyboard.append([InlineKeyboardButton("--------------------------", callback_data="none", style="danger")])
    if page > 1:
        keyboard.append([InlineKeyboardButton("⬅️ قبلی", callback_data=f"banned_page_{page-1}", style="success")])
    if end_idx < len(banned):
        keyboard.append([InlineKeyboardButton("بعدی ➡️", callback_data=f"banned_page_{page+1}", style="primary")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_admin", style="primary")])
    return InlineKeyboardMarkup(keyboard)

def get_permissions_keyboard(admin_id):
    perms = db.get("admins", {}).get(admin_id, {}).get("permissions", {})
    keyboard = [
        [InlineKeyboardButton(f"{'✅' if perms.get('ban', False) else '❌'} بن کردن", callback_data=f"perm_ban_{admin_id}", style="primary")],
        [InlineKeyboardButton(f"{'✅' if perms.get('broadcast', False) else '❌'} پیام همگانی", callback_data=f"perm_broadcast_{admin_id}", style="success")],
        [InlineKeyboardButton(f"{'✅' if perms.get('set_permissions', False) else '❌'} تنظیم محدودیت", callback_data=f"perm_set_permissions_{admin_id}", style="success")],
        [InlineKeyboardButton(f"{'✅' if perms.get('view_admins', False) else '❌'} مشاهده لیست ادمین", callback_data=f"perm_view_admins_{admin_id}", style="danger")],
        [InlineKeyboardButton(f"{'✅' if perms.get('add_admin', False) else '❌'} افزودن ادمین", callback_data=f"perm_add_admin_{admin_id}", style="danger")],
        [InlineKeyboardButton(f"{'✅' if perms.get('remove_admin', False) else '❌'} حذف ادمین", callback_data=f"perm_remove_admin_{admin_id}", style="success")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin_menu", style="success")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- توابع جوین اجباری ---
async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channels = db.get("force_join", {}).get("channels", [])
    if not channels:
        return True
    user_id = update.effective_user.id
    for channel in channels:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ عضویت در کانال", url=f"https://t.me/{channel[1:] if channel.startswith('@') else channel}", style="danger")],
                    [InlineKeyboardButton("🔄 بررسی عضویت", callback_data="check_join", style="danger")]
                ])
                msg_text = "❌ برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:\n\n"
                for ch in channels:
                    msg_text += f"🔗 {ch}\n"
                if update.callback_query:
                    await update.callback_query.message.reply_text(msg_text, reply_markup=keyboard)
                else:
                    await update.message.reply_text(msg_text, reply_markup=keyboard)
                return False
        except:
            continue
    return True

async def force_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get("force_join", {}).get("channels", [])
    if not channels:
        await query.message.edit_text("✅ جوین اجباری غیرفعال است.\n\nلطفاً دستور /start را دوباره وارد کنید.")
        return
    user_id = update.effective_user.id
    all_joined = True
    for channel in channels:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                all_joined = False
                break
        except:
            all_joined = False
    if all_joined:
        await query.message.edit_text("✅ عضویت شما تأیید شد! حالا می‌توانید از ربات استفاده کنید.\n\nلطفاً دستور /start را دوباره وارد کنید.")
    else:
        await query.answer("❌ شما هنوز در همه کانال‌ها عضو نشده‌اید!", show_alert=True)

async def force_join_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get("force_join", {}).get("channels", [])
    channels_text = "\n".join([f"• {ch}" for ch in channels]) if channels else "هیچ کانالی ثبت نشده"
    text = f"🔒 مدیریت جوین اجباری\n━━━━━━━━━━━━━━━━━━\n📋 کانال‌های ثبت شده:\n{channels_text}\n━━━━━━━━━━━━━━━━━━"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن کانال", callback_data="add_channel", style="success")],
        [InlineKeyboardButton("🗑 حذف کانال", callback_data="remove_channel", style="primary")],
        [InlineKeyboardButton("📋 کانال‌های ثبت شده", callback_data="list_channels", style="danger")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="back_to_admin", style="success")]
    ])
    await query.message.edit_text(text, reply_markup=kb)

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["waiting_for_channel"] = "add"
    await query.message.reply_text("لطفاً آدرس کانال را ارسال کنید:\nمثال: @channel_username")

async def remove_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get("force_join", {}).get("channels", [])
    if not channels:
        await query.message.reply_text("❌ هیچ کانالی برای حذف وجود ندارد.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(ch, callback_data=f"remove_this_{ch}", style="danger")] for ch in channels] + [[InlineKeyboardButton("🔙 بازگشت", callback_data="force_join_menu", style="primary")]])
    await query.message.reply_text("کانال مورد نظر برای حذف را انتخاب کنید:", reply_markup=kb)

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get("force_join", {}).get("channels", [])
    text = "📋 لیست کانال‌های جوین اجباری:\n\n" + "\n".join([f"• {ch}" for ch in channels]) if channels else "هیچ کانالی ثبت نشده"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="force_join_menu", style="success")]])
    await query.message.edit_text(text, reply_markup=kb)

# --- پیام همگانی پیشرفته ---
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(update.effective_user.id, "broadcast") and update.effective_user.id != OWNER_ID:
        await query.message.reply_text("❌ **شما دسترسی «پیام همگانی» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
        return
    context.user_data["waiting_for_broadcast"] = True
    await query.message.reply_text("📢 **ارسال پیام همگانی**\n\nلطفاً متن، عکس یا ویدیوی خود را ارسال کنید.\n(می‌تواند شامل کپشن هم باشد)\n\nبرای لغو، دستور /cancel را بفرستید.", parse_mode="Markdown")

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not has_permission(user_id, "broadcast") and user_id != OWNER_ID:
        await update.message.reply_text("❌ شما دسترسی پیام همگانی را ندارید!")
        context.user_data["waiting_for_broadcast"] = False
        return
    
    msg = update.message
    success = 0
    fail = 0
    
    progress_msg = await update.message.reply_text("⏳ در حال ارسال پیام همگانی به همه کاربران...")
    
    for uid in db.get("users", {}):
        try:
            if msg.text:
                await context.bot.send_message(chat_id=int(uid), text=msg.text)
            elif msg.photo:
                await context.bot.send_photo(chat_id=int(uid), photo=msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(chat_id=int(uid), video=msg.video.file_id, caption=msg.caption)
            elif msg.document:
                await context.bot.send_document(chat_id=int(uid), document=msg.document.file_id, caption=msg.caption)
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    
    await progress_msg.edit_text(f"✅ **پیام همگانی ارسال شد!**\n\n📨 موفق: {success}\n❌ ناموفق: {fail}", parse_mode="Markdown")
    context.user_data["waiting_for_broadcast"] = False

# --- راهنمای ادمین ---
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = """📘 **راهنمای کامل پنل مدیریت**

➤ **📊 آمار**  
نمایش تعداد کل کاربران، بن‌شده‌ها، ادمین‌ها و کل دانلودهای موفق

➤ **👥 مدیریت کاربران**  
لیست تمام کاربران با قابلیت بن/آنبن (فقط ادمین‌های دارای دسترسی بن)

➤ **🚫 لیست بن‌شده‌ها**  
نمایش کاربران مسدود شده به همراه دلیل و زمان

➤ **👑 مدیریت ادمین‌ها**  
• افزودن ادمین جدید  
• حذف ادمین  
• مشاهده لیست ادمین‌ها  
• تنظیم محدودیت‌ها (بن، پیام همگانی، تنظیم محدودیت، مشاهده لیست ادمین، افزودن ادمین، حذف ادمین)

➤ **📢 پیام همگانی**  
ارسال متن، عکس یا ویدیو به تمام کاربران

➤ **🔒 جوین اجباری**  
تنظیم کانال‌هایی که کاربران باید عضو شوند

➤ **دستورات متنی**  
• /ban [ایدی] [روز] [دلیل]  
• /unban [ایدی]  
• /broadcast [متن]  
• /backup (فقط مالک) - ایجاد بکاپ دستی

➤ **نحوه دانلود از اینستاگرام**  
1. در اینستاگرام، روی سه نقطه (...) بالای پست کلیک کنید  
2. گزینه «کیپ لینک» را انتخاب کنید  
3. لینک را برای ربات ارسال کنید

⚠️ **نکته:** مالک ربات (شما) همه دسترسی‌ها را دارد و قابل بن نیست."""
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="back_to_admin", style="primary")]])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

# --- توابع مدیریت ادمین ---
async def admin_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(update.effective_user.id, "view_admins") and update.effective_user.id != OWNER_ID:
        await query.message.reply_text("❌ **شما دسترسی «مشاهده لیست ادمین» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin_start", style="primary")],
        [InlineKeyboardButton("🗑 حذف ادمین", callback_data="remove_admin_start", style="primary")],
        [InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="list_admins", style="danger")],
        [InlineKeyboardButton("⚙️ تنظیم محدودیت", callback_data="set_permissions_start", style="success")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="back_to_admin", style="primary")]
    ])
    await query.message.edit_text("👑 مدیریت ادمین‌ها\n━━━━━━━━━━━━━━━━━━", reply_markup=kb)

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(update.effective_user.id, "add_admin") and update.effective_user.id != OWNER_ID:
        await query.message.reply_text("❌ **شما دسترسی «افزودن ادمین» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
        return
    context.user_data["waiting_for_admin"] = "add"
    await query.message.reply_text("لطفاً آیدی عددی ادمین جدید را ارسال کنید:\nمثال: 123456789")

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(update.effective_user.id, "remove_admin") and update.effective_user.id != OWNER_ID:
        await query.message.reply_text("❌ **شما دسترسی «حذف ادمین» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
        return
    admins = db.get("admins", {})
    valid_admins = {aid: info for aid, info in admins.items() if aid.isdigit()}
    if not valid_admins:
        await query.message.reply_text("❌ هیچ ادمینی برای حذف وجود ندارد.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{db['users'].get(aid, {}).get('name', 'Unknown')} | {aid}", callback_data=f"remove_admin_{aid}", style="danger")] for aid in valid_admins] + [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin_menu", style="danger")]])
    await query.message.reply_text("ادمین مورد نظر برای حذف را انتخاب کنید:", reply_markup=kb)

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "👑 لیست ادمین‌ها:\n━━━━━━━━━━━━━━━━━━\n"
    text += f"👑 مالک ربات: {OWNER_ID}\n"
    for aid, info in db.get("admins", {}).items():
        if aid.isdigit():
            name = db["users"].get(aid, {}).get("name", "Unknown")
            text += f"\n• {name} | {aid}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin_menu", style="success")]])
    await query.message.edit_text(text, reply_markup=kb)

async def set_permissions_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(update.effective_user.id, "set_permissions") and update.effective_user.id != OWNER_ID:
        await query.message.reply_text("❌ **شما دسترسی «تنظیم محدودیت» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
        return
    admins = db.get("admins", {})
    valid_admins = {aid: info for aid, info in admins.items() if aid.isdigit()}
    if not valid_admins:
        await query.message.reply_text("❌ هیچ ادمینی برای تنظیم محدودیت وجود ندارد.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{db['users'].get(aid, {}).get('name', 'Unknown')} | {aid}", callback_data=f"set_perm_{aid}", style="success")] for aid in valid_admins] + [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin_menu", style="danger")]])
    await query.message.reply_text("ادمین مورد نظر برای تنظیم محدودیت را انتخاب کنید:", reply_markup=kb)

async def show_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id):
    query = update.callback_query
    await query.answer()
    perms = db.get("admins", {}).get(admin_id, {}).get("permissions", {})
    text = f"⚙️ تنظیم محدودیت برای ادمین: {admin_id}\n━━━━━━━━━━━━━━━\n"
    text += f"بن کردن: {'✅' if perms.get('ban', False) else '❌'}\n"
    text += f"پیام همگانی: {'✅' if perms.get('broadcast', False) else '❌'}\n"
    text += f"تنظیم محدودیت: {'✅' if perms.get('set_permissions', False) else '❌'}\n"
    text += f"مشاهده لیست ادمین: {'✅' if perms.get('view_admins', False) else '❌'}\n"
    text += f"افزودن ادمین: {'✅' if perms.get('add_admin', False) else '❌'}\n"
    text += f"حذف ادمین: {'✅' if perms.get('remove_admin', False) else '❌'}"
    await query.message.edit_text(text, reply_markup=get_permissions_keyboard(admin_id))

# --- توابع بن ---
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ فقط ادمین‌ها میتوانند از این دستور استفاده کنند.")
        return
    if not has_permission(update.effective_user.id, "ban") and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ شما دسترسی بن کردن را ندارید!")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ دستور صحیح:\n/ban (ایدی) (روز) (دلیل)\nمثال: /ban 123456789 7 اسپم")
        return
    target_id = args[0]
    days = int(args[1])
    reason = " ".join(args[2:])
    if target_id == str(OWNER_ID):
        await update.message.reply_text("❌ شما نمی‌توانید صاحب ربات را بن کنید!")
        return
    if is_admin(target_id):
        await update.message.reply_text("❌ نمی‌توانید یک ادمین دیگر را بن کنید!")
        return
    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    db["banned"][target_id] = {"until": until, "reason": reason, "banned_by": str(update.effective_user.id)}
    save_db(db)
    await update.message.reply_text(f"✅ کاربر {target_id} به مدت {days} روز بن شد.\nدلیل: {reason}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ فقط ادمین‌ها میتوانند از این دستور استفاده کنند.")
        return
    if not has_permission(update.effective_user.id, "ban") and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ شما دسترسی آنبن کردن را ندارید!")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ دستور صحیح:\n/unban (ایدی)\nمثال: /unban 123456789")
        return
    target_id = args[0]
    if target_id in db["banned"]:
        del db["banned"][target_id]
        save_db(db)
        await update.message.reply_text(f"✅ کاربر {target_id} آنبن شد.")
    else:
        await update.message.reply_text("❌ این کاربر در لیست بن نیست.")

async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.answer("❌ فقط ادمین‌ها میتوانند این بخش را ببینند!", show_alert=True)
        return
    await query.message.edit_text("🚫 لیست کاربران بن شده:", reply_markup=get_banned_list_keyboard())

# --- پنل اصلی ادمین ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.callback_query:
            await update.callback_query.answer("❌ فقط ادمین‌ها میتوانند از پنل استفاده کنند!", show_alert=True)
        else:
            await update.message.reply_text("❌ فقط ادمین‌ها میتوانند از پنل استفاده کنند!")
        return
    kb = [
        [InlineKeyboardButton("📊 آمار", callback_data="stats", style="success"), InlineKeyboardButton("👥 مدیریت کاربران", callback_data="user_list", style="primary")],
        [InlineKeyboardButton("🚫 لیست بن‌شده‌ها", callback_data="banned_list", style="danger"), InlineKeyboardButton("📢 پیام همگانی", callback_data="broadcast_menu", style="success")],
        [InlineKeyboardButton("👑 مدیریت ادمین‌ها", callback_data="admin_management", style="danger"), InlineKeyboardButton("🔒 جوین اجباری", callback_data="force_join_menu", style="danger")],
        [InlineKeyboardButton("📘 راهنمای ادمین", callback_data="admin_help", style="success"), InlineKeyboardButton("❌ بستن", callback_data="close_panel", style="primary")]
    ]
    if user_id == OWNER_ID:
        kb.insert(3, [InlineKeyboardButton("📥 دریافت بکاپ", callback_data="get_backup", style="primary"), InlineKeyboardButton("📤 آپلود بکاپ", callback_data="upload_backup", style="primary")])
    if edit and update.callback_query:
        await update.callback_query.message.edit_text("🛠 پنل مدیریت\n━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("🛠 پنل مدیریت\n━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(kb))

# --- دستور استارت با منوی آبی شیشه‌ای ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    
    if uid in db.get("banned", {}):
        until = db["banned"][uid]["until"]
        if datetime.now() < datetime.strptime(until, "%Y-%m-%d %H:%M"):
            await update.message.reply_text(f"❌ مسدود هستید!\nدلیل: {db['banned'][uid]['reason']}\nتا: {until}")
            return
    
    if not await check_force_join(update, context):
        return
    
    if uid not in db.get("users", {}):
        db["users"][uid] = {"name": user.full_name, "username": user.username or "None"}
        save_db(db)
    
    # منوی آبی شیشه‌ای با خطوط جداکننده
    if is_admin(user.id):
        text = "🔷 **پنل مدیریت ربات** 🔷\n━━━━━━━━━━━━━━━━━━━━━━\n👋 خوش آمدید ادمین عزیز!\n━━━━━━━━━━━━━━━━━━━━━━\nاز دکمه زیر برای ورود به پنل استفاده کنید:"
        buttons = [["🛠 پنل مدیریت"]]
    else:
        text = "🔷 **ربات دانلودر اینستاگرام** 🔷\n━━━━━━━━━━━━━━━━━━━━━━\n🤖 سلام! من آماده دانلود از اینستاگرام هستم.\n━━━━━━━━━━━━━━━━━━━━━━\n📥 لینک پست، ریل یا ویدیو را برای من بفرست.\n━━━━━━━━━━━━━━━━━━━━━━\n📖 برای راهنما دکمه زیر را بزن:"
        buttons = [["📖 راهنما"]]
    
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    
    # بررسی می‌کنیم که پیام از چه نوعی است
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

# --- راهنمای کاربر عادی ---
async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """📖 **راهنمای استفاده**
━━━━━━━━━━━━━━━━━━━━━━

➤ **مراحل دانلود:**
1️⃣ در اینستاگرام، روی سه نقطه (...) پست کلیک کنید
2️⃣ گزینه «کپی لینک/Copy Link» را انتخاب کنید
3️⃣ لینک را برای ربات ارسال کنید

➤ **فرمت‌های قابل پذیرش:**
• https://www.instagram.com/p/...
• https://www.instagram.com/reel/...
• https://www.instagram.com/tv/...

➤ **غیر قابل دانلود:**
• استوری‌ها (Stories)
• هایالیت‌ها (Highlights)
• پست‌های خصوصی
• پست‌های حذف شده

➤ **محدودیت:** هر 15 ثانیه فقط یک لینک

━━━━━━━━━━━━━━━━━━━━━━
🔷 **ربات دانلودر اینستاگرام** 🔷"""
    await update.message.reply_text(text, parse_mode="Markdown")

# --- آپلود بکاپ (فقط مالک) ---
async def upload_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ فقط مالک ربات میتواند بکاپ آپلود کند.", show_alert=True)
        return
    await query.answer()
    context.user_data["waiting_for_backup"] = True
    await query.message.reply_text("📤 فایل بکاپ JSON را ارسال کنید.")

async def process_backup_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.user_data.get("waiting_for_backup"):
        return
    if not update.message.document:
        await update.message.reply_text("❌ لطفاً فایل بکاپ JSON را ارسال کنید.")
        return

    context.user_data["waiting_for_backup"] = False
    temp_path = os.path.join(BACKUP_FOLDER, "uploaded_backup_temp.json")
    try:
        document = update.message.document
        if not document.file_name.lower().endswith(".json"):
            await update.message.reply_text("❌ فقط فایل JSON قابل قبول است.")
            return

        telegram_file = await document.get_file()
        await telegram_file.download_to_drive(temp_path)

        with open(temp_path, "r", encoding="utf-8") as f:
            new_db = json.load(f)

        required = {"users", "banned", "force_join", "admins", "broadcast", "cooldown", "stats"}
        if not isinstance(new_db, dict) or not required.issubset(new_db):
            await update.message.reply_text("❌ فایل بکاپ معتبر نیست یا ساختار آن صحیح نیست.")
            return

        save_db(new_db)
        global db
        db = new_db
        await update.message.reply_text("✅ بکاپ با موفقیت آپلود و بازیابی شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در بازیابی بکاپ: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --- هندلر پیام‌ها با محدودیت 15 ثانیه ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)

    if update.message.document and context.user_data.get("waiting_for_backup"):
        await process_backup_upload(update, context)
        return

    text = update.message.text
    
    if uid in db.get("banned", {}):
        return
    if not await check_force_join(update, context):
        return
    if uid not in db.get("users", {}):
        user = update.effective_user
        db["users"][uid] = {"name": user.full_name, "username": user.username or "None"}
        save_db(db)
    
    if text == "🛠 پنل مدیریت" and is_admin(user_id):
        await admin_panel(update, context)
        return
    elif text == "📖 راهنما":
        await help_menu(update, context)
        return
    
    if context.user_data.get("waiting_for_broadcast"):
        await process_broadcast(update, context)
        return
    if context.user_data.get("waiting_for_ban"):
        await process_ban(update, context)
        return
    if context.user_data.get("waiting_for_channel") == "add":
        channel = text.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        channels = db.get("force_join", {}).get("channels", [])
        if channel not in channels:
            channels.append(channel)
            db["force_join"]["channels"] = channels
            save_db(db)
            await update.message.reply_text(f"✅ کانال {channel} با موفقیت اضافه شد.")
        else:
            await update.message.reply_text("❌ این کانال قبلاً اضافه شده است.")
        context.user_data["waiting_for_channel"] = None
        return
    if context.user_data.get("waiting_for_admin") == "add":
        try:
            new_admin_id = text.strip()
            if new_admin_id == str(OWNER_ID):
                await update.message.reply_text("❌ این کاربر مالک ربات است!")
            elif new_admin_id in db.get("admins", {}):
                await update.message.reply_text("❌ این کاربر قبلاً ادمین است!")
            else:
                db["admins"][new_admin_id] = {
                    "added_by": str(user_id),
                    "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "permissions": {
                        "ban": True,
                        "broadcast": False,
                        "set_permissions": False,
                        "view_admins": True,
                        "add_admin": False,
                        "remove_admin": False
                    }
                }
                save_db(db)
                await update.message.reply_text(f"✅ کاربر {new_admin_id} به عنوان ادمین اضافه شد.")
        except:
            await update.message.reply_text("❌ خطا! آیدی عددی معتبر ارسال کنید.")
        context.user_data["waiting_for_admin"] = None
        return
    
    if not text or "instagram.com" not in text:
        return
    
    # محدودیت 15 ثانیه برای کاربران عادی
    if not is_admin(user_id):
        last_used = db["cooldown"].get(uid, 0)
        now = time.time()
        if now - last_used < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - (now - last_used))
            await update.message.reply_text(f"⏳ **صبر کن رفیق!**\nباید {remaining} ثانیه صبر کنی تا لینک بعدی رو بفرستی.\n━━━━━━━━━━━━━━━━━━━━━━\n💡 اگه ادمین باشی محدودیت نداری!", parse_mode="Markdown")
            return
        db["cooldown"][uid] = now
        save_db(db)
    
    save_db(db)
    
    msg = await update.message.reply_text("🔄 در حال پردازش...")
    
    items = []
    # --- API اصلی: RapidAPI ---
    if RAPID_KEY:
        try:
            async with http_session.get(
                RAPID_URL,
                params={"url": text},
                headers={"x-rapidapi-host": RAPID_HOST, "x-rapidapi-key": RAPID_KEY},
                timeout=aiohttp.ClientTimeout(total=40),
            ) as r:
                res_data = await r.json()
                for m in (res_data.get("media") or []):
                    if m.get("url"):
                        items.append({"url": m["url"], "is_video": m.get("type") != "image"})
        except Exception as e:
            print("RapidAPI error:", e)
            items = []

    # --- APIهای پشتیبان (اگر API اصلی جواب نداد) ---
    if not items:
        for api_info in API_LIST:
            try:
                async with http_session.get(api_info["url"], params={"apikey": api_info["key"], "type": "post", "url": text}, timeout=25) as r:
                    res_data = await r.json()
                    if res_data.get("ok") and res_data.get("result", {}).get("result"):
                        for it in res_data["result"]["result"]:
                            u = it.get("video_url") or it.get("display_url")
                            if u:
                                items.append({"url": u, "is_video": bool(it.get("is_video"))})
                        if items:
                            break
            except Exception as e:
                print("Backup API error:", e)
                items = []
                continue

    if items:
        insta_btn = InlineKeyboardMarkup([[InlineKeyboardButton("مشاهده در اینستاگرام 🔗", url=text, style="danger")]])
        for res in items:
            media_url = res.get("url")
            if not media_url:
                continue
            for i in range(1, 5):
                await msg.edit_text(f"📥 درحال دانلود {i*20}%")
                await asyncio.sleep(0.05)
            try:
                if res.get("is_video"):
                    await update.message.reply_video(media_url, caption="✅ @zeusdownloader_bot", reply_markup=insta_btn)
                else:
                    await update.message.reply_photo(media_url, caption="✅ @zeusdownloader_bot", reply_markup=insta_btn)
            except:
                await update.message.reply_document(media_url, caption="✅ @zeusdownloader_bot", reply_markup=insta_btn)
        await msg.edit_text("✅ فایل با موفقیت ارسال شد")
        await asyncio.sleep(1)
        await msg.delete()
        db["stats"]["total_downloads"] = db["stats"].get("total_downloads", 0) + 1
        save_db(db)
    else:
        await msg.edit_text("🔴 لینک احتمالا استوری، هایلایت، پست خصوصی یا پست حذف شده است\nربات قادر به دانلود لینک نیست ❌")

# --- دکمه‌های پنل ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "check_join":
        await force_join_callback(update, context)
        return
    if data == "force_join_menu":
        await force_join_menu(update, context)
        return
    if data == "add_channel":
        await add_channel_start(update, context)
        return
    if data == "remove_channel":
        await remove_channel_start(update, context)
        return
    if data == "list_channels":
        await list_channels(update, context)
        return
    if data.startswith("remove_this_"):
        channel = data.replace("remove_this_", "")
        channels = db.get("force_join", {}).get("channels", [])
        if channel in channels:
            channels.remove(channel)
            db["force_join"]["channels"] = channels
            save_db(db)
            await query.message.reply_text(f"✅ کانال {channel} حذف شد.")
        await force_join_menu(update, context)
        return
    if data == "stats":
        total_downloads = db.get("stats", {}).get("total_downloads", 0)
        await query.message.edit_text(f"📊 **آمار ربات**\n━━━━━━━━━━━━━━━━━━\n👥 کل کاربران: {len(db.get('users', {}))}\n🚫 تعداد بن‌شده: {len(db.get('banned', {}))}\n👑 تعداد ادمین‌ها: {len(db.get('admins', {}))}\n📥 کل دانلودها: {total_downloads}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin", style="primary")]]))
        return
    if data == "user_list" or data.startswith("page_"):
        p = int(data.split("_")[1]) if data.startswith("page_") else 1
        await query.message.edit_text("📋 **مدیریت کاربران**\n━━━━━━━━━━━━━━━━━━", parse_mode="Markdown", reply_markup=get_user_list_keyboard(p))
        return
    if data == "banned_list" or data.startswith("banned_page_"):
        if data.startswith("banned_page_"):
            p = int(data.split("_")[2])
            await query.message.edit_text("🚫 **لیست کاربران بن شده**\n━━━━━━━━━━━━━━━━━━", parse_mode="Markdown", reply_markup=get_banned_list_keyboard(p))
        else:
            await banned_list(update, context)
        return
    if data == "admin_management":
        await admin_management_menu(update, context)
        return
    if data == "add_admin_start":
        await add_admin_start(update, context)
        return
    if data == "remove_admin_start":
        await remove_admin_start(update, context)
        return
    if data == "list_admins":
        await list_admins(update, context)
        return
    if data == "set_permissions_start":
        await set_permissions_start(update, context)
        return
    if data.startswith("remove_admin_"):
        admin_id = data.replace("remove_admin_", "")
        if admin_id in db.get("admins", {}):
            del db["admins"][admin_id]
            save_db(db)
            await query.message.reply_text(f"✅ ادمین {admin_id} حذف شد.")
        await admin_management_menu(update, context)
        return
    if data.startswith("set_perm_"):
        admin_id = data.replace("set_perm_", "")
        await show_permissions(update, context, admin_id)
        return
    if data.startswith("perm_"):
        rest = data[len("perm_"):]
        perm_type, _, admin_id = rest.rpartition("_")
        if admin_id == str(OWNER_ID):
            await query.message.reply_text("❌ **نمی‌توانید محدودیت مالک ربات را تغییر دهید!**", parse_mode="Markdown")
            return
        if admin_id not in db.get("admins", {}):
            db["admins"][admin_id] = {}
        if "permissions" not in db["admins"][admin_id]:
            db["admins"][admin_id]["permissions"] = {}
        current = db["admins"][admin_id]["permissions"].get(perm_type, False)
        db["admins"][admin_id]["permissions"][perm_type] = not current
        save_db(db)
        await show_permissions(update, context, admin_id)
        return
    if data.startswith("askban_"):
        if not has_permission(update.effective_user.id, "ban") and update.effective_user.id != OWNER_ID:
            await query.message.reply_text("❌ **شما دسترسی «بن کردن» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
            return
        parts = data.split("_")
        context.user_data["ban_target"] = parts[1]
        context.user_data["ban_page"] = parts[2]
        context.user_data["waiting_for_ban"] = True
        await query.message.reply_text("فرمت بن:\n`روز,دلیل`\nمثال: `7,اسپم`")
        return
    if data.startswith("unban_"):
        if not has_permission(update.effective_user.id, "ban") and update.effective_user.id != OWNER_ID:
            await query.message.reply_text("❌ **شما دسترسی «آنبن کردن» را ندارید!**\n━━━━━━━━━━━━━━━━━━\nبا مالک ربات تماس بگیرید.", parse_mode="Markdown")
            return
        parts = data.split("_")
        uid = parts[1]
        p = int(parts[2])
        if uid in db.get("banned", {}):
            del db["banned"][uid]
            save_db(db)
        await query.message.edit_text("📋 **مدیریت کاربران**\n━━━━━━━━━━━━━━━━━━", parse_mode="Markdown", reply_markup=get_user_list_keyboard(p))
        return
    if data == "back_to_admin":
        await admin_panel(update, context, True)
        return
    if data == "back_to_admin_menu":
        await admin_management_menu(update, context)
        return
    if data == "close_panel":
        await query.message.delete()
        return
    if data == "broadcast_menu":
        await broadcast_menu(update, context)
        return
    if data == "admin_help":
        await admin_help(update, context)
        return
    if data == "upload_backup":
        await upload_backup_start(update, context)
        return
    if data == "get_backup":
        await get_backup_callback(update, context)
        return

async def process_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        d, r = update.message.text.split(",", 1)
        days = int(d.strip())
        reason = r.strip()
        target_id = context.user_data["ban_target"]
        
        if target_id == str(OWNER_ID):
            await update.message.reply_text("❌ شما نمی‌توانید صاحب ربات را بن کنید!")
            context.user_data["waiting_for_ban"] = False
            return
        if is_admin(target_id):
            await update.message.reply_text("❌ نمی‌توانید یک ادمین دیگر را بن کنید!")
            context.user_data["waiting_for_ban"] = False
            return
        
        until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        db["banned"][target_id] = {"until": until, "reason": reason, "banned_by": str(update.effective_user.id)}
        save_db(db)
        await update.message.reply_text(f"✅ کاربر {target_id} به مدت {days} روز بن شد.\nدلیل: {reason}")
    except:
        await update.message.reply_text("❌ خطا! فرمت صحیح:\n`روز,دلیل`\nمثال: `7,اسپم`")
    context.user_data["waiting_for_ban"] = False

# --- ایجاد و ارسال فایل بکاپ (فقط مالک) ---
async def create_and_send_backup(target):
    """target یک شیء با متد reply_document/reply_text است (update.message یا query.message)"""
    try:
        backup_name = f"manual_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join(BACKUP_FOLDER, backup_name)
        shutil.copy(DB_FILE, backup_path)
        with open(backup_path, "rb") as f:
            await target.reply_document(document=f, filename=backup_name, caption=f"✅ بکاپ دستی با نام {backup_name} ایجاد و ارسال شد.")
    except Exception as e:
        await target.reply_text(f"❌ خطا در ایجاد بکاپ: {e}")

async def manual_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ فقط مالک ربات میتواند بکاپ دستی بگیرد.")
        return
    await create_and_send_backup(update.message)

async def get_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ فقط مالک ربات میتواند بکاپ بگیرد.", show_alert=True)
        return
    await query.answer()
    await create_and_send_backup(query.message)

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور ساده پیام همگانی متنی (بدون عکس/ویدیو)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ فقط ادمین‌ها میتوانند از این دستور استفاده کنند.")
        return
    if not has_permission(update.effective_user.id, "broadcast") and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ شما دسترسی پیام همگانی را ندارید!")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ دستور صحیح:\n/broadcast متن پیام\nمثال: /broadcast سلام به همه!")
        return
    msg_text = " ".join(args)
    success = 0
    fail = 0
    progress = await update.message.reply_text("⏳ در حال ارسال پیام همگانی...")
    for uid in db.get("users", {}):
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg_text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    await progress.edit_text(f"✅ پیام همگانی ارسال شد!\n\n📨 موفق: {success}\n❌ ناموفق: {fail}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    webhook_path = os.environ.get("WEBHOOK_PATH", "webhook")
    public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    webhook_url = os.environ.get("WEBHOOK_URL") or (f"https://{public_domain}/{webhook_path}" if public_domain else "")

    if not webhook_url:
        raise RuntimeError("WEBHOOK_URL or RAILWAY_PUBLIC_DOMAIN must be set.")

    app = ApplicationBuilder().token(BOT_TOKEN).job_queue(None).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("broadcast", broadcast_message))
    app.add_handler(CommandHandler("backup", manual_backup))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_path,
        webhook_url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )
