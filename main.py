import requests
from bs4 import BeautifulSoup
import json
import telebot
from telebot import types
from config import bot_token

TOKEN = bot_token
securitylab_url = 'https://www.securitylab.ru/news/'
habr_url = 'https://habr.com/ru/news/'

bot = telebot.TeleBot(TOKEN)

def parse_securitylab_news(news_count=None):
    response = requests.get(securitylab_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    articles_cards = soup.find_all("a", class_="article-card")

    news_links = []
    for article in articles_cards[:news_count]:
        title = article.find("h2", class_="article-card-title").text.strip()
        link = 'https://www.securitylab.ru' + article.get("href")
        news_links.append({'title': title, 'link': link})

    return news_links

def parse_habr_news(news_count=None):
    response = requests.get(habr_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    articles_list = soup.find("div", class_="tm-articles-list")
    articles = articles_list.find_all("article")

    news_links = []
    for article in articles[:news_count]:
        title = article.find("h2",).text.strip()
        link = "https://habr.com" + article.find("a", class_="tm-title__link").get("href")
        news_links.append({'title': title, 'link': link})

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
    site = message.text
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('Последняя новость'))
    markup.add(types.KeyboardButton('5 последних новостей'))
    markup.add(types.KeyboardButton('Все новости'))
    markup.add(types.KeyboardButton('Назад'))
    bot.send_message(message.chat.id, 'Выберите опцию:', reply_markup=markup)
    bot.register_next_step_handler(message, get_news, site)

def get_news(message, site):
    if site == 'SecurityLab':
        total_articles = len(parse_securitylab_news(None))
    elif site == 'Habr':
        total_articles = len(parse_habr_news(None))

    if message.text == 'Последняя новость':
        news_count = 1
    elif message.text == '5 последних новостей':
        news_count = 5
    elif message.text == 'Все новости':
        news_count = total_articles

    if site == 'SecurityLab':
        news_links = parse_securitylab_news(news_count)
    elif site == 'Habr':
        news_links = parse_habr_news(news_count)

    for article in news_links:
        bot.send_message(message.chat.id, f'<a href="{article["link"]}">{article["title"]}</a>', parse_mode='HTML')
    save_to_json(news_links, f'{site.lower()}_news.json')

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('Назад'))
    bot.send_message(message.chat.id, 'Выберите опцию:', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Назад')
def go_back(message):
    start(message)

bot.polling()
