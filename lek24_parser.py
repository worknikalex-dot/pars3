
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config


BASE_URL = "https://24lek.ru"
SEARCH_URL = f"{BASE_URL}/action.php"
PAGE_URL = f"{BASE_URL}/action2.php"

DEBUG_DIR = Path(__file__).resolve().parent

ARTICLE_RE = re.compile(r"^article\d+$", re.IGNORECASE)

PHARMACY_ID_RE = re.compile(
    r"""open_in_map\s*\(\s*['"]?(\d+)""",
    re.IGNORECASE,
)

PRICE_RE = re.compile(
    r"^\s*"
    r"(\d+(?:[\s\u00a0]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(?:₽|руб\.?|р\.)?\s*$",
    re.IGNORECASE,
)

INTERNET_PHARMACIES = {
    1105: {
        "domains": ("apteka.ru",),
        "names": ("аптека.ру",),
    },
    731: {
        "domains": ("aptekalegko.ru",),
        "names": ("аптека легко",),
    },
    897: {
        "domains": ("gubernskieapteki.ru",),
        "names": ("губернскиеаптеки", "губернские аптеки"),
    },
    1151: {
        "domains": ("pharmeconom.ru",),
        "names": ("фармэконом",),
    },
    344: {
        "domains": ("аптеканейрон.рф",),
        "names": ("нейрон",),
    },
    813: {
        "domains": ("таблеткитут.рф",),
        "names": ("таблеткитут", "таблетки тут"),
    },
}


def _save_debug_html(filename: str, content: str) -> None:
    """Сохраняет HTML-ответ для диагностики."""
    path = DEBUG_DIR / filename

    try:
        path.write_text(content or "", encoding="utf-8")
        print(f"[24lek][DEBUG] HTML сохранён: {path}")
    except OSError as exc:
        print(f"[24lek][DEBUG] Не удалось сохранить {path}: {exc}")


