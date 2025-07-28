import os
import requests
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Ошибка: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы в .env")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Сообщение успешно отправлено")
            return True
        else:
            print(f"Ошибка отправки сообщения: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Исключение при отправке сообщения: {e}")
        return False

if __name__ == "__main__":
    # Тестовый запуск
    send_message("Привет! Это тестовое сообщение из send_telegram.py")
