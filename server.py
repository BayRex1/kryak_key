# server.py
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
import threading
import time
import os
import random
import string

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с Android

# ========== БАЗА ДАННЫХ ==========

def get_db():
    # Создаем папку для базы данных если её нет
    db_path = '/tmp/key_shop.db' if os.environ.get('RENDER') else 'key_shop.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            coins INTEGER DEFAULT 0,
            total_paid INTEGER DEFAULT 0,
            registered_date TEXT,
            last_activity TEXT
        )
    ''')
    
    # Таблица платежей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            amount_rub INTEGER,
            amount_coins INTEGER,
            payment_code TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_date TEXT,
            confirmed_date TEXT,
            admin_id INTEGER
        )
    ''')
    
    # Таблица ключей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            key_value TEXT UNIQUE,
            purchase_date TEXT,
            price INTEGER
        )
    ''')
    
    # Таблица цен на ключи
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS key_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keys_sold INTEGER DEFAULT 0,
            current_price INTEGER DEFAULT 100
        )
    ''')
    
    # Инициализируем цены если таблица пустая
    cursor.execute("SELECT * FROM key_prices")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO key_prices (keys_sold, current_price) VALUES (0, 100)")
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# Инициализируем БД при запуске
init_db()

# ========== API ДЛЯ ANDROID ==========

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'online',
        'message': 'Key Shop API Server',
        'endpoints': [
            '/api/user/<user_id>',
            '/api/user/<user_id>/profile',
            '/api/user/<user_id>/keys',
            '/api/key/price',
            '/api/payment/create',
            '/api/payment/check/<code>/<user_id>',
            '/api/buy/key',
            '/api/stats'
        ]
    })

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Получить данные пользователя"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем есть ли пользователь
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        # Создаём нового пользователя
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, coins, registered_date, last_activity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 'android_user', 'Android User', 0, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    
    # Получаем цену ключа
    cursor.execute("SELECT current_price FROM key_prices WHERE id=1")
    key_price = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'coins': user['coins'],
        'keyPrice': key_price,
        'username': user['username']
    })

@app.route('/api/user/<user_id>/profile', methods=['GET'])
def get_user_profile(user_id):
    """Получить полный профиль пользователя"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, username, first_name, coins, total_paid, registered_date
        FROM users WHERE user_id = ?
    """, (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Считаем количество ключей
    cursor.execute("SELECT COUNT(*) FROM keys WHERE user_id = ?", (user_id,))
    keys_count = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'user_id': user['user_id'],
        'username': user['username'],
        'first_name': user['first_name'],
        'coins': user['coins'],
        'total_paid': user['total_paid'],
        'keys_count': keys_count,
        'registered_date': user['registered_date']
    })

@app.route('/api/user/<user_id>/keys', methods=['GET'])
def get_user_keys(user_id):
    """Получить ключи пользователя"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT key_value, purchase_date, price
        FROM keys
        WHERE user_id = ?
        ORDER BY purchase_date DESC
        LIMIT 50
    """, (user_id,))
    
    keys = cursor.fetchall()
    conn.close()
    
    keys_list = []
    for key in keys:
        keys_list.append({
            'key_value': key['key_value'],
            'purchase_date': key['purchase_date'],
            'price': key['price']
        })
    
    return jsonify(keys_list)

@app.route('/api/key/price', methods=['GET'])
def get_key_price():
    """Получить текущую цену ключа"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT current_price FROM key_prices WHERE id=1")
    price = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({'price': price})

@app.route('/api/payment/create', methods=['POST'])
def create_payment():
    """Создать новый платёж"""
    data = request.json
    user_id = data.get('userId')
    amount = data.get('amount')
    coins = data.get('coins')
    
    payment_code = f"KEY{user_id[-4:] if len(user_id) > 4 else user_id}{int(time.time())}"
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO payments (user_id, amount_rub, amount_coins, payment_code, created_date, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, amount, coins, payment_code, datetime.now().isoformat(), 'pending'))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'payment_code': payment_code
    })

@app.route('/api/payment/check/<payment_code>/<user_id>', methods=['GET'])
def check_payment(payment_code, user_id):
    """Проверить статус платежа"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT status, amount_coins FROM payments
        WHERE payment_code = ? AND user_id = ?
    """, (payment_code, user_id))
    
    payment = cursor.fetchone()
    conn.close()
    
    if payment:
        return jsonify({
            'confirmed': payment['status'] == 'confirmed',
            'coins': payment['amount_coins'] if payment['status'] == 'confirmed' else 0
        })
    else:
        return jsonify({'confirmed': False, 'coins': 0})

@app.route('/api/buy/key', methods=['POST'])
def buy_key():
    """Купить ключ за монеты"""
    data = request.json
    user_id = data.get('userId')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем баланс и цену
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    cursor.execute("SELECT current_price FROM key_prices WHERE id=1")
    price = cursor.fetchone()[0]
    
    if not user or user['coins'] < price:
        conn.close()
        return jsonify({'success': False, 'error': 'Not enough coins'})
    
    # Списываем монеты
    cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (price, user_id))
    
    # Генерируем ключ
    key_value = 'KEY-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
    cursor.execute("""
        INSERT INTO keys (user_id, key_value, purchase_date, price)
        VALUES (?, ?, ?, ?)
    """, (user_id, key_value, datetime.now().isoformat(), price))
    
    # Увеличиваем цену
    cursor.execute("UPDATE key_prices SET keys_sold = keys_sold + 1, current_price = current_price + 10 WHERE id=1")
    
    # Получаем новую цену
    cursor.execute("SELECT current_price FROM key_prices WHERE id=1")
    new_price = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'key': key_value,
        'new_price': new_price
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Получить статистику"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM keys")
    keys_sold = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount_rub) FROM payments WHERE status = 'confirmed'")
    total_earned = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT current_price FROM key_prices WHERE id=1")
    current_price = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'users': users_count,
        'keys_sold': keys_sold,
        'total_earned': total_earned,
        'current_price': current_price
    })

# ========== ЗАПУСК СЕРВЕРА ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Сервер Key Shop запущен!")
    print(f"📱 Порт: {port}")
    print("🌐 Эндпоинты доступны по адресу:")
    print("   / - информация")
    print("   /api/stats - статистика")
    print("   /api/key/price - цена ключа")
    app.run(host='0.0.0.0', port=port)
