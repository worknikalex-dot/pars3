# -*- coding: utf-8 -*-
"""
Конфигурация проекта.
Заполните DADATA_TOKEN своим бесплатным ключом с https://dadata.ru/api/suggest/address/
(регистрация бесплатная, в бесплатном тарифе геокодирования адреса более чем достаточно).
"""

# Токен API Dadata (Suggestions API) — ОБЯЗАТЕЛЬНО укажите свой
DADATA_TOKEN = "скрыто"
DADATA_SECRET_KEY = "скрыто"

# Радиус поиска аптек от адреса, метры
RADIUS_METERS = 300

# Город для фильтрации подсказок Dadata (чтобы адрес однозначно резолвился в Красноярске)
DADATA_CITY_HINT = "Красноярск"

# Файлы проекта (должны лежать рядом с main.py)
PRODUCTS_FILE = "products.xlsx"
APTEKI_FILE = "apteki.json"
REPORT_FILE = "report.xlsx"

# Параметр city на сайте 24lek.ru. 0 = Красноярск (основной город справочника).
CITY_ID_24LEK = 0
RAON_ID_24LEK = 0

# Задержка между HTTP-запросами к 24lek.ru, секунды (не долбить сайт слишком часто)
REQUEST_DELAY = 0.6

# Максимум "страниц" (по 50 товаров) на один запрос препарата.
# Если среди первых найденных уже встретились все нужные аптеки — скрипт остановится раньше.
MAX_PAGES_PER_QUERY = 30

# User-Agent для запросов
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
