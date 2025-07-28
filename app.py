import os
import datetime
import threading
import requests
import logging
import ipaddress
import time
from flask import Flask, render_template, request, session, redirect, url_for
from user_agents import parse
from dotenv import load_dotenv
from flask_babel import Babel
from flask_limiter import Limiter
from flask import jsonify
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# Загрузка переменных окружения
load_dotenv()

# Инициализация Flask
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# Настройка защиты от DDoS
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # Для продакшена используйте Redis: "redis://localhost:6379"
)

LOG_COOLDOWN = 60  # время в секундах, чтобы не отправлять повторно одно и то же сообщение

last_log_message = None  # глобально

# Настройка Babel
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'
babel = Babel(app)

def get_locale():
    return session.get('lang', 'ru')

babel.init_app(app, locale_selector=get_locale)

# Конфигурация Telegram
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text):
    if not bot_token or not chat_id:
        print("Telegram credentials not configured")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

# Переводы для приложения
translations = {
    'ru': {
        'info_title': "PrankVzlom 📹📔",
        'disclaimer': "САЙТ СДЕЛАН ДЛЯ РАЗВЛЕКАТЕЛЬНЫХ ЦЕЛЕЙ И МЫ НИКОГО НЕ ХОТИМ ОСКОРБИТЬ ИЛИ УНИЗИТЬ",
        'software': "Софты",
        'admins': "Администрация",
        'partners': "Партнёры",
        'main_admin': "Главный администратор",
        'creators': "Создатели",
        'senior_admins': "Старшие администраторы",
        'junior_admins': "Младшие администраторы",
        'senior_mods': "Старшие модераторы",
        'copyright': "© 2025 PrankVzlom. Все права защищены.",
        'accept': "Принять",
        'modal_title': "ВНИМАНИЕ",
        'modal_content': "Этот сайт создан исключительно в развлекательных целях. Мы не хотим никого оскорбить или унизить.",
        'links': {
            'official_channel': "ОФИЦИАЛЬНЫЙ КАНАЛ",
            'redirect': "ПЕРЕХОДНИК",
            'chat': "ЧАТ",
            'tutorial': "ТУТОРИАЛ ПО КАМЕРАМ",
            'audio': "АУДИО КАНАЛ",
            'bot': "БОТ",
            'tiktok': "ТИК ТОК",
            'support': "ПОДДЕРЖКА"
        },
        'partner_owl': "Скоро..."
    },
    'en': {
        'info_title': "PrankVzlom 📹📔",
        'disclaimer': "THIS SITE IS FOR ENTERTAINMENT PURPOSES ONLY AND WE DON'T WANT TO OFFEND OR HUMILIATE ANYONE",
        'software': "Software",
        'admins': "Administration",
        'partners': "Partners",
        'main_admin': "Main Admin",
        'creators': "Creators",
        'senior_admins': "Senior Admins",
        'junior_admins': "Junior Admins",
        'senior_mods': "Senior Moderators",
        'copyright': "© 2025 PrankVzlom. All rights reserved.",
        'accept': "Accept",
        'modal_title': "WARNING",
        'modal_content': "This site is made for entertainment purposes only. We don't want to offend or humiliate anyone.",
        'links': {
            'official_channel': "OFFICIAL CHANNEL",
            'redirect': "REDIRECT",
            'chat': "CHAT",
            'tutorial': "CAMERA TUTORIAL",
            'audio': "AUDIO CHANNEL",
            'bot': "BOT",
            'tiktok': "TIKTOK",
            'support': "SUPPORT"
        },
        'partner_owl': "Soon..."
    }
}

