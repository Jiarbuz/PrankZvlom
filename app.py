import os
import time
import ipaddress
import requests
import datetime
import threading
import logging
from datetime import timedelta
from flask import Flask, render_template, request, session, redirect, url_for, abort, jsonify
from flask_babel import Babel
from flask_limiter import Limiter
from user_agents import parse
from redis import Redis
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Инициализация Flask
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'super-secret-key')
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# Настройка Redis
redis_client = Redis(host='localhost', port=6379)

# Настройки сессии и безопасности
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=1),
)

# Настройка лимитера
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="redis://red-d23qvvumcj7s739luqo0:uB5xnzFoWjSAJSlF7gozCjARDba0Fhdt@red-d23qvvumcj7s739luqo0:6379",
    default_limits=["200 per day", "50 per hour"]
)

# Настройка Babel
def get_locale():
    return session.get('lang', 'ru')

babel = Babel(app, locale_selector=get_locale)

# Конфигурация Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOG_COOLDOWN = 60
last_log_message = None

# Блокировки и безопасность
BLOCKED_RANGES = [
    ("104.16.0.0", "104.31.255.255"),
]
blocked_ips = {}
ip_request_times = {}
sent_messages_cache = {}
MAX_REQUESTS = 50
WINDOW_SECONDS = 60
BLOCK_TIME = 1800
MESSAGE_CACHE_TIMEOUT = 300

# Переводы
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
        'junior_mods': "Младшие модераторы",
        'junior_jr': "Новички",
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
        'junior_mods': "Junior Moderators",
        'junior_jr': "Newbies",
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

# Вспомогательные функции
def get_ip_info(ip):
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,isp")
        data = resp.json()
        if data.get('status') == 'success':
            return {
                'country': data.get('country', ''),
                'countryCode': data.get('countryCode', ''),
                'region': data.get('regionName', ''),
                'city': data.get('city', ''),
                'isp': data.get('isp', ''),
                'ip': ip
            }
        return {}
    except Exception:
        return {}

def ip_in_range(ip, ip_range):
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ipaddress.ip_address(ip_range[0]) <= ip_obj <= ipaddress.ip_address(ip_range[1])
    except ValueError:
        return False

def get_client_ip():
    if 'X-Forwarded-For' in request.headers:
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        app.logger.error(f"Error sending Telegram message: {e}")

# Middleware для защиты и логирования
@app.before_request
def protect_and_log():
    if request.path.startswith('/static/'):
        return

    # Проверка блокировки IP
    ip = get_client_ip()
    for ip_range in BLOCKED_RANGES:
        if ip_in_range(ip, ip_range):
            abort(403)

    # Rate limiting
    now = time.time()
    blocked_until = blocked_ips.get(ip)
    if blocked_until and blocked_until > now:
        abort(403)
    elif blocked_until:
        blocked_ips.pop(ip, None)

    req_times = ip_request_times.get(ip, [])
    req_times = [t for t in req_times if now - t < WINDOW_SECONDS]
    req_times.append(now)
    ip_request_times[ip] = req_times

    if len(req_times) > MAX_REQUESTS:
        blocked_ips[ip] = now + BLOCK_TIME
        info = get_ip_info(ip)
        message = (
            f"🚫 IP заблокирован за превышение лимита\n"
            f"🕒 Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📡 IP: <code>{info.get('ip', ip)}</code>\n"
            f"🌍 Страна: {info.get('country', 'Unknown')}\n"
            f"🏙️ Город: {info.get('city', 'Unknown')}\n"
            f"🏢 Провайдер: {info.get('isp', 'Unknown')}\n"
            f"📝 Запросов за {WINDOW_SECONDS} сек: {len(req_times)}"
        )
        threading.Thread(target=send_telegram_message, args=(message,)).start()
        abort(403)

    # Логирование посещений (исключаем страницу /log из логирования)
    global last_log_message
    if request.path != '/log':
        ua = parse(request.headers.get('User-Agent', 'Unknown'))
        log_message = (
            f"🌐 Новый посетитель\n"
            f"🕒 Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📡 IP: {ip}\n"
            f"🖥 OS: {ua.os.family}\n"
            f"🌍 Browser: {ua.browser.family}\n"
            f"📍 Страница: {request.path}"
        )
        if log_message != last_log_message:
            last_log_message = log_message
            threading.Thread(target=send_telegram_message, args=(log_message,)).start()

# Маршруты
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
                },
                {
                    "name": "пряниковий манiяк", 
                    "url": "https://t.me/apect0bah_3a_cnam",
                    "avatar": "https://ltdfoto.ru/images/2025/07/28/photo_2025-07-11_22-38-54.jpg"
                },
                {
                    "name": "ὙperBoreia", 
                    "url": "https://t.me/antikoks",
                    "avatar": "https://i.ibb.co/RT7sjHWY/photo-2025-07-27-18-51-08.jpg"
                },
                {
                    "name": "Алексей Проктолог [ ПРОКТОЛОГИЯ ]", 
                    "url": "https://t.me/alexey_proktolog",
                    "avatar": "https://ltdfoto.ru/images/2025/07/28/photo_2025-07-24_02-53-41.md.jpg"
                }
            ],
            t['junior_mods']: [
                {
                    "name": "j17", 
                    "url": "https://t.me/j17s",
                    "avatar": "https://ltdfoto.ru/images/2025/07/25/photo_2025-07-20_00-29-14.jpg"
                }
            ],
            t['junior_jr']: [
                {
                    "name": "Zxc", 
                    "url": "https://t.me/Zxc2",
                    "avatar": None
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

@app.route('/home')
@limiter.limit("10 per minute")
def home():
    return redirect(url_for('index'))

@app.route('/set_language/<lang>')
@limiter.limit("5 per minute")
def set_language(lang):
    if lang in ['ru', 'en']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/log', methods=['POST'])
def log():
    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    ip = get_client_ip()
    now = datetime.datetime.now()
    info = get_ip_info(ip)

    text = (
        f"📥 Лог\n"
        f"🕒 Время: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📡 IP: <code>{info.get('ip', ip)}</code>\n"
        f"🌍 Страна: {info.get('country', 'Unknown')}\n"
        f"🏙️ Город: {info.get('city', 'Unknown')}\n"
        f"🏢 Провайдер: {info.get('isp', 'Unknown')}\n"
        f"💬 Сообщение: {message}"
    )

    threading.Thread(target=send_telegram_message, args=(text,)).start()
    return jsonify({'status': 'ok'}), 200

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template('rate_limit.html'), 429

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)