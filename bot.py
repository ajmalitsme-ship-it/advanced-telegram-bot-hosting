import os
import sys
import asyncio
import logging
import subprocess
import zipfile
import re
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import aiofiles
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ParseMode
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

# ----------------- CONFIG -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8214091166:AAEi8sAp-K7gMzix7ralzsVFpn8hJPjJK5U")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8525952693").split(",")]
DB_PATH = "bot_hosting.db"

# ----------------- LOGGING -----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------- DATABASE WRAPPER -----------------
class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, name TEXT,
            joined TEXT, banned INTEGER DEFAULT 0, total_bots INTEGER DEFAULT 0,
            premium INTEGER DEFAULT 0
        )''')
        self.conn.execute('''CREATE TABLE IF NOT EXISTS bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT,
            bot_type TEXT, file_path TEXT, container_id TEXT, status TEXT
        )''')
        self.conn.commit()

    def add_user(self, user_id, username, name):
        joined = str(datetime.now())
        self.conn.execute('INSERT OR IGNORE INTO users(user_id, username, name, joined) VALUES (?,?,?,?)',
                          (user_id, username, name, joined))
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id=?', (user_id,))
        return cursor.fetchone()

    def add_bot(self, user_id, name, bot_type, file_path):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO bots(user_id,name,bot_type,file_path,status) VALUES (?,?,?,?,?)',
                       (user_id, name, bot_type, file_path, "stopped"))
        bot_id = cursor.lastrowid
        self.conn.commit()
        return bot_id

    def get_bot(self, bot_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM bots WHERE bot_id=?', (bot_id,))
        return cursor.fetchone()

    def get_user_bots(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM bots WHERE user_id=?', (user_id,))
        return cursor.fetchall()

db = Database(DB_PATH)

# ----------------- BOT MANAGER -----------------
class BotManager:
    def __init__(self):
        self.bots_dir = Path("hosted_bots")
        self.bots_dir.mkdir(exist_ok=True)

    async def create_bot_environment(self, user_id:int, bot_id:int, bot_type:str):
        bot_dir = self.bots_dir / f"user_{user_id}" / f"bot_{bot_id}"
        bot_dir.mkdir(parents=True, exist_ok=True)
        return bot_dir

    async def start_bot(self, bot_id:int):
        bot = db.get_bot(bot_id)
        if not bot: return {"success": False, "message":"Bot not found"}
        db.conn.execute('UPDATE bots SET status=? WHERE bot_id=?', ("running", bot_id))
        db.conn.commit()
        return {"success": True, "message": "Bot started"}

    async def stop_bot(self, bot_id:int):
        bot = db.get_bot(bot_id)
        if not bot: return {"success": False, "message":"Bot not found"}
        db.conn.execute('UPDATE bots SET status=? WHERE bot_id=?', ("stopped", bot_id))
        db.conn.commit()
        return {"success": True, "message": "Bot stopped"}

bot_manager = BotManager()

# ----------------- TELEGRAM COMMANDS -----------------
async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    keyboard = [
        [KeyboardButton("🚀 Upload Bot"), KeyboardButton("📊 My Bots")],
        [KeyboardButton("📱 Help"), KeyboardButton("💎 Premium")],
        [KeyboardButton("👤 Profile"), KeyboardButton("📩 Support")]
    ]
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\nUse /menu to see commands",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def menu(update:Update, context:ContextTypes.DEFAULT_TYPE):
    text = """
📋 COMMAND MENU
🚀 /upload
📊 /mybots
▶️ /start_bot <id>
⏸ /stop_bot <id>
🔄 /restart_bot <id>
📝 /logs <id>
📈 /stats <id>
🔧 /install <id> <module>
💎 /premium
👤 /profile
📩 /support
"""
    await update.message.reply_text(text)
# ----------------- SYNTAX VALIDATOR -----------------
import ast

class SyntaxValidator:
    @staticmethod
    def validate_python(code: str) -> Dict[str, any]:
        try:
            ast.parse(code)
            return {"valid": True, "errors": []}
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [{
                    "line": e.lineno,
                    "offset": e.offset,
                    "message": e.msg,
                    "text": e.text
                }]
            }

    @staticmethod
    def validate_javascript(code: str) -> Dict[str, any]:
        try:
            temp_file = "temp_validation.js"
            with open(temp_file, 'w') as f:
                f.write(code)
            result = subprocess.run(
                ['node', '--check', temp_file],
                capture_output=True, text=True, timeout=5
            )
            os.remove(temp_file)
            if result.returncode == 0:
                return {"valid": True, "errors": []}
            else:
                return {"valid": False, "errors": [{"message": result.stderr}]}
        except Exception as e:
            return {"valid": False, "errors": [{"message": str(e)}]}

    @staticmethod
    def extract_requirements(code: str, language: str) -> List[str]:
        requirements = []
        if language == "python":
            import_pattern = r'^(?:from\s+(\S+)|import\s+(\S+))'
            for line in code.split('\n'):
                line = line.strip()
                match = re.match(import_pattern, line)
                if match:
                    module = match.group(1) or match.group(2)
                    module = module.split('.')[0]
                    if module not in ['sys','os','time','datetime','re']:
                        requirements.append(module)
        elif language == "javascript":
            require_pattern = r'require\([\'"](.+?)[\'"]\)'
            import_pattern = r'import\s+.+\s+from\s+[\'"](.+?)[\'"]'
            for pattern in [require_pattern, import_pattern]:
                matches = re.findall(pattern, code)
                requirements.extend(matches)
        return list(set(requirements))

validator = SyntaxValidator()

# ----------------- UPLOAD HANDLER -----------------
UPLOAD_BOT = 1

async def upload_bot_start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Send your bot file (.py, .js, or .zip) now"
    )
    return UPLOAD_BOT

async def handle_bot_upload(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document = update.message.document
    if not document:
        await update.message.reply_text("❌ No file detected!")
        return ConversationHandler.END

    file_name = document.file_name
    if file_name.endswith('.py'):
        bot_type = "python"
    elif file_name.endswith('.js'):
        bot_type = "javascript"
    elif file_name.endswith('.zip'):
        bot_type = "archive"
    else:
        await update.message.reply_text("❌ Unsupported file type!")
        return ConversationHandler.END

    bot_id = db.add_bot(user_id, file_name, bot_type, "")
    bot_dir = await bot_manager.create_bot_environment(user_id, bot_id, bot_type)
    file_path = bot_dir / file_name

    await context.bot.get_file(document.file_id).download_to_drive(file_path)

    # Extract if zip
    if bot_type == "archive":
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(bot_dir)
        main_files = list(bot_dir.glob("*.py")) + list(bot_dir.glob("*.js"))
        if not main_files:
            await update.message.reply_text("❌ No .py or .js file found in archive!")
            return ConversationHandler.END
        main_file = main_files[0]
        bot_type = "python" if main_file.suffix == ".py" else "javascript"
    else:
        main_file = file_path

    # Read code
    async with aiofiles.open(main_file, 'r', encoding='utf-8') as f:
        code = await f.read()

    # Validate
    if bot_type == "python":
        validation = validator.validate_python(code)
    else:
        validation = validator.validate_javascript(code)

    requirements = validator.extract_requirements(code, bot_type)

    # Update bot path & type
    db.conn.execute('UPDATE bots SET file_path=?, bot_type=? WHERE bot_id=?',
                    (str(main_file), bot_type, bot_id))
    db.conn.commit()

    if validation["valid"]:
        response = f"✅ Bot uploaded! ID: {bot_id}\nType: {bot_type.upper()}\nModules: {', '.join(requirements) if requirements else 'None'}"
    else:
        errors = validation["errors"]
        error_details = "\n".join([f"Line {e.get('line','N/A')}: {e.get('message','Error')}" for e in errors])
        response = f"❌ Syntax errors detected:\n{error_details}"

    await update.message.reply_text(response)
    return ConversationHandler.END

# ----------------- MY BOTS -----------------
async def my_bots(update:Update, context:ContextTypes.DEFAULT_TYPE):
    bots = db.get_user_bots(update.effective_user.id)
    if not bots:
        await update.message.reply_text("📭 No bots found! Use /upload")
        return
    text = f"🤖 **YOUR BOTS** ({len(bots)})\n\n"
    for bot in bots:
        status = "🟢 Running" if bot[6]=="running" else "🔴 Stopped"
        text += f"Bot #{bot[0]}: {bot[2]} ({bot[3].upper()}) - {status}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ----------------- CONVERSATION HANDLER -----------------
def register_upload_handler(app):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('upload', upload_bot_start)],
        states={UPLOAD_BOT: [MessageHandler(filters.Document.ALL, handle_bot_upload)]},
        fallbacks=[]
    )
    app.add_handler(conv_handler)
# ----------------- BOT MANAGEMENT COMMANDS -----------------
async def start_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /start_bot <bot_id>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    if bot[6] == "running":
        await update.message.reply_text("⚠️ Bot already running!")
        return

    result = await bot_manager.start_bot(bot_id)
    if result["success"]:
        await update.message.reply_text(f"✅ Bot {bot_id} started! Use /logs {bot_id} to see logs.")
    else:
        await update.message.reply_text(f"❌ Failed to start bot: {result['message']}")

async def stop_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /stop_bot <bot_id>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    result = await bot_manager.stop_bot(bot_id)
    if result["success"]:
        await update.message.reply_text(f"✅ Bot {bot_id} stopped!")
    else:
        await update.message.reply_text(f"❌ Failed to stop bot: {result['message']}")

async def restart_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /restart_bot <bot_id>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    stop_result = await bot_manager.stop_bot(bot_id)
    if stop_result["success"]:
        await asyncio.sleep(1)
        start_result = await bot_manager.start_bot(bot_id)
        if start_result["success"]:
            await update.message.reply_text(f"🔄 Bot {bot_id} restarted successfully!")
        else:
            await update.message.reply_text(f"❌ Failed to restart: {start_result['message']}")
    else:
        await update.message.reply_text(f"❌ Failed to stop bot: {stop_result['message']}")

# ----------------- BOT LOGS -----------------
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /logs <bot_id>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    log_file = Path(bot[4]).parent / "bot.log"
    if log_file.exists():
        async with aiofiles.open(log_file, 'r', encoding='utf-8') as f:
            logs = await f.read()
        if len(logs) > 4000:
            logs = logs[-4000:]
        await update.message.reply_text(f"📝 **LOGS (Bot {bot_id})**\n\n```\n{logs}\n```",
                                        parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("📄 No logs available for this bot.")

# ----------------- BOT STATS -----------------
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /stats <bot_id>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    # Mock stats (replace with real container stats if using Docker)
    stats = {
        "cpu_percent": round(5 + bot_id % 10, 2),
        "memory_mb": round(50 + bot_id * 2, 2)
    }
    await update.message.reply_text(
        f"📊 **Bot {bot_id} Stats**\nCPU Usage: {stats['cpu_percent']}%\nMemory Usage: {stats['memory_mb']} MB",
        parse_mode=ParseMode.MARKDOWN
    )

# ----------------- INLINE BUTTONS -----------------
async def bot_controls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_id = int(context.callback_query.data.split("_")[1])
    action = update.callback_query.data.split("_")[0]

    if action == "start":
        result = await bot_manager.start_bot(bot_id)
        await update.callback_query.answer(result["message"])
    elif action == "stop":
        result = await bot_manager.stop_bot(bot_id)
        await update.callback_query.answer(result["message"])
    elif action == "restart":
        stop_result = await bot_manager.stop_bot(bot_id)
        await asyncio.sleep(1)
        start_result = await bot_manager.start_bot(bot_id)
        await update.callback_query.answer("Bot restarted successfully!")

async def my_bots_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bots = db.get_user_bots(update.effective_user.id)
    for bot in bots:
        status = "🟢 Running" if bot[6]=="running" else "🔴 Stopped"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Start", callback_data=f"start_{bot[0]}"),
                InlineKeyboardButton("⏸ Stop", callback_data=f"stop_{bot[0]}"),
                InlineKeyboardButton("🔄 Restart", callback_data=f"restart_{bot[0]}")
            ]
        ])
        await update.message.reply_text(f"Bot #{bot[0]}: {bot[2]} ({bot[3].upper()}) - {status}",
                                        reply_markup=keyboard)
        # ----------------- INSTALL MODULE -----------------
async def install_module_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
        module_name = context.args[1]
    except:
        await update.message.reply_text("❌ Usage: /install <bot_id> <module>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    msg = await update.message.reply_text(f"📦 Installing {module_name}...")
    # Mock installation (replace with Docker or subprocess logic)
    await asyncio.sleep(1)
    await msg.edit_text(f"✅ Module {module_name} installed!\nUse /restart_bot {bot_id} to restart.")

# ----------------- USER PROFILE -----------------
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    bots = db.get_user_bots(update.effective_user.id)
    running = sum(1 for b in bots if b[6]=="running")
    text = f"""
👤 **YOUR PROFILE**

🆔 ID: `{user[0]}`
👤 Name: {user[2]}
📅 Joined: {user[3][:10]}
💎 Premium: {"YES" if user[6] else "NO"}

📊 **Stats:**
🤖 Total Bots: {len(bots)}
🟢 Running: {running}
🔴 Stopped: {len(bots)-running}
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ----------------- DELETE BOT -----------------
async def delete_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /delete_bot <bot_id>")
        return

    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        await update.message.reply_text("❌ Bot not found!")
        return

    # Stop bot if running
    if bot[6]=="running":
        await bot_manager.stop_bot(bot_id)

    # Remove files
    import shutil
    bot_dir = Path(bot[4]).parent
    if bot_dir.exists():
        shutil.rmtree(bot_dir)

    # Delete from database
    db.conn.execute('DELETE FROM bots WHERE bot_id=?', (bot_id,))
    db.conn.commit()

    await update.message.reply_text(f"✅ Bot {bot_id} deleted!")

# ----------------- PREMIUM SYSTEM -----------------
async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user[6]:
        await update.message.reply_text("💎 You are already a premium user!")
    else:
        await update.message.reply_text(
            "💎 **PREMIUM FEATURES**\n\n"
            "✨ Unlimited bots\n⚡ Faster processing\n🛡 Priority support\n📊 Advanced analytics\n🚀 Auto-scaling\n\n"
            "Contact admin to upgrade!"
        )

# ----------------- HELP & SUPPORT -----------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📱 **HELP GUIDE**

**Getting Started:**
1. Upload bot: /upload
2. Install modules: /install
3. Start bot: /start_bot
4. Monitor logs: /logs /stats

**Commands:**
/mybots - Your bots
/profile - Your profile
/help - This message
/premium - Premium info

**Support:** @gadgetpremiumzone
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📩 Contact support at @gadgetpremiumzone")
# ----------------- ADMIN COMMANDS -----------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return

    users = db.get_all_users()
    bots = db.get_all_bots()
    running = sum(1 for b in bots if b[6]=="running")
    text = f"""
⚡ **ADMIN PANEL**

👥 Users: {len(users)}
🤖 Bots: {len(bots)}
🟢 Running: {running}
🔴 Stopped: {len(bots)-running}

**Commands:**
/users /allbots
/ban /unban
/broadcast
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    users = db.get_all_users()
    text = f"👥 **ALL USERS** ({len(users)})\n\n"
    for user in users[:50]:
        text += f"{user[2]} ({user[0]})\nBots: {user[5]}\nPremium: {'YES' if user[6] else 'NO'}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def list_all_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    bots = db.get_all_bots()
    text = f"🤖 **ALL BOTS** ({len(bots)})\n\n"
    for bot in bots[:50]:
        status = "🟢 Running" if bot[6]=="running" else "🔴 Stopped"
        text += f"{status} Bot #{bot[0]} - User {bot[1]} - {bot[2]} ({bot[3].upper()})\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        db.conn.execute('UPDATE users SET banned=1 WHERE user_id=?', (user_id,))
        db.conn.commit()
        await update.message.reply_text(f"✅ User {user_id} banned!")
    except:
        await update.message.reply_text("❌ Usage: /ban <user_id>")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        db.conn.execute('UPDATE users SET banned=0 WHERE user_id=?', (user_id,))
        db.conn.commit()
        await update.message.reply_text(f"✅ User {user_id} unbanned!")
    except:
        await update.message.reply_text("❌ Usage: /unban <user_id>")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    users = db.get_all_users()
    msg = await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    success = 0
    for user in users:
        try:
            await context.bot.send_message(user[0], f"📢 **BROADCAST**\n\n{message}", parse_mode=ParseMode.MARKDOWN)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await msg.edit_text(f"✅ Sent to {success} users!")

# ----------------- ERROR HANDLER -----------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ An unexpected error occurred!")

# ----------------- BOT STARTUP -----------------
def main():
    print("🚀 Starting Advanced Bot Hosting...")
    application = Application.builder().token(BOT_TOKEN).build()

    # Upload handler
    register_upload_handler(application)

    # Core commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("mybots", my_bots))
    application.add_handler(CommandHandler("start_bot", start_bot_command))
    application.add_handler(CommandHandler("stop_bot", stop_bot_command))
    application.add_handler(CommandHandler("restart_bot", restart_bot_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("install", install_module_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("delete_bot", delete_bot_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("premium", premium_command))
    application.add_handler(CommandHandler("support", support_command))

    # Admin handlers
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("allbots", list_all_bots))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # Inline callback buttons
    application.add_handler(CallbackQueryHandler(bot_controls))

    # Fallback text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Global error handler
    application.add_error_handler(error_handler)
# =================== PART 6: ADVANCED FEATURES / GITHUB / PREMIUM ===================
import requests
from pathlib import Path
import zipfile

# ----------------- PREMIUM CHECK DECORATOR -----------------
def premium_only(func):
    async def wrapper(update, context):
        user = cursor.execute("SELECT * FROM users WHERE user_id=?", (update.effective_user.id,)).fetchone()
        if not user or not user[6]:
            await update.message.reply_text("❌ This feature is only for Premium users!")
            return
        await func(update, context)
    return wrapper

# ----------------- GITHUB INTEGRATION -----------------
@premium_only
async def connect_github(update, context):
    text = """
🔗 **Connect Your GitHub**

1. Go to GitHub → Settings → Developer settings → Personal Access Tokens  
2. Generate a token with `repo` access  
3. Send the token here
"""
    await update.message.reply_text(text)
    return "GITHUB_TOKEN"  # Conversation state for token capture

async def save_github_token(update, context):
    token = update.message.text.strip()
    user_id = update.effective_user.id
    cursor.execute("UPDATE users SET github_token=? WHERE user_id=?", (token, user_id))
    conn.commit()
    await update.message.reply_text("✅ GitHub token saved successfully!")

# ----------------- DEPLOY FROM GITHUB -----------------
@premium_only
async def deploy_github_repo(update, context):
    user = cursor.execute("SELECT * FROM users WHERE user_id=?", (update.effective_user.id,)).fetchone()
    token = user[7]  # github_token
    if not token:
        await update.message.reply_text("❌ GitHub not connected. Use /connect_github first.")
        return

    try:
        repo_url = context.args[0]
        branch = context.args[1] if len(context.args) > 1 else "main"
        api_url = repo_url.replace("https://github.com/", "https://api.github.com/repos/") + f"/zipball/{branch}"
        headers = {"Authorization": f"token {token}"}

        r = requests.get(api_url, headers=headers)
        if r.status_code != 200:
            await update.message.reply_text(f"❌ Failed to fetch repo: {r.status_code}")
            return

        user_dir = Path("hosted_bots") / f"user_{user[0]}"
        user_dir.mkdir(exist_ok=True)
        zip_path = user_dir / "repo.zip"
        with open(zip_path, "wb") as f:
            f.write(r.content)

        # Extract repository
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(user_dir)
        zip_path.unlink()

        await update.message.reply_text("✅ Repo deployed successfully! Use /start_bot <bot_id> to start your bot.")
    except Exception as e:
        await update.message.reply_text(f"❌ Deployment failed: {str(e)}")

# ----------------- REAL-TIME STATS -----------------
@premium_only
async def realtime_stats(update, context):
    bots = cursor.execute("SELECT * FROM bots WHERE user_id=?", (update.effective_user.id,)).fetchall()
    text = "📊 **Real-Time Bot Stats**\n\n"
    for bot in bots:
        text += f"Bot #{bot[0]}: Status {bot[6]}\n"
    await update.message.reply_text(text)

# ----------------- ADMIN PREMIUM MANAGEMENT -----------------
async def grant_premium(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        cursor.execute("UPDATE users SET premium=1 WHERE user_id=?", (user_id,))
        conn.commit()
        await update.message.reply_text(f"💎 User {user_id} granted Premium!")
    except:
        await update.message.reply_text("❌ Usage: /grant_premium <user_id>")

async def revoke_premium(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        cursor.execute("UPDATE users SET premium=0 WHERE user_id=?", (user_id,))
        conn.commit()
        await update.message.reply_text(f"❌ Premium revoked for User {user_id}")
    except:
        await update.message.reply_text("❌ Usage: /revoke_premium <user_id>")

# ----------------- ADD HANDLERS -----------------
def add_advanced_handlers(application):
    # Premium features
    application.add_handler(CommandHandler("connect_github", connect_github))
    application.add_handler(CommandHandler("deploy_repo", deploy_github_repo))
    application.add_handler(CommandHandler("realtime_stats", realtime_stats))

    # Admin premium management
    application.add_handler(CommandHandler("grant_premium", grant_premium))
    application.add_handler(CommandHandler("revoke_premium", revoke_premium))

def main():
    print("🚀 Starting Bot Hosting Platform...")

    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers here...
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    # ...other handlers

    print("✅ Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)  # <-- NO extra indentation
