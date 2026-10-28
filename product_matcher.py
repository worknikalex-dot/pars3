# -*- coding: utf-8 -*-
"""Проверка соответствия карточки 24lek.ru исходному препарату."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation


FORM_PATTERNS = {
    "таблетки_шипучие": (
        r"\bтаблетк\w*\s+шипуч\w*",
        r"\bтабл\.?\s*шип\w*",
        r"\bтаб\s+шип\w*",
    ),
    "таблетки": (
        r"\bтаблетк\w*",
        r"\bтабл\b",
        r"\bтаб\b",
    ),
    "капсулы": (
        r"\bкапсул\w*",
        r"\bкапс\b",
    ),
    "капли": (r"\bкапл\w*",),
    "раствор": (r"\bраствор\w*", r"\bр-р\b"),
    "сироп": (r"\bсироп\w*",),
    "спрей": (r"\bспре\w*", r"\bспр\b"),
    "мазь": (r"\bмаз\w*",),
    "гель": (r"\bгел\w*",),
    "крем": (r"\bкрем\w*",),
    "свечи": (r"\bсвеч\w*", r"\bсуппозитор\w*"),
    "порошок": (r"\bпорош\w*",),
    "гранулы": (r"\bгранул\w*",),
    "суспензия": (r"\bсуспенз\w*",),
    "эмульсия": (r"\bэмульс\w*",),
    "пастилки": (r"\bпастил\w*",),
    "пластырь": (r"\bпластыр\w*",),
    "аэрозоль": (r"\bаэрозол\w*",),
}

UNIT_ALIASES = {
    "мкг": "мкг",
    "µg": "мкг",
    "mcg": "мкг",
    "мг": "мг",
    "mg": "мг",
    "г": "г",
    "гр": "г",
    "грамм": "г",
    "грамма": "г",
    "граммов": "г",
    "мл": "мл",
    "ml": "мл",
    "л": "л",
    "литр": "л",
    "литра": "л",
    "литров": "л",
    "ме": "ме",
    "iu": "ме",
}

NOISE_WORDS = {
    "таб", "табл", "таблетка", "таблетки", "таблеток",
    "кап", "капл", "капли", "капель", "капсула", "капсулы",
    "п", "о", "пленочной", "пленочная", "пленочное",
    "покрытой", "покрытые", "покрытых", "оболочкой",
    "для", "приема", "внутрь", "наружного", "применения",
    "глазные", "глазн", "назальные", "назал",
    "ректальные", "вагинальные",
    "шт", "штук", "штуки",
}

BASE_STOP_WORDS = NOISE_WORDS | {
    "мг", "мкг", "г", "гр", "мл", "л", "ме", "iu",
    "порошок", "раствор", "сироп", "спрей", "мазь", "гель",
    "крем", "свечи", "гранулы", "суспензия", "эмульсия",
    "пастилки", "пластырь", "аэрозоль",
}

MEASURE_RE = re.compile(
    r"(?<![а-яёa-z0-9])"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>мкг\.?|µg|mcg|мг|mg|гр|грамм(?:а|ов)?|г|"
    r"мл|ml|литр(?:а|ов)?|л|м\.?е\.?|ме|iu)"
    r"(?![а-яёa-z])",
    re.IGNORECASE,
)

PERCENT_RE = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*%")

# Поддерживаемые форматы: №20, #20, n20, x20, 20 шт., 20шт., 20 штук.
PACK_PATTERNS = (
    re.compile(r"(?:#\s*|(?<![a-zа-я])n\s*)(\d+)\b", re.IGNORECASE),
    re.compile(r"[xх×]\s*(\d+)\b", re.IGNORECASE),
    re.compile(
        r"(?<!\d)(\d+)\s*(?:шт\.?|штук(?:а|и)?)\b",
        re.IGNORECASE,
    ),
)

BRACKET_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def _clean_text(value):
    """Нормализовать текст, сохранив знак упаковки до Unicode-нормализации."""
    text = str(value or "")

    # Важно: сначала заменяем №, поскольку NFKC может преобразовать его в No.
    text = text.replace("№", " # ")
    text = unicodedata.normalize("NFKC", text).lower()

    text = text.replace("ё", "е")
    text = text.replace("×", "x").replace("х", "x")
    text = text.replace(",", ".")
    text = re.sub(r"/[^/]*/", " ", text)
    text = re.sub(r"[/\\|]+", " ", text)
    text = BRACKET_RE.sub(" ", text)
    text = re.sub(r"[^a-zа-я0-9.%#\s-]", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def _decimal_key(value):
    try:
        return format(
            Decimal(str(value).replace(",", ".")).normalize(),
            "f",
        )
    except (InvalidOperation, ValueError):
        return str(value)


def _extract_measurements(text):
    result = []

    for match in MEASURE_RE.finditer(text):
        unit = match.group("unit").lower().rstrip(".")
        result.append((
            _decimal_key(match.group("value")),
            UNIT_ALIASES.get(unit, unit),
        ))

    return result


def _extract_percentages(text):
    return sorted(
        _decimal_key(match.group(1))
        for match in PERCENT_RE.finditer(text)
    )


def _extract_pack_count(text):
    """Извлечь количество единиц в упаковке."""
    candidates = []

    for pattern in PACK_PATTERNS:
        for match in pattern.finditer(text):
            candidates.append((match.start(), int(match.group(1))))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _base_tokens(text):
    """Получить значимые слова названия без дозировок и формы выпуска."""
    text = MEASURE_RE.sub(" ", text)
    text = PERCENT_RE.sub(" ", text)

    for pattern in PACK_PATTERNS:
        text = pattern.sub(" ", text)

    # Удаляем знак упаковки, чтобы # не превратился в слово.
    text = text.replace("#", " ")
    text = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", text)

    for patterns in FORM_PATTERNS.values():
        for pattern in patterns:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    tokens = re.findall(r"[a-zа-я]+", text)

    return [
        token for token in tokens
        if token not in BASE_STOP_WORDS and len(token) > 1
    ]


def _extract_forms(text):
    forms = set()

    for form, patterns in FORM_PATTERNS.items():
        if any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in patterns
        ):
            forms.add(form)

    return forms


def _forms_compatible(source_forms, card_forms):
    if not source_forms:
        return True, "форма выпуска в исходном названии не указана"

    if not card_forms:
        return False, "в карточке не удалось определить форму выпуска"

    compatible = {
        "таблетки": {"таблетки", "таблетки_шипучие"},
        "таблетки_шипучие": {"таблетки_шипучие"},
    }

    for form in source_forms:
        allowed = compatible.get(form, {form})

        if not (allowed & card_forms):
            return False, (
                "форма выпуска не совпадает: "
                f"исходная {form}, карточка "
                f"{', '.join(sorted(card_forms))}"
            )

    return True, "форма выпуска совпадает"


def _result(matches, reason, source_name, card_name, details):
    return {
        "matches": bool(matches),
        "reason": reason,
        "source_name": source_name,
        "card_name": card_name,
        "details": [
            {
                "check": name,
                "matches": bool(ok),
                "reason": message,
            }
            for name, ok, message in details
        ],
    }


def match_product(source_name, card_name):
    """Подробно проверить соответствие карточки исходному товару."""
    source_raw = str(source_name or "").strip()
    card_raw = str(card_name or "").strip()

    if not source_raw:
        return _result(
            False, "пустое исходное название товара",
            source_raw, card_raw, [],
        )

    if not card_raw:
        return _result(
            False, "пустое название карточки",
            source_raw, card_raw, [],
        )

    source = _clean_text(source_raw)
    card = _clean_text(card_raw)
    details = []

    # 1. Проверка основных слов названия.
    source_tokens = set(_base_tokens(source))
    card_tokens = set(_base_tokens(card))
    missing_tokens = source_tokens - card_tokens

    if missing_tokens:
        reason = (
            "в карточке отсутствуют слова: "
            + ", ".join(sorted(missing_tokens))
        )
        details.append(("название", False, reason))
        return _result(
            False, reason, source_raw, card_raw, details,
        )

    details.append((
        "название", True, "основа названия совпадает",
    ))

    # 2. Количество в упаковке.
    source_pack = _extract_pack_count(source)
    card_pack = _extract_pack_count(card)

    if source_pack is not None:
        ok = source_pack == card_pack

        if ok:
            reason = f"количество в упаковке совпадает: {source_pack} шт."
        else:
            card_value = (
                "не указано" if card_pack is None
                else f"{card_pack} шт."
            )
            reason = (
                "количество в упаковке не совпадает: "
                f"исходное {source_pack} шт., карточка {card_value}"
            )

        details.append(("упаковка", ok, reason))

        if not ok:
            return _result(
                False, reason, source_raw, card_raw, details,
            )

    # 3. Дозировка и объём.
    source_measures = _extract_measurements(source)
    card_measures = _extract_measurements(card)

    if source_measures:
        remaining = list(card_measures)
        missing = []

        for item in source_measures:
            if item in remaining:
                remaining.remove(item)
            else:
                missing.append(item)

        ok = not missing

        if ok:
            reason = "дозировка/объём совпадает"
        else:
            reason = (
                "в карточке отсутствуют характеристики: "
                + ", ".join(
                    f"{value} {unit}" for value, unit in missing
                )
            )

        details.append(("дозировка и объём", ok, reason))

        if not ok:
            return _result(
                False, reason, source_raw, card_raw, details,
            )

    # 4. Концентрация.
    source_pct = _extract_percentages(source)
    card_pct = _extract_percentages(card)

    if source_pct:
        remaining = list(card_pct)
        missing = []

        for value in source_pct:
            if value in remaining:
                remaining.remove(value)
            else:
                missing.append(value)

        ok = not missing

        if ok:
            reason = "концентрация совпадает"
        else:
            reason = (
                "концентрация не совпадает: исходная "
                + ", ".join(value + "%" for value in source_pct)
                + "; карточка "
                + (
                    ", ".join(value + "%" for value in card_pct)
                    or "не указана"
                )
            )

        details.append(("концентрация", ok, reason))

        if not ok:
            return _result(
                False, reason, source_raw, card_raw, details,
            )

    # 5. Лекарственная форма.
    ok, reason = _forms_compatible(
        _extract_forms(source),
        _extract_forms(card),
    )
    details.append(("форма выпуска", ok, reason))

    if not ok:
        return _result(
            False, reason, source_raw, card_raw, details,
        )

    return _result(
        True,
        "товар подходит по проверенным характеристикам",
        source_raw,
        card_raw,
        details,
    )


def is_matching_product(source_name, card_name):
    """Вернуть True, если карточка подходит, иначе False."""
    return match_product(source_name, card_name)["matches"]


if __name__ == "__main__":
    tests = [
        (
            "АЦЦ 200МГ №20 ТАБ.",
            "Ацц лонг таб шип 600мг х 20 (Salutas Pharma)",
            False,
        ),
        (
            "ТАУФОН 4% 10 МЛ КАПЛИ ГЛАЗН. /ОТИСИФАРМ/",
            "ТАУФОН 4% 10мл капли глазные Фармстандарт-УфаВИТА",
            True,
        ),
        (
            "ПЕНТАЛГИН №12 ТАБЛ.П.П.О. /ФАРМСТАНДАРТ ЛЕКСРЕДСТВА ОАО/",
            "пенталгин таб п/об пленочной n12 с дротаверином",
            True,
        ),
        (
            "ПЕНТАЛГИН №12 ТАБ.",
            "Пенталгин 12шт. таблетки покрытые пленочной оболочкой",
            True,
        ),
        (
            "ПЕНТАЛГИН №12 ТАБ.",
            "Пенталгин таблетки 10 шт.",
            False,
        ),
    ]

    for source, card, expected in tests:
        result = match_product(source, card)
        status = "OK" if result["matches"] == expected else "ОШИБКА"

        print(f"[{status}] {source}")
        print(f"  Карточка: {card}")
        print(
            f"  Совпадение: {result['matches']} "
            f"(ожидалось {expected})"
        )
        print(f"  Причина: {result['reason']}")
