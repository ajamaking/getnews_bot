import requests
from bs4 import BeautifulSoup
import json
import telebot
from telebot import types
from config import bot_token

TOKEN = bot_token
securitylab_url = 'https://www.securitylab.ru/news/'
habr_url = 'https://habr.com/ru/rss/hub/just_ai/'

bot = telebot.TeleBot(TOKEN)

def parse_securitylab_news(news_count=5):
    response = requests.get(securitylab_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    articles_cards = soup.find_all("a", class_="article-card")

    news_links = []
    for article in articles_cards[:news_count]:
        title = article.find("h2", class_="article-card-title").text.strip()
        link = 'https://www.securitylab.ru' + article.get("href")
        news_links.append({'title': title, 'link': link})

    return news_links

def parse_habr_news():
    response = requests.get(habr_url)
    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all("item")
    news_links = [{'title': item.find("title").text, 'link': item.find("link").text} for item in items[:5]]
    return news_links

def save_to_json(news_links, filename):
    with open(filename, 'w') as f:
        json.dump(news_links, f, ensure_ascii=False, indent=4)

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('SecurityLab'))
    markup.add(types.KeyboardButton('Habr'))
    bot.send_message(message.chat.id, 'Выберите сайт:', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ['SecurityLab', 'Habr'])
def choose_option(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('Последняя новость'))
    markup.add(types.KeyboardButton('5 последних новостей'))
    markup.add(types.KeyboardButton('Все новости'))
    bot.send_message(message.chat.id, 'Выберите опцию:', reply_markup=markup)
    bot.register_next_step_handler(message, get_news, message.text)

def get_news(message, site):
    if site == 'SecurityLab':
        news_links = parse_securitylab_news()
    elif site == 'Habr':
        news_links = parse_habr_news()

    if message.text == 'Последняя новость':
        news = news_links[:1]
    elif message.text == '5 последних новостей':
        news = news_links[:5]
    elif message.text == 'Все новости':
        news = news_links

    for article in news:
        bot.send_message(message.chat.id, f'<a href="{article["link"]}">{article["title"]}</a>', parse_mode='HTML')
    save_to_json(news, f'{site.lower()}_news.json')

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('Назад'))
    bot.send_message(message.chat.id, 'Выберите опцию:', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Назад')
def go_back(message):
    start(message)

bot.polling()
