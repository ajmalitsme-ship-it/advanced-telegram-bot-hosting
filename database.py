import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                join_date TEXT,
                is_banned INTEGER DEFAULT 0,
                total_bots INTEGER DEFAULT 0,
                is_premium INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bots (
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
                uptime INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS modules (
                module_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER,
                module_name TEXT,
                version TEXT,
                install_date TEXT,
                FOREIGN KEY(bot_id) REFERENCES bots(bot_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER,
                log_type TEXT,
                log_message TEXT,
                timestamp TEXT,
                FOREIGN KEY(bot_id) REFERENCES bots(bot_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id: int, username: str, first_name: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, join_date)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_user(self, user_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    
    def add_bot(self, user_id: int, bot_name: str, bot_type: str, file_path: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bots (user_id, bot_name, bot_type, file_path, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, bot_name, bot_type, file_path, 'stopped', datetime.now().isoformat()))
        bot_id = cursor.lastrowid
        cursor.execute('UPDATE users SET total_bots = total_bots + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return bot_id
    
    def get_user_bots(self, user_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bots WHERE user_id = ?', (user_id,))
        bots = cursor.fetchall()
        conn.close()
        return bots
    
    def update_bot_status(self, bot_id: int, status: str, container_id: str = None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if container_id:
            cursor.execute('''
                UPDATE bots SET status = ?, container_id = ?, last_active = ?
                WHERE bot_id = ?
            ''', (status, container_id, datetime.now().isoformat(), bot_id))
        else:
            cursor.execute('UPDATE bots SET status = ? WHERE bot_id = ?', (status, bot_id))
        conn.commit()
        conn.close()
    
    def get_bot(self, bot_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bots WHERE bot_id = ?', (bot_id,))
        bot = cursor.fetchone()
        conn.close()
        return bot
    
    def add_log(self, bot_id: int, log_type: str, log_message: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (bot_id, log_type, log_message, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (bot_id, log_type, log_message, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def add_module(self, bot_id: int, module_name: str, version: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO modules (bot_id, module_name, version, install_date)
            VALUES (?, ?, ?, ?)
        ''', (bot_id, module_name, version, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_bot_modules(self, bot_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modules WHERE bot_id = ?', (bot_id,))
        modules = cursor.fetchall()
        conn.close()
        return modules
    
    def get_all_bots(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bots')
        bots = cursor.fetchall()
        conn.close()
        return bots
    
    def get_all_users(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users')
        users = cursor.fetchall()
        conn.close()
        return users
    
    def ban_user(self, user_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def unban_user(self, user_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def delete_bot(self, bot_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM bots WHERE bot_id = ?', (bot_id,))
        result = cursor.fetchone()
        if result:
            user_id = result[0]
            cursor.execute('DELETE FROM bots WHERE bot_id = ?', (bot_id,))
            cursor.execute('DELETE FROM modules WHERE bot_id = ?', (bot_id,))
            cursor.execute('DELETE FROM logs WHERE bot_id = ?', (bot_id,))
            cursor.execute('UPDATE users SET total_bots = total_bots - 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
