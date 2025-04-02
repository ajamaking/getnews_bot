import os
import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types
import sqlite3
import re
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Инициализация бота
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
bot = telebot.TeleBot(TOKEN)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Источники новостей
SOURCES = {
    "Habr": "https://habr.com/ru/news/",
    "RIA": "https://ria.ru/world/",
    "Lenta": "https://lenta.ru/rss/news"
}

# Подключение к БД
conn = sqlite3.connect("news.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS published_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        link TEXT UNIQUE,
        source TEXT,
        message_id INTEGER,
        published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()


def fetch_html(url):
    """Получает HTML-страницу по URL с обработкой ошибок."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logger.error(f"Ошибка при получении HTML: {e}")
        return None


def parse_news(source, news_count):
    """Парсинг новостей с выбранного сайта."""
    parsers = {
        "Lenta": parse_lenta_news,
        "Habr": parse_habr_news,
        "RIA": parse_ria_news
    }
    return parsers[source](news_count) if source in parsers else []


def parse_lenta_news(news_count):
    """Парсинг новостей с Lenta.ru."""
    html = fetch_html(SOURCES["Lenta"])
    if not html:
        return []
    soup = BeautifulSoup(html, 'xml')
    articles = soup.find_all("item")
    return [{
        'title': a.find("title").text.strip(),
        'link': a.find("link").text.strip()
    } for a in articles[:news_count]]


def parse_habr_news(news_count):
    """Парсинг новостей с Habr."""
    html = fetch_html(SOURCES["Habr"])
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    articles = soup.find_all("article")
    return [{
        'title': a.find("h2").text.strip(),
        'link': "https://habr.com" + a.find("a").get("href")
    } for a in articles[:news_count]]


def parse_ria_news(news_count):
    """Парсинг новостей с РИА Новости."""
    html = fetch_html(SOURCES["RIA"])
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    articles = soup.find_all("a", class_="list-item__title")

    return [{
        'title': a.text.strip(),
        'link': a.get("href") if "http" in a.get("href") else f"https://ria.ru{a.get('href')}"
    } for a in articles[:news_count]]


def is_news_published(link):
    """Проверка, публиковалась ли новость ранее."""
    cursor.execute("SELECT * FROM published_news WHERE link = ?", (link,))
    return cursor.fetchone() is not None


def save_news(title, link, source, message_id):
    """Сохранение опубликованной новости в БД."""
    cursor.execute("INSERT OR IGNORE INTO published_news (title, link, source, message_id) VALUES (?, ?, ?, ?)",
                   (title, link, source, message_id))
    conn.commit()


def delete_news(link):
    """Удаление новости по ссылке."""
    cursor.execute("DELETE FROM published_news WHERE link = ?", (link,))
    conn.commit()


def delete_post_from_channel(message_id):
    """Удаление поста из канала по message_id."""
    try:
        bot.delete_message(CHANNEL_ID, message_id)
        logger.info(f"Сообщение с ID {message_id} удалено из канала.")
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")


def generate_post(title, link, source):
    """Создание поста для отправки."""
    return f"\U0001F4F0 <b>{title}</b>\n\n🔗 <a href=\"{link}\">Читать полностью</a>\n\nИсточник: {source}"


def main_menu():
    """Создание клавиатуры с главными кнопками."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Получить новости", "Опубликовать на канал")
    markup.add("Удалить новость", "Отчёт")
    return markup