def _make_session() -> requests.Session:
    """Создаёт HTTP-сессию для запросов к сайту."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    })
    return session


def _parse_price(text: str) -> Optional[float]:
    """Преобразует текст цены в число."""
    if not text:
        return None

    cleaned = text.replace("\xa0", " ").strip()
    match = PRICE_RE.fullmatch(cleaned)

    if not match:
        return None

    number = re.sub(r"[\s\u00a0]", "", match.group(1))
    number = number.replace(",", ".")

    try:
        price = float(number)
    except (TypeError, ValueError):
        return None

    return price if price > 0 else None


def _normalize_host(host: str) -> str:
    """Нормализует домен, включая кириллические домены."""
    host = (host or "").strip().lower().rstrip(".")

    try:
        host = host.encode("ascii").decode("idna")
    except UnicodeError:
        pass

    return host


def _get_internet_pharmacy_id(element: Any) -> Optional[int]:
    """Определяет интернет-аптеку по домену или тексту ссылки."""
    if not hasattr(element, "find_all"):
        return None

    for link in element.find_all("a", href=True):
        href = unquote(str(link.get("href", ""))).strip()
        link_text = link.get_text(" ", strip=True).lower()

        try:
            host = _normalize_host(urlparse(href).hostname or "")
        except ValueError:
            host = ""

        for pharmacy_id, info in INTERNET_PHARMACIES.items():
            for domain in info["domains"]:
                normalized_domain = _normalize_host(domain)

                if (
                    host == normalized_domain
                    or host.endswith("." + normalized_domain)
                ):
                    return pharmacy_id

            if any(name in link_text for name in info["names"]):
                return pharmacy_id

    return None


def _get_pharmacy_id(element: Any) -> Optional[int]:
    """Определяет ID физической или интернет-аптеки."""
    match = PHARMACY_ID_RE.search(str(element))

    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    if hasattr(element, "find_all"):
        for link in element.find_all("a", href=True):
            match = PHARMACY_ID_RE.search(str(link.get("href", "")))

            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass

    return _get_internet_pharmacy_id(element)


def _get_card_url(card: Any) -> str:
    """Извлекает ссылку на карточку на 24lek.ru."""
    base_host = _normalize_host(urlparse(BASE_URL).hostname or "")

    for link in card.find_all("a", href=True):
        href = unquote(str(link.get("href", "")).strip())

        if not href or href.startswith(
            ("javascript:", "mailto:", "tel:", "#")
        ):
            continue

        try:
            parsed = urlparse(href)
        except ValueError:
            continue

        if parsed.scheme and parsed.netloc:
            host = _normalize_host(parsed.hostname or "")

            if host != base_host and not host.endswith("." + base_host):
                continue

        absolute_url = urljoin(BASE_URL, href)

        if urlparse(absolute_url).path:
            return absolute_url

    return ""


def _extract_items_from_html(html_text: str) -> List[Dict[str, Any]]:
    """Извлекает цены из HTML-карточек товаров."""
    soup = BeautifulSoup(html_text, "html.parser")
    items: List[Dict[str, Any]] = []

    cards = soup.find_all(
        id=lambda value: isinstance(value, str)
        and ARTICLE_RE.fullmatch(value)
    )

    if not cards:
        cards = soup.select("[id^='article']")

    seen_cards: Set[str] = set()

    for card in cards:
        card_id = str(card.get("id", ""))

        if card_id and card_id in seen_cards:
            continue

        if card_id:
            seen_cards.add(card_id)

        spans = card.find_all("span")

        if len(spans) < 3:
            continue

        price = _parse_price(spans[2].get_text(" ", strip=True))

        if price is None:
            continue

        name = spans[0].get_text(" ", strip=True)

        if not name:
            name = card.get_text(" ", strip=True)

        pharmacy_id = _get_pharmacy_id(card)

        if pharmacy_id is None:
            continue

        items.append({
            "apteka_id": pharmacy_id,
            "pharmacy_id": pharmacy_id,
            "price": price,
            "name": name,
            "source": BASE_URL,
            "url": _get_card_url(card),
        })

    return items


def _get_pagination_meta(html_text: str) -> Dict[str, Any]:
    """
    Извлекает параметры пагинации.

    num_rows может сначала присваиваться значение 0,
    а ниже — фактическое число результатов. Поэтому берём
    последнее числовое присваивание.
    """
    rows_matches = re.findall(
        r"""num_rows\s*=\s*["']?(\d+)["']?""",
        html_text,
        re.IGNORECASE,
    )

    code_matches = re.findall(
        r"""Send\s*\[\s*['"]code['"]\s*\]\s*=\s*['"]([^'"]*)['"]""",
        html_text,
        re.IGNORECASE,
    )

    total_rows = int(rows_matches[-1]) if rows_matches else 0
    code = code_matches[-1].strip() if code_matches else ""

    return {
        "total_rows": total_rows,
        "code": code,
    }


def _print_response_diagnostics(
    response: requests.Response,
    query: str,
) -> None:
    """Выводит информацию об HTTP-ответе."""
    print(
        f"[24lek] Запрос: {query!r}; "
        f"HTTP {response.status_code}; URL: {response.url}"
    )

    print(
        f"[24lek][DEBUG] Тип ответа: "
        f"{response.headers.get('Content-Type', 'не указан')}; "
        f"размер: {len(response.text)} символов"
    )

    if response.status_code >= 400:
        preview = response.text[:500].replace("\n", " ")
        print(f"[24lek] Начало ответа: {preview}")



def _print_post_request_diagnostics(
    session: requests.Session,
    url: str,
    data: Dict[str, Any],
    headers: Dict[str, str],
    offset: int,
) -> None:
    """Выводит безопасную диагностику POST без значений cookie."""
    print(
        f"[24lek][DEBUG] POST {url}; offset={offset}; "
        f"параметры: {data!r}"
    )
    print(f"[24lek][DEBUG] POST-заголовки: {headers!r}")
    cookie_names = sorted(
        {cookie.name for cookie in session.cookies}
    )
    print(
        f"[24lek][DEBUG] Cookie в сессии: {len(cookie_names)}; "
        f"имена: {cookie_names}"
    )


def search_drug_prices(
    query: str,
    needed_apteka_ids: Optional[Set[int]] = None,
    session: Optional[requests.Session] = None,
    raon_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Ищет цены на 24lek.ru, перебирая страницы через action2.php.

    Интерфейс совместим с main.py:
        search_drug_prices(query, needed_apteka_ids, session, raon_id)

    Поиск отмечается полным только если:
    - определено количество результатов;
    - все необходимые страницы успешно получены;
    - ответы пагинации имеют ожидаемый формат.
    """
    query = str(query or "").strip()

    if not query:
        print("[24lek] Пустой поисковый запрос — пропускаю.")
        return []

    own_session = session is None

    if session is None:
        session = _make_session()

    selected_raon = (
        getattr(config, "RAON_ID_24LEK", 0)
        if raon_id is None
        else raon_id
    )

    params = {
        "kray": 0,
        "city": getattr(config, "CITY_ID_24LEK", ""),
        "raon": selected_raon,
        "query": query,
    }

    all_items: List[Dict[str, Any]] = []
    seen_records: Set[Tuple[int, float, str]] = set()

    search_complete = False
    incomplete_reason = "Полнота поиска не подтверждена"

    def add_items(page_html: str) -> int:
        added = 0

        for item in _extract_items_from_html(page_html):
            pharmacy_id = item["apteka_id"]

            if (
                needed_apteka_ids is not None
                and pharmacy_id not in needed_apteka_ids
            ):
                continue

            key = (
                pharmacy_id,
                item["price"],
                item["name"].strip().casefold(),
            )

            if key in seen_records:
                continue

            seen_records.add(key)
            all_items.append(item)
            added += 1

        return added

    safe_query = re.sub(
        r"[^a-zA-Zа-яА-Я0-9_-]+",
        "_",
        query,
    )[:60].strip("_") or "query"

    try:
        try:
            response = session.get(
                SEARCH_URL,
                params=params,
                timeout=30,
            )

            _print_response_diagnostics(response, query)

            _save_debug_html(
                f"debug_24lek_first_page_{safe_query}_raon_{selected_raon}.html",
                response.text,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            incomplete_reason = f"Ошибка начального запроса: {exc}"
            print(
                f"[24lek] Ошибка поискового запроса "
                f"{query!r}, raon={selected_raon}: {exc}"
            )
            return []

        first_page_count = add_items(response.text)

        print(
            f"[24lek] {query!r}, raon={selected_raon}: "
            f"первая страница — {first_page_count} подходящих позиций."
        )

        pagination = _get_pagination_meta(response.text)
        total_rows = pagination["total_rows"]
        code = pagination["code"]

        print(
            f"[24lek][DEBUG] Метаданные: "
            f"num_rows={total_rows}, "
            f"code найден: {'да' if code else 'нет'}"
        )

        for line in response.text.splitlines():
            if "num_rows" in line.lower() or "send[" in line.lower():
                print(
                    "[24lek][DEBUG] Строка метаданных: "
                    + line.strip()[:700]
                )

        if total_rows <= 0:
            incomplete_reason = (
                "Не удалось определить фактическое количество результатов"
            )
            print(f"[24lek] {query!r}: {incomplete_reason}.")

        else:
            page_size = 50
            max_pages = max(
                1,
                int(getattr(config, "MAX_PAGES_PER_QUERY", 30)),
            )
            request_delay = max(
                0.0,
                float(getattr(config, "REQUEST_DELAY", 0.6)),
            )

            pages_needed = (total_rows + page_size - 1) // page_size
            pages_to_fetch = min(pages_needed, max_pages)
            pagination_ok = True

            if pages_needed > max_pages:
                pagination_ok = False
                incomplete_reason = (
                    f"Превышен лимит страниц: требуется {pages_needed}, "
                    f"разрешено {max_pages}"
                )

            # Если code пустой, всё равно пробуем запросить следующую
            # страницу: HTML сайта может задавать пустой code для района.
            for page_number in range(1, pages_to_fetch):
                offset = page_number * page_size

                data = {
                    "a": query,
                    "city": params["city"],
                    "raon": params["raon"],
                    "num": offset,
                    "code": code,
                }

                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": response.url,
                }

                _print_post_request_diagnostics(
                    session,
                    PAGE_URL,
                    data,
                    headers,
                    offset,
                )

                try:
                    page_response = session.post(
                        PAGE_URL,
                        data=data,
                        headers=headers,
                        timeout=30,
                    )
                    _print_response_diagnostics(page_response, query)

                    # Сохраняем тело до raise_for_status, в том числе при 4xx/5xx.
                    _save_debug_html(
                        f"debug_24lek_pagination_response_{safe_query}"
                        f"_raon_{selected_raon}_offset_{offset}.html",
                        page_response.text,
                    )
                    page_response.raise_for_status()

                except requests.RequestException as exc:
                    pagination_ok = False
                    incomplete_reason = (
                        f"Ошибка пагинации на offset={offset}: {exc}"
                    )
                    print(f"[24lek] {query!r}: {incomplete_reason}.")
                    break

                page_html = page_response.text.strip()

                if not page_html or page_html == "0":
                    pagination_ok = False
                    incomplete_reason = (
                        f"Пустой ответ пагинации на offset={offset}"
                    )
                    print(f"[24lek] {query!r}: {incomplete_reason}.")
                    break

                # action2.php должен вернуть HTML карточек.
                # Проверяем, что ответ похож на ожидаемую страницу.
                page_soup = BeautifulSoup(page_html, "html.parser")
                has_articles = bool(
                    page_soup.find(
                        id=lambda value: isinstance(value, str)
                        and ARTICLE_RE.fullmatch(value)
                    )
                )

                if not has_articles:
                    pagination_ok = False
                    incomplete_reason = (
                        f"В ответе offset={offset} не найдены карточки "
                        f"articleN; ответ сохранён для диагностики"
                    )
                    print(f"[24lek] {query!r}: {incomplete_reason}.")
                    break

                added = add_items(page_html)

                print(
                    f"[24lek] {query!r}, raon={selected_raon}: "
                    f"offset={offset}, добавлено {added}, "
                    f"всего {len(all_items)}."
                )

                if request_delay:
                    time.sleep(request_delay)

            if pagination_ok and pages_needed <= max_pages:
                search_complete = True
                incomplete_reason = (
                    f"Получены все {pages_needed} страниц "
                    f"по num_rows={total_rows}"
                )
            elif pagination_ok:
                incomplete_reason = (
                    f"Получено {pages_to_fetch} страниц из {pages_needed}"
                )

    finally:
        if own_session:
            session.close()

    status = "FOUND" if all_items else "INCOMPLETE"

    for item in all_items:
        item["search_complete"] = search_complete
        item["search_status"] = status
        item["search_reason"] = incomplete_reason

    if needed_apteka_ids is not None:
        found_ids = {item["apteka_id"] for item in all_items}
        missing_ids = sorted(needed_apteka_ids - found_ids)

        if missing_ids:
            print(
                f"[24lek] {query!r}, raon={selected_raon}: "
                f"нет подходящих ценовых записей для ID аптек: {missing_ids}"
            )

    print(
        f"[24lek] {query!r}, raon={selected_raon}: "
        f"найдено {len(all_items)} ценовых записей; "
        f"полный поиск: {'да' if search_complete else 'нет'}; "
        f"статус: {status}."
    )

    print(f"[24lek] Причина статуса поиска: {incomplete_reason}")

    return all_items