# Главная страница
@app.route('/')
@limiter.limit("10 per minute")
def index():
    lang = session.get('lang', 'ru')
    t = translations[lang]
    
    site_data = {
        "info": {
            "title": t['info_title'],
            "description": t['disclaimer'],
            "links": [
                {"name": t['links']['official_channel'], "url": "https://t.me/+K7nGKPBpyIswMDhi"},
                {"name": t['links']['redirect'], "url": "https://t.me/prankzvon"},
                {"name": t['links']['chat'], "url": "https://t.me/+gUAplPwH9GhiMDg1"},
                {"name": t['links']['tutorial'], "url": "https://t.me/+8dU6v546c3JiODc8"},
                {"name": t['links']['audio'], "url": "https://t.me/+Egx6krEx0zM3NTRl"},
                {"name": t['links']['bot'], "url": "https://t.me/prankvzlomnewbot"},
                {"name": t['links']['tiktok'], "url": "https://www.tiktok.com/@jiarbuz"},
                {"name": t['links']['support'], "url": "https://t.me/PrankVzlomUnban"}
            ]
        },
        "software": [
            {"name": "SmartPSS", "url": "https://cloud.mail.ru/public/11we/vbzNxnSQi"},
            {"name": "Nesca", "url": "https://cloud.mail.ru/public/J2sJ/3vuy7XC1n"},
            {"name": "Noon", "url": "https://cloud.mail.ru/public/4Cmj/yMeVGQXE6"},
            {"name": "Ingram", "url": "https://cloud.mail.ru/public/nPCQ/JA73sB4tq"},
            {"name": "SoundPad", "url": "https://mega.nz/file/Ck4jhZBL#bXmvrKCquhJrt2hMlHiV2QfpzMm3uj_lLjv9yFLEjgA"},
            {"name": "iVMS-4200", "url": "https://cloud.mail.ru/public/8t1M/g5zfvA8Lq"},
            {"name": "MVFPS", "url": "https://cloud.mail.ru/public/26ae/58VrzdvYT"},
            {"name": "KPortScan", "url": "https://cloud.mail.ru/public/yrup/9PQyDe86G"}
        ],
        "admins": {
            t['main_admin']: [
                {
                    "name": "Православный Бес", 
                    "url": "https://t.me/bes689",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-25_06-19-13.jpg"
                }
            ],
            t['creators']: [
                {
                    "name": "Everyday", 
                    "url": "https://t.me/mobile_everyday",
                    "avatar": "https://i.ibb.co/spKRJcmK/photo-2025-05-23-16-45-24.jpg"
                },
                {
                    "name": "Андрей", 
                    "url": "https://t.me/prankzvon231",
                    "avatar": None
                },
                {
                    "name": "Lucper", 
                    "url": "https://t.me/lucper1",
                    "avatar": "https://i.ibb.co/TMbSG0jp/photo-2025-07-20-01-44-45-2.gif"
                }
            ],
            t['senior_admins']: [
                {
                    "name": "Диванный воин Кчау", 
                    "url": "https://t.me/bestanov",
                    "avatar": "https://i.ibb.co/rKLcJ70c/photo-2025-04-23-02-37-37.jpg"
                },
                {
                    "name": "JIARBUZ.exe", 
                    "url": "https://t.me/jiarbuz",
                    "avatar": "https://i.ibb.co/kgBVDqM8/photo-2025-06-10-15-16-39.jpg"
                },
                {
                    "name": "ximi13p", 
                    "url": "https://t.me/ximi13p",
                    "avatar": None
                }
            ],
            t['junior_admins']: [
                {
                    "name": "k3stovski", 
                    "url": "https://t.me/k3stovski",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-24_23-01-05.jpg"
                },
                {
                    "name": "kronaфacia", 
                    "url": "https://t.me/kronaphasia",
                    "avatar": None
                },
                {
                    "name": "Жук", 
                    "url": "https://t.me/werwse",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-23_22-07-41.md.jpg"
                },
                {
                    "name": "Цыфра", 
                    "url": "https://t.me/himera_unturned",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-01_00-52-02.md.jpg"
                },
                {
                    "name": "Наполеонский пистолэт", 
                    "url": "https://t.me/prnkzvn",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-20_04-28-28.jpg"
                }
            ],
            t['senior_mods']: [
                {
                    "name": "Paul Du Rove", 
                    "url": "tg://openmessage?user_id=7401067755",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-05-03_16-27-45.jpg"
                },
                {
                    "name": "aiocryp", 
                    "url": "https://t.me/aiocryp",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-25_00-37-50.jpg"
                },
                {
                    "name": "саня шпалин", 
                    "url": "https://t.me/sanya_shpalka",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-22_03-52-56.md.jpg"
                }
            ]
        },
        "partners": [
            {
                "name": t['partner_owl'],
                "url": "https://youtu.be/dQw4w9WgXcQ",
                "avatar": "https://cdn-icons-png.flaticon.com/512/8890/8890972.png"
            }
        ],
        "translations": t
    }
    return render_template('index.html', data=site_data, current_lang=lang)

# Установка языка
@app.route('/set_language/<lang>')
@limiter.limit("5 per minute")
def set_language(lang):
    if lang in ['ru', 'en']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

# Тг бот

@app.route('/log', methods=['POST'])
def log():
    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'  # исправлено
    payload = {
        'chat_id': chat_id,  # исправлено
        'text': message
    }
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        return jsonify({'status': 'ok'}), 200
    else:
        return jsonify({'error': 'Failed to send message to Telegram'}), 500

# Логирование посетителей
@app.before_request
@limiter.limit("20 per minute")
def log_visitor_info():
    global last_log_message
    
    if request.path.startswith('/static/'):
        return

    ip = get_client_ip()
    ua = parse(request.headers.get('User-Agent', 'Unknown'))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    message = (
        f"🌐 Новый посетитель\n"
        f"🕒 Время: {now}\n"
        f"📡 IP: {ip}\n"
        f"🖥 OS: {ua.os.family}\n"
        f"🌍 Browser: {ua.browser.family}\n"
        f"📍 Страница: {request.path}"
    )

    if message == last_log_message:
        # Если сообщение совпадает с последним, не отправляем
        return

    last_log_message = message
    threading.Thread(target=send_telegram_message, args=(message,)).start()


def get_client_ip():
    # Попытка взять IP из заголовка X-Forwarded-For (если прокси настроен)
    if 'X-Forwarded-For' in request.headers:
        # В заголовке может быть несколько IP, берём первый (реальный клиентский)
        ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
    else:
        ip = request.remote_addr
    return ip

# Обработчик ошибки 429
@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template('rate_limit.html'), 429

if __name__ == '__main__':
    app.run(debug=True)