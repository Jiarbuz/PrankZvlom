import redis

def main():
    try:
        # Подключаемся к Redis (по умолчанию localhost:6379)
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Проверяем соединение
        if not r.ping():
            print("Не удалось подключиться к Redis")
            return
        
        print("Подключение к Redis успешно")

        # Устанавливаем ключ с текстом
        r.set('greeting', 'Hello Redis!')

        # Получаем значение ключа
        greeting = r.get('greeting')
        print(f"greeting: {greeting}")

        # Проверяем, существует ли ключ
        exists = r.exists('greeting')
        print(f"Ключ 'greeting' существует? {'Да' if exists else 'Нет'}")

        # Инкрементируем числовой ключ
        r.set('counter', 0)
        r.incr('counter')
        counter = r.get('counter')
        print(f"Значение 'counter' после инкремента: {counter}")

        # Удаляем ключ
        r.delete('greeting')
        exists = r.exists('greeting')
        print(f"Ключ 'greeting' существует после удаления? {'Да' if exists else 'Нет'}")

    except redis.RedisError as e:
        print(f"Ошибка Redis: {e}")

if __name__ == "__main__":
    main()
