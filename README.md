# Муж на час — Django MVP

## Установка

```bash
python -m venv .venv
# Windows PowerShell:
. .\.venv\Scripts\Activate.ps1
# Linux/macOS:
# . .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Открой: http://127.0.0.1:8000

## Админка
http://127.0.0.1:8000/admin — управляй услугами, заявками, отзывами.

## Заполнение прайса
В админке добавь записи **Service**: название, категория, цена «от», единица (час/работа/шт), описание.

## Публикация отзывов
Отзывы создаются клиентами на странице `/reviews/`. Галочка «approved» в админке — модерация.

## Настройки контактов в футере
Правь низ шаблона `base.html` под свой телефон/e-mail и города.

## Дальше
- RU/DE переключатель языка
- Кнопки WhatsApp/Telegram
- reCAPTCHA на формы
- E-mail уведомления при новой заявке
- Фото «до/после» и портфолио
