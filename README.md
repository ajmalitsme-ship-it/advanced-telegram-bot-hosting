# 🚀 Advanced Telegram Bot Hosting Platform

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Required-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Most Advanced Telegram Bot Hosting Platform** with Docker containerization, real-time syntax validation, resource monitoring, and premium admin features!

## ✨ Features

### 🎯 Core Features
- 🤖 **Multi-Language Support**: Host Python (.py) and JavaScript (.js) bots
- 📦 **Smart Upload**: Upload single files or ZIP archives
- 🔍 **Syntax Validation**: Automatic error detection before hosting
- 🐳 **Docker Isolation**: Each bot runs in isolated container
- ⚡ **Real-time Monitoring**: CPU, memory, and resource tracking
- 📊 **Live Logs**: View bot logs in real-time
- 🔧 **Manual Module Installation**: Install packages on-demand

### 💎 Advanced Features
- 📈 **Resource Management**: CPU and memory limits per bot
- 🛡️ **Auto-restart**: Bots restart automatically on failure
- 📝 **Log Management**: Persistent log storage and viewing
- 👥 **User Management**: Ban/unban users, track statistics
- 📢 **Broadcast System**: Send messages to all users
- 🎨 **Beautiful UI**: Premium Telegram keyboard interface
- ⚙️ **Admin Panel**: Powerful control panel for administrators

### 🔐 Security Features
- 🐳 Container isolation for each bot
- 🚫 User ban system
- 📊 Resource usage limits
- 🔒 Admin-only commands
- 📝 Complete audit logging

## 🛠️ Technology Stack

- **Python 3.11+**
- **python-telegram-bot 20.7**
- **Docker & Docker SDK**
- **SQLite3** (Database)
- **aiofiles** (Async file operations)
- **psutil** (Resource monitoring)

## 📋 Prerequisites

1. **Docker** installed on your system
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```

2. **Python 3.11+** (for local development)

3. **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)

4. **Your Telegram User ID** (get from [@userinfobot](https://t.me/userinfobot))

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/kboy90194-cell/advanced-telegram-bot-hosting.git
cd advanced-telegram-bot-hosting
```

### 2. Configuration

Create `.env` file:
```bash
cp .env.example .env
nano .env
```

Add your credentials:
```env
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=your_telegram_user_id
```

### 3. Run with Docker Compose

```bash
docker-compose up -d
```

### 4. Check Logs
```bash
docker-compose logs -f
```

## 📖 Usage Guide

### For Users

1. **Start Bot**: `/start`
2. **Upload Bot**: Click "🚀 Upload Bot" or use `/upload`
3. **Send File**: Upload your `.py`, `.js`, or `.zip` file
4. **View Bots**: `/mybots`
5. **Start Hosting**: `/start_bot <bot_id>`
6. **Monitor**: `/logs <bot_id>` or `/stats <bot_id>`
7. **Install Module**: `/install <bot_id> <module_name>`

### For Admins

1. **Admin Panel**: `/admin`
2. **View All Users**: `/users`
3. **View All Bots**: `/allbots`
4. **Ban User**: `/ban <user_id>`
5. **Unban User**: `/unban <user_id>`
6. **Broadcast**: `/broadcast <message>`

## 📱 Commands Reference

### User Commands
| Command | Description |
|---------|-------------|
| `/start` | Start the bot and see welcome message |
| `/upload` | Upload a new bot file |
| `/mybots` | View all your hosted bots |
| `/start_bot <id>` | Start a specific bot |
| `/stop_bot <id>` | Stop a running bot |
| `/restart_bot <id>` | Restart a bot |
| `/logs <id>` | View bot logs |
| `/stats <id>` | View bot statistics |
| `/install <id> <module>` | Install a module |
| `/delete_bot <id>` | Delete a bot |
| `/profile` | View your profile |
| `/help` | Show help message |
| `/premium` | View premium features |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/admin` | Open admin panel |
| `/users` | List all users |
| `/allbots` | List all bots |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/broadcast <msg>` | Broadcast message |

## 🎨 Bot Features

### Syntax Validation
```python
# Python code validation
✅ Checks syntax errors before hosting
✅ Shows line numbers and error details
✅ Detects missing imports
```