def source_menu():
    """Создание клавиатуры с кнопками источников."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for source in SOURCES.keys():
        markup.add(source)
    return markup


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=main_menu())


@bot.message_handler(func=lambda message: message.text == "Получить новости")
def ask_source_news(message):
    """Выбор источника новостей перед получением."""
    bot.send_message(message.chat.id, "Выберите источник новостей:", reply_markup=source_menu())
    bot.register_next_step_handler(message, ask_news_count, "get")


@bot.message_handler(func=lambda message: message.text == "Опубликовать на канал")
def ask_source_publish(message):
    """Выбор источника новостей перед публикацией."""
    bot.send_message(message.chat.id, "Выберите источник новостей:", reply_markup=source_menu())
    bot.register_next_step_handler(message, ask_news_count, "publish")


def ask_news_count(message, action):
    """Запрос количества новостей."""
    if message.text not in SOURCES:
        bot.send_message(message.chat.id, "Ошибка: выберите источник из списка.", reply_markup=main_menu())
        return
    bot.send_message(message.chat.id, "Введите количество новостей:")
    bot.register_next_step_handler(message, process_news_request, message.text, action)


def process_news_request(message, source, action):
    """Получение и публикация новостей."""
    try:
        news_count = int(message.text)
    except ValueError:
        bot.send_message(message.chat.id, "Ошибка: введите число.", reply_markup=main_menu())
        return

    news_list = parse_news(source, news_count)

    if not news_list:
        bot.send_message(message.chat.id, "Не удалось получить новости. Попробуйте позже.", reply_markup=main_menu())
        return

    for article in news_list:
        post = generate_post(article["title"], article["link"], source)

        if action == "get":
            bot.send_message(message.chat.id, post, parse_mode='HTML')
        elif action == "publish":
            if not is_news_published(article["link"]):
                sent_message = bot.send_message(CHANNEL_ID, post, parse_mode='HTML')
                save_news(article["title"], article["link"], source, sent_message.message_id)
                logger.info(f"Опубликована новость: {article['title']}")

    bot.send_message(message.chat.id, "✅ Операция завершена!", reply_markup=main_menu())


@bot.message_handler(func=lambda message: message.text == "Удалить новость")
def delete_news_request(message):
    bot.send_message(message.chat.id, "Введите ссылку новости для удаления:")
    bot.register_next_step_handler(message, process_delete_news)


def process_delete_news(message):
    link = message.text
    cursor.execute("SELECT message_id FROM published_news WHERE link = ?", (link,))
    result = cursor.fetchone()

    if result:
        message_id = result[0]
        delete_post_from_channel(message_id)
        delete_news(link)
        bot.send_message(message.chat.id, "✅ Новость удалена из канала и базы данных!", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "Ошибка: новость не найдена.", reply_markup=main_menu())


@bot.message_handler(func=lambda message: message.text == "Отчёт")
def request_report(message):
    bot.send_message(message.chat.id, "Введите команду отчёта (/report YYYY-MM-DD или /report last N):",
                     reply_markup=main_menu())


@bot.message_handler(commands=['report'])
def report_news(message):
    """Вывод отчёта по новостям."""
    command = message.text.split(maxsplit=1)

    if len(command) == 1:
        cursor.execute(
            "SELECT title, link, source, published_at FROM published_news ORDER BY published_at DESC LIMIT 10")
    else:
        param = command[1]

        if re.match(r"\d{4}-\d{2}-\d{2}", param):
            cursor.execute("SELECT title, link, source, published_at FROM published_news WHERE DATE(published_at) = ?",
                           (param,))
        elif re.match(r"last \d+", param):
            num = int(param.split()[1])
            cursor.execute(
                "SELECT title, link, source, published_at FROM published_news ORDER BY published_at DESC LIMIT ?",
                (num,))
        else:
            bot.send_message(message.chat.id, "Ошибка: используйте /report YYYY-MM-DD или /report last N",
                             reply_markup=main_menu())
            return

    news_list = cursor.fetchall()
    if not news_list:
        bot.send_message(message.chat.id, "Нет опубликованных новостей за этот период.", reply_markup=main_menu())
        return

    report_text = "\n\n".join([f"📌 <b>{title}</b>\n🔗 <a href=\"{link}\">Читать</a>\n📰 {source} | 🕒 {published_at}" for
                               title, link, source, published_at in news_list])
    bot.send_message(message.chat.id, report_text, parse_mode="HTML", reply_markup=main_menu())


if __name__ == "__main__":
    logger.info("Бот запущен.")
    bot.polling(none_stop=True)
