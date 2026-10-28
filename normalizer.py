# -*- coding: utf-8 -*-
"""
Нормализация названия препарата из Excel в короткий поисковый запрос,
который реально понимает поиск на 24lek.ru.

Принцип (выведен из примеров в задании):
  бренд [+ количество упаковки (из №XX)] [+ объём в мл, если есть] [+ первые 3 буквы формы выпуска]

Примеры:
  ПЕНТАЛГИН №12 ТАБЛ.П.П.О. /ФАРМСТАНДАРТ ЛЕКСРЕДСТВА ОАО/ -> пенталгин 12 таб
  АЦЦ 200МГ №20 ТАБ.                                        -> ацц 20 таб
  КСИЛОМЕТАЗОЛИН СПРЕЙ                                       -> ксилометазолин спр
  ТАУФОН 4% 10 МЛ КАПЛИ ГЛАЗН. /ОТИСИФАРМ/                   -> тауфон 10 мл кап
"""

import re

# Стемы форм выпуска: если слово начинается с одного из этих стемов -> форма
# = первые 3 буквы НАЙДЕННОГО слова (не стема!).
FORM_STEMS = [
    "табл", "таб",
    "капсул",
    "капл",           # капли
    "кап",
    "спрей", "спр",
    "раствор", "раст",
    "мазь", "мази",
    "гель", "гел",
    "свеч",
    "пластыр",
    "порошок", "пор",
    "эмульси",
    "сироп",
    "лосьон",
    "аэрозол",
    "гранул",
    "паст",
    "крем",
]

# Слова-"шумы", которые никогда не должны попадать в бренд (способ введения и т.п.)
NOISE_WORDS = {
    "глазн", "наруж", "внутр", "ректал", "вагинал", "назал",
    "п", "о",  # остатки от "п.п.о."
}


def _strip_brackets(text: str) -> str:
    text = re.sub(r"/[^/]*/", " ", text)   # /ФАРМСТАНДАРТ .../
    text = re.sub(r"\([^)]*\)", " ", text)  # (производитель)
    text = re.sub(r"\[[^\]]*\]", " ", text)  # [производитель]
    return text


def normalize_name(raw_name: str) -> str:
    """Возвращает нормализованную поисковую строку для 24lek.ru."""
    if not raw_name:
        return ""

    text = _strip_brackets(raw_name)
    text = text.lower()

    # 1) количество упаковки из №XX (приоритетный источник qty)
    qty = None
    m_qty = re.search(r"№\s*(\d+)", text)
    if m_qty:
        qty = m_qty.group(1)
        text = re.sub(r"№\s*\d+", " ", text)

    # 2) убираем концентрацию в процентах (4%, 0.05% и т.п.) — это НЕ количество упаковки
    text = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", text)

    # 3) убираем дозировку в мг/мкг (200мг, 500 мг) — тоже не количество упаковки
    text = re.sub(r"\d+(?:[.,]\d+)?\s*(мг|мкг)\b", " ", text)

    # 4) объём в мл — важная часть названия, сохраняем отдельно
    volume = None
    m_vol = re.search(r"(\d+(?:[.,]\d+)?)\s*мл\b", text)
    if m_vol:
        volume = f"{m_vol.group(1).replace(',', '.')} мл"
        text = re.sub(r"\d+(?:[.,]\d+)?\s*мл\b", " ", text, count=1)

    # 5) если количество не нашлось через №, пробуем взять одиночное число,
    #    оставшееся в тексте (напр. "x 12", "12 шт")
    if qty is None:
        m_qty2 = re.search(r"\b(\d+)\b", text)
        if m_qty2:
            qty = m_qty2.group(1)
            text = re.sub(r"\b" + re.escape(qty) + r"\b", " ", text, count=1)

    # 6) токенизация по кириллическим словам
    tokens = re.findall(r"[а-яё]+", text)
    tokens = [t for t in tokens if t not in NOISE_WORDS]

    # 7) ищем форму выпуска
    form = None
    form_idx = None
    for i, tok in enumerate(tokens):
        for stem in FORM_STEMS:
            if tok.startswith(stem):
                form = tok[:3]
                form_idx = i
                break
        if form:
            break

    if form_idx is not None:
        brand_tokens = tokens[:form_idx]
    else:
        brand_tokens = tokens

    brand = " ".join(brand_tokens).strip()
    if not brand:
        # fallback — на случай совсем необычного формата
        brand = re.sub(r"[^а-яё\s]", " ", raw_name.lower())
        brand = re.sub(r"\s+", " ", brand).strip()

    parts = [brand]
    if qty:
        parts.append(qty)
    if volume:
        parts.append(volume)
    if form:
        parts.append(form)

    result = " ".join(p for p in parts if p)
    result = re.sub(r"\s+", " ", result).strip()
    return result


if __name__ == "__main__":
    tests = [
        "ПЕНТАЛГИН №12 ТАБЛ.П.П.О. /ФАРМСТАНДАРТ ЛЕКСРЕДСТВА ОАО/",
        "АЦЦ 200МГ №20 ТАБ.",
        "КСИЛОМЕТАЗОЛИН СПРЕЙ",
        "ТАУФОН 4% 10 МЛ КАПЛИ ГЛАЗН. /ОТИСИФАРМ/",
    ]
    for t in tests:
        print(f"{t!r} -> {normalize_name(t)!r}")
