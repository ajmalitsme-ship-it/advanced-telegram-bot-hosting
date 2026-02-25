import os
import sys
import asyncio
import logging
import subprocess
import zipfile
import ast
import re
import psutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import docker
import aiofiles

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
from telegram.constants import ParseMode

from database import Database

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ⚙️ BOT CONFIGURATION - এখানে তোমার info দাও
BOT_TOKEN = os.getenv("BOT_TOKEN", "8214091166:AAEi8sAp-K7gMzix7ralzsVFpn8hJPjJK5U")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8525952693").split(",")]
CHANNEL_ID = "-1003559364122"
PRIVATE_CHANNEL = "https://t.me/+HSqmdVuHFr84MzRl"

# Database setup
DB_PATH = "bot_hosting.db"

# Docker client
docker_client = docker.from_env()

# States for conversation
UPLOAD_BOT, INSTALL_MODULE = range(2)

# Initialize database
db = Database(DB_PATH)

# ==================== SYNTAX VALIDATOR ====================
class SyntaxValidator:
    @staticmethod
    def validate_python(code: str) -> Dict[str, any]:
        """Validate Python syntax and return detailed errors"""
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
        """Validate JavaScript syntax using Node.js"""
        try:
            temp_file = "temp_validation.js"
            with open(temp_file, 'w') as f:
                f.write(code)
            
            result = subprocess.run(
                ['node', '--check', temp_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            os.remove(temp_file)
            
            if result.returncode == 0:
                return {"valid": True, "errors": []}
            else:
                return {"valid": False, "errors": [{"message": result.stderr}]}
        except subprocess.TimeoutExpired:
            return {"valid": False, "errors": [{"message": "Validation timeout"}]}
        except Exception as e:
            return {"valid": False, "errors": [{"message": str(e)}]}
    
    @staticmethod
    def extract_requirements(code: str, language: str) -> List[str]:
        """Extract required modules from code"""
        requirements = []
        
        if language == "python":
            import_pattern = r'^(?:from\s+(\S+)|import\s+(\S+))'
            for line in code.split('\n'):
                line = line.strip()
                match = re.match(import_pattern, line)
                if match:
                    module = match.group(1) or match.group(2)
                    module = module.split('.')[0]
                    if module not in ['sys', 'os', 'time', 'datetime', 're']:
                        requirements.append(module)
        
        elif language == "javascript":
            require_pattern = r'require\([\'"](.+?)[\'"]\)'
            import_pattern = r'import\s+.+\s+from\s+[\'"](.+?)[\'"]'
            
            for pattern in [require_pattern, import_pattern]:
                matches = re.findall(pattern, code)
                requirements.extend(matches)
        
        return list(set(requirements))

# ==================== BOT MANAGER ====================
class BotManager:
    def __init__(self):
        self.bots_dir = Path("hosted_bots")
        self.bots_dir.mkdir(exist_ok=True)
    
    async def create_bot_environment(self, user_id: int, bot_id: int, bot_type: str):
        """Create isolated environment for bot"""
        bot_dir = self.bots_dir / f"user_{user_id}" / f"bot_{bot_id}"
        bot_dir.mkdir(parents=True, exist_ok=True)
        return bot_dir
    
    async def start_bot(self, bot_id: int) -> Dict[str, any]:
        """Start bot in Docker container"""
        try:
            bot = db.get_bot(bot_id)
            if not bot:
                return {"success": False, "message": "Bot not found"}
            
            bot_type = bot[3]
            file_path = bot[4]
            
            if bot_type == "python":
                image = "python:3.11-slim"
                cmd = ["python", "-u", os.path.basename(file_path)]
            else:
                image = "node:18-alpine"
                cmd = ["node", os.path.basename(file_path)]
            
            container = docker_client.containers.run(
                image,
                command=cmd,
                volumes={
                    os.path.dirname(file_path): {'bind': '/app', 'mode': 'rw'}
                },
                working_dir='/app',
                detach=True,
                name=f"bot_{bot_id}",
                restart_policy={"Name": "unless-stopped"},
                mem_limit="512m",
                cpu_quota=50000
            )
            
            db.update_bot_status(bot_id, "running", container.id)
            db.add_log(bot_id, "info", "Bot started successfully")
            
            return {
                "success": True,
                "message": "Bot started successfully",
                "container_id": container.id
            }
        
        except Exception as e:
            db.add_log(bot_id, "error", f"Failed to start: {str(e)}")
            return {"success": False, "message": str(e)}
    
    async def stop_bot(self, bot_id: int) -> Dict[str, any]:
        """Stop bot container"""
        try:
            bot = db.get_bot(bot_id)
            if not bot or not bot[5]:
                return {"success": False, "message": "Bot not running"}
            
            container = docker_client.containers.get(bot[5])
            container.stop()
            container.remove()
            
            db.update_bot_status(bot_id, "stopped")
            db.add_log(bot_id, "info", "Bot stopped")
            
            return {"success": True, "message": "Bot stopped successfully"}
        
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def restart_bot(self, bot_id: int) -> Dict[str, any]:
        """Restart bot"""
        stop_result = await self.stop_bot(bot_id)
        if stop_result["success"]:
            await asyncio.sleep(2)
            return await self.start_bot(bot_id)
        return stop_result
    
    async def get_bot_logs(self, bot_id: int, lines: int = 50) -> str:
        """Get bot container logs"""
        try:
            bot = db.get_bot(bot_id)
            if not bot or not bot[5]:
                return "Bot not running"
            
            container = docker_client.containers.get(bot[5])
            logs = container.logs(tail=lines).decode('utf-8')
            return logs
        except Exception as e:
            return f"Error getting logs: {str(e)}"
    
    async def get_bot_stats(self, bot_id: int) -> Dict[str, any]:
        """Get bot resource usage statistics"""
        try:
            bot = db.get_bot(bot_id)
            if not bot or not bot[5]:
                return None
            
            container = docker_client.containers.get(bot[5])
            stats = container.stats(stream=False)
            
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            cpu_percent = (cpu_delta / system_delta) * 100.0 if system_delta > 0 else 0
            
            memory_usage = stats['memory_stats']['usage'] / (1024 * 1024)
            memory_limit = stats['memory_stats']['limit'] / (1024 * 1024)
            memory_percent = (memory_usage / memory_limit) * 100
            
            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_usage, 2),
                "memory_percent": round(memory_percent, 2)
            }
        except Exception as e:
            return None
    
    async def install_module(self, bot_id: int, module_name: str) -> Dict[str, any]:
        """Install module in bot environment"""
        try:
            bot = db.get_bot(bot_id)
            if not bot:
                return {"success": False, "message": "Bot not found"}
            
            bot_type = bot[3]
            bot_dir = os.path.dirname(bot[4])
            
            if bot_type == "python":
                result = subprocess.run(
                    ['pip', 'install', module_name, '--target', bot_dir],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            else:
                result = subprocess.run(
                    ['npm', 'install', module_name],
                    cwd=bot_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            
            if result.returncode == 0:
                db.add_module(bot_id, module_name, "latest")
                db.add_log(bot_id, "info", f"Module {module_name} installed")
                return {"success": True, "message": f"Module {module_name} installed successfully"}
            else:
                return {"success": False, "message": result.stderr}
        
        except Exception as e:
            return {"success": False, "message": str(e)}

bot_manager = BotManager()

# ==================== TELEGRAM BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
╔═══════════════════════╗
   🚀 **ADVANCED BOT HOSTING** 🚀
╚═══════════════════════╝

👋 Welcome **{user.first_name}**!

✨ **Most Advanced Features:**
━━━━━━━━━━━━━━━━━━━━━
🤖 Host Python & JavaScript bots
📦 Auto syntax validation
⚡ Real-time monitoring & logs
🔧 Manual module installation
🐳 Docker container isolation
📊 Resource usage tracking
💎 Premium admin features
🎨 Beautiful premium UI

━━━━━━━━━━━━━━━━━━━━━

**🎯 Quick Start:**
1️⃣ Upload your bot file (.py or .js)
2️⃣ Bot validates syntax automatically
3️⃣ Start hosting instantly!

**📱 Join Our Channels:**
🔹 Premium Zone: @gadgetpremiumzone
🔸 Mod APK: {PRIVATE_CHANNEL}

━━━━━━━━━━━━━━━━━━━━━

💫 **Use /menu to see all commands**
"""
    
    keyboard = [
        [KeyboardButton("🚀 Upload Bot"), KeyboardButton("📊 My Bots")],
        [KeyboardButton("📱 Help"), KeyboardButton("💎 Premium")],
        [KeyboardButton("👤 Profile"), KeyboardButton("📞 Support")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu_text = """
╔════════════════════╗
   📋 **COMMAND MENU**
╚════════════════════╝

**👤 User Commands:**
━━━━━━━━━━━━━━━━━
🚀 /upload - Upload new bot
📊 /mybots - View your bots
▶️ /start_bot - Start a bot
⏸ /stop_bot - Stop a bot
🔄 /restart_bot - Restart bot
📝 /logs - View bot logs
📈 /stats - Bot statistics
🔧 /install - Install module
💎 /premium - Premium features
👤 /profile - Your profile

**🛠 Admin Commands:**
━━━━━━━━━━━━━━━━━
📊 /admin - Admin panel
👥 /users - All users
🤖 /allbots - All bots
🚫 /ban - Ban user
✅ /unban - Unban user
📢 /broadcast - Send message

**💡 Need Help?**
Use /help for detailed guide
"""
    await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN)

async def upload_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
╔════════════════════════╗
   📤 **UPLOAD YOUR BOT**
╚════════════════════════╝

**📋 Upload Instructions:**
━━━━━━━━━━━━━━━━━━━━━

✅ **Supported Files:**
• Python (.py) scripts
• JavaScript (.js) scripts
• ZIP archives with bot code

🔍 **Auto Validation:**
• Syntax checking
• Error detection
• Module requirements analysis

📦 **What Happens:**
1️⃣ Upload your file
2️⃣ Auto syntax validation
3️⃣ Error report (if any)
4️⃣ Ready to host!

━━━━━━━━━━━━━━━━━━━━━

**📎 Send your bot file now:**
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return UPLOAD_BOT

async def handle_bot_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if user and user[4]:
        await update.message.reply_text("❌ You are banned from using this service.")
        return ConversationHandler.END
    
    processing_msg = await update.message.reply_text("⏳ Processing your bot...")
    
    try:
        document = update.message.document
        file = await context.bot.get_file(document.file_id)
        file_name = document.file_name
        
        if file_name.endswith('.py'):
            bot_type = "python"
        elif file_name.endswith('.js'):
            bot_type = "javascript"
        elif file_name.endswith('.zip'):
            bot_type = "archive"
        else:
            await processing_msg.edit_text("❌ Unsupported file type!")
            return ConversationHandler.END
        
        bot_id = db.add_bot(user_id, file_name, bot_type, "")
        bot_dir = await bot_manager.create_bot_environment(user_id, bot_id, bot_type)
        
        if bot_type == "archive":
            file_path = bot_dir / file_name
            await file.download_to_drive(file_path)
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(bot_dir)
            main_files = list(bot_dir.glob("*.py")) + list(bot_dir.glob("*.js"))
            if not main_files:
                await processing_msg.edit_text("❌ No .py or .js file found!")
                db.delete_bot(bot_id)
                return ConversationHandler.END
            main_file = main_files[0]
            bot_type = "python" if main_file.suffix == ".py" else "javascript"
        else:
            main_file = bot_dir / file_name
            await file.download_to_drive(main_file)
        
        async with aiofiles.open(main_file, 'r', encoding='utf-8') as f:
            code = await f.read()
        
        validator = SyntaxValidator()
        if bot_type == "python":
            validation = validator.validate_python(code)
        else:
            validation = validator.validate_javascript(code)
        
        requirements = validator.extract_requirements(code, bot_type)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE bots SET file_path = ?, bot_type = ? WHERE bot_id = ?',
                      (str(main_file), bot_type, bot_id))
        conn.commit()
        conn.close()
        
        if validation["valid"]:
            response = f"""
╔════════════════════════╗
   ✅ **BOT UPLOADED**
╚════════════════════════╝

🆔 **Bot ID:** `{bot_id}`
📝 **Name:** {file_name}
💻 **Type:** {bot_type.upper()}
✅ **Status:** Ready

🔍 **Syntax:** ✅ PASSED

**📦 Modules:**
{chr(10).join([f"• {req}" for req in requirements[:10]]) if requirements else "• None detected"}

━━━━━━━━━━━━━━━━━━━━━

**🚀 Next:**
/start_bot {bot_id}
/logs {bot_id}
"""
            db.add_log(bot_id, "success", "Bot uploaded successfully")
        else:
            errors = validation["errors"]
            error_details = "\n".join([
                f"❌ Line {e.get('line', 'N/A')}: {e.get('message', 'Error')}"
                for e in errors[:5]
            ])
            
            response = f"""
╔════════════════════════╗
   ⚠️ **SYNTAX ERRORS**
╚════════════════════════╝

🆔 **Bot ID:** `{bot_id}`
📝 **Name:** {file_name}

🔍 **Syntax:** ❌ FAILED

**⚠️ Errors:**
{error_details}

━━━━━━━━━━━━━━━━━━━━━

💡 **Fix and re-upload**
"""
            db.add_log(bot_id, "error", f"Syntax errors: {len(errors)}")
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
    
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error: {str(e)}")
    
    return ConversationHandler.END

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bots = db.get_user_bots(user_id)
    
    if not bots:
        await update.message.reply_text("📭 No bots found! Use /upload")
        return
    
    text = f"🤖 **YOUR BOTS** ({len(bots)})\n\n"
    
    for bot in bots:
        status_emoji = "🟢" if bot[6] == "running" else "🔴"
        text += f"""{status_emoji} **Bot #{bot[0]}**
📝 {bot[2]}
💻 {bot[3].upper()}
📊 {bot[6].upper()}

/start_bot {bot[0]}
/logs {bot[0]}
━━━━━━━━━━━━━━━━━

"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

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
        await update.message.reply_text("⚠️ Already running!")
        return
    
    msg = await update.message.reply_text("🚀 Starting...")
    result = await bot_manager.start_bot(bot_id)
    
    if result["success"]:
        await msg.edit_text(f"✅ Bot {bot_id} started!\n\n/logs {bot_id}")
    else:
        await msg.edit_text(f"❌ Failed: {result['message']}")

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
    
    msg = await update.message.reply_text("⏸ Stopping...")
    result = await bot_manager.stop_bot(bot_id)
    
    await msg.edit_text("✅ Bot stopped!" if result["success"] else f"❌ {result['message']}")

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
    
    msg = await update.message.reply_text("🔄 Restarting...")
    result = await bot_manager.restart_bot(bot_id)
    
    await msg.edit_text("✅ Bot restarted!" if result["success"] else f"❌ {result['message']}")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /logs <bot_id>")
        return
    
    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Bot not found!")
            return
    
    logs = await bot_manager.get_bot_logs(bot_id, 50)
    
    if len(logs) > 4000:
        logs = logs[-4000:]
    
    await update.message.reply_text(f"📝 **LOGS (Bot {bot_id})**\n\n```\n{logs}\n```", parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /stats <bot_id>")
        return
    
    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Bot not found!")
            return
    
    if bot[6] != "running":
        await update.message.reply_text("⚠️ Bot not running!")
        return
    
    stats = await bot_manager.get_bot_stats(bot_id)
    modules = db.get_bot_modules(bot_id)
    
    if stats:
        text = f"""
📊 **STATISTICS**

🆔 Bot: {bot_id}
⚡ CPU: {stats['cpu_percent']}%
💾 Memory: {stats['memory_mb']:.2f} MB
📦 Modules: {len(modules)}
"""
    else:
        text = "❌ Unable to fetch stats"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

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
    result = await bot_manager.install_module(bot_id, module_name)
    
    if result["success"]:
        await msg.edit_text(f"✅ Module installed!\n\n/restart_bot {bot_id}")
    else:
        await msg.edit_text(f"❌ Failed: {result['message']}")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    bots = db.get_user_bots(update.effective_user.id)
    running = sum(1 for b in bots if b[6] == "running")
    
    text = f"""
👤 **YOUR PROFILE**

🆔 ID: `{user[0]}`
👤 Name: {user[2]}
📅 Joined: {user[3][:10]}
💎 Premium: {'YES' if user[6] else 'NO'}

📊 **Stats:**
🤖 Total Bots: {user[5]}
🟢 Running: {running}
🔴 Stopped: {user[5] - running}
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def delete_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /delete_bot <bot_id>")
        return
    
    bot = db.get_bot(bot_id)
    if not bot or bot[1] != update.effective_user.id:
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Bot not found!")
            return
    
    if bot[6] == "running":
        await bot_manager.stop_bot(bot_id)
    
    import shutil
    bot_dir = Path(bot[4]).parent
    if bot_dir.exists():
        shutil.rmtree(bot_dir)
    
    db.delete_bot(bot_id)
    await update.message.reply_text(f"✅ Bot {bot_id} deleted!")

# Admin commands
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    
    users = db.get_all_users()
    bots = db.get_all_bots()
    running = sum(1 for b in bots if b[6] == "running")
    
    text = f"""
⚡ **ADMIN PANEL**

👥 Users: {len(users)}
🤖 Bots: {len(bots)}
🟢 Running: {running}
🔴 Stopped: {len(bots) - running}

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
    
    for user in users[:20]:
        text += f"{user[2]} ({user[0]})\nBots: {user[5]}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def list_all_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    bots = db.get_all_bots()
    text = f"🤖 **ALL BOTS** ({len(bots)})\n\n"
    
    for bot in bots[:15]:
        emoji = "🟢" if bot[6] == "running" else "🔴"
        text += f"{emoji} Bot #{bot[0]} - User {bot[1]}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        db.ban_user(user_id)
        await update.message.reply_text(f"✅ User {user_id} banned!")
    except:
        await update.message.reply_text("❌ Usage: /ban <user_id>")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(context.args[0])
        db.unban_user(user_id)
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📱 **HELP GUIDE**

**Getting Started:**
1. Upload bot file: /upload
2. Install modules: /install
3. Start bot: /start_bot
4. Monitor: /logs /stats

**Commands:**
/mybots - Your bots
/profile - Your profile
/help - This message

**Support:**
@gadgetpremiumzone
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
💎 **PREMIUM FEATURES**

✨ Unlimited bots
⚡ Faster processing
🛡 Priority support
📊 Advanced analytics
🚀 Auto-scaling

**Contact admin to upgrade!**
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🚀 Upload Bot":
        await upload_bot_start(update, context)
    elif text == "📊 My Bots":
        await my_bots(update, context)
    elif text == "📱 Help":
        await help_command(update, context)
    elif text == "💎 Premium":
        await premium_command(update, context)
    elif text == "👤 Profile":
        await profile_command(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ An error occurred!")

def main():
    print("🚀 Starting Bot Hosting Platform...")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    upload_handler = ConversationHandler(
        entry_points=[
            CommandHandler('upload', upload_bot_start),
            MessageHandler(filters.Regex('^🚀 Upload Bot$'), upload_bot_start)
        ],
        states={
            UPLOAD_BOT: [MessageHandler(filters.Document.ALL, handle_bot_upload)]
        },
        fallbacks=[]
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(upload_handler)
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
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("allbots", list_all_bots))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    print("✅ Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