### Resource Monitoring
```
📊 CPU Usage: Real-time tracking
💾 Memory Usage: MB and percentage
🔥 Container Stats: Live updates
```

### Module Installation
```bash
# Python modules
/install 1 aiogram
/install 1 requests

# JavaScript packages
/install 2 express
/install 2 axios
```

## 🏗️ Project Structure

```
advanced-telegram-bot-hosting/
├── bot.py                 # Main bot application
├── database.py            # Database management
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker image configuration
├── docker-compose.yml    # Docker compose setup
├── .env.example          # Environment variables template
├── .gitignore           # Git ignore file
├── README.md            # This file
└── hosted_bots/         # User bots storage (created automatically)
```

## 🔧 Development

### Local Setup (Without Docker)

1. **Create Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate  # Windows
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Bot**
   ```bash
   python bot.py
   ```

### Database Schema

```sql
-- Users table
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    join_date TEXT,
    is_banned INTEGER DEFAULT 0,
    total_bots INTEGER DEFAULT 0,
    is_premium INTEGER DEFAULT 0
);

-- Bots table
CREATE TABLE bots (
    bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bot_name TEXT,
    bot_type TEXT,
    file_path TEXT,
    container_id TEXT,
    status TEXT,
    created_at TEXT,
    last_active TEXT,
    cpu_usage REAL DEFAULT 0,
    memory_usage REAL DEFAULT 0,
    uptime INTEGER DEFAULT 0
);

-- Modules table
CREATE TABLE modules (
    module_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    module_name TEXT,
    version TEXT,
    install_date TEXT
);

-- Logs table
CREATE TABLE logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    log_type TEXT,
    log_message TEXT,
    timestamp TEXT
);
```

## 🐛 Troubleshooting

### Docker Permission Issues
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Bot Not Starting
- Check if Docker is running: `docker ps`
- Check bot token in `.env`
- View logs: `docker-compose logs`

### Module Installation Fails
- Ensure bot is stopped before installing modules
- Check module name spelling
- Some modules may require system dependencies

## 📊 Performance

- **Container Limits**: 512MB RAM, 50% CPU per bot
- **Restart Policy**: Automatic restart on failure
- **Database**: SQLite3 with optimized queries
- **Async Operations**: Non-blocking file operations

## 🔒 Security Considerations

1. **Container Isolation**: Each bot runs in isolated Docker container
2. **Resource Limits**: CPU and memory limits prevent abuse
3. **User Management**: Ban system for malicious users
4. **Admin Authentication**: Commands restricted to admin IDs
5. **Syntax Validation**: Prevents execution of invalid code

## 🌟 Future Enhancements

- [ ] Web dashboard
- [ ] Custom domain support
- [ ] Auto-scaling based on load
- [ ] Kubernetes deployment
- [ ] Payment integration
- [ ] Advanced analytics
- [ ] Multi-admin support
- [ ] Bot templates library

## 💎 Premium Features (Coming Soon)

- ✨ Unlimited bots
- ⚡ Higher resource limits
- 🛡️ Priority support
- 📊 Advanced analytics
- 🚀 Auto-scaling
- 🔧 Custom configurations

## 📞 Support

- **Telegram Channel**: [@gadgetpremiumzone](https://t.me/gadgetpremiumzone)
- **Issues**: [GitHub Issues](https://github.com/kboy90194-cell/advanced-telegram-bot-hosting/issues)
- **Discussions**: [GitHub Discussions](https://github.com/kboy90194-cell/advanced-telegram-bot-hosting/discussions)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
- [Docker](https://www.docker.com/) - Containerization platform
- All contributors and users!

## 📈 Stats

![GitHub stars](https://img.shields.io/github/stars/kboy90194-cell/advanced-telegram-bot-hosting)
![GitHub forks](https://img.shields.io/github/forks/kboy90194-cell/advanced-telegram-bot-hosting)
![GitHub issues](https://img.shields.io/github/issues/kboy90194-cell/advanced-telegram-bot-hosting)

---

**Made with ❤️ by [kboy90194-cell](https://github.com/kboy90194-cell)**

**⭐ Star this repo if you find it useful!**
