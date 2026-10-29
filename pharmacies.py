# -*- coding: utf-8 -*-
"""
Работа с аптеками:
- загрузка apteki.json;
- сохранение района каждой аптеки;
- вычисление расстояния по формуле гаверсинусов;
- отбор аптек в заданном радиусе;
- отдельный учёт аптек без координат.
"""

import json
import math
from typing import List, Dict, Optional

import config


def load_pharmacies(path: str = None) -> List[Dict]:
    """
    Загружает все аптеки, включая записи без координат.
    Сохраняет район из apteki.json в поле district.
    """
    path = path or config.APTEKI_FILE

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Поддерживаем как список аптек, так и объект с ключом list.
    if isinstance(data, dict):
        data = data.get("list", [])

    pharmacies = []

    for item in data:
        try:
            pid = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue

        lat = _to_float_or_none(item.get("lat"))
        lon = _to_float_or_none(item.get("lon"))

        if (
            lat is None
            or lon is None
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            lat = None
            lon = None

        pharmacies.append({
            "id": pid,
            "name": str(item.get("name") or "").strip(),
            "address": str(item.get("address") or "").strip(),
            "district": str(item.get("district") or "").strip(),
            "lat": lat,
            "lon": lon,
        })

    return pharmacies


def _to_float_or_none(value) -> Optional[float]:
    """Безопасно преобразует значение координаты в число."""
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pharmacies_without_coordinates(
    pharmacies: List[Dict]
) -> List[Dict]:
    """Возвращает аптеки, для которых координаты неизвестны."""
    return [
        ph for ph in pharmacies
        if ph.get("lat") is None or ph.get("lon") is None
    ]


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Расстояние между двумя точками в метрах."""
    earth_radius_m = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    a = max(0.0, min(1.0, a))

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def pharmacies_in_radius(
    pharmacies: List[Dict],
    lat: float,
    lon: float,
    radius_m: float = None
) -> List[Dict]:
    """Возвращает аптеки в заданном радиусе."""
    radius_m = (
        radius_m
        if radius_m is not None
        else config.RADIUS_METERS
    )

    result = []

    for ph in pharmacies:
        ph_lat = ph.get("lat")
        ph_lon = ph.get("lon")

        if ph_lat is None or ph_lon is None:
            continue

        dist = haversine_m(lat, lon, ph_lat, ph_lon)

        if dist <= radius_m:
            item = dict(ph)
            item["distance_m"] = round(dist)
            result.append(item)

    result.sort(key=lambda x: x["distance_m"])
    return result


def pharmacy_header(ph: Dict) -> str:
    """Формирует заголовок столбца отчёта."""
    name = ph.get("name") or "Аптека"
    address = ph.get("address") or ""

    if ph.get("distance_m") is None:
        return f"{name} — {address} (расстояние неизвестно)"

    return f"{name} — {address} ({ph['distance_m']} м)"


if __name__ == "__main__":
    pharmacies = load_pharmacies()
    without_coords = pharmacies_without_coordinates(pharmacies)

    print(f"Всего загружено аптек: {len(pharmacies)}")
    print(f"Без координат: {len(without_coords)}")

    print("\nПроверка районов:")
    districts = sorted({
        ph["district"] or "[пусто]"
        for ph in pharmacies
    })

    for district in districts:
        count = sum(
            1 for ph in pharmacies
            if (ph["district"] or "[пусто]") == district
        )
        print(f"  {district}: {count} аптек")

    print("\nТестовые аптеки:")
    for target_id in (1091, 439, 539):
        found = next(
            (
                ph for ph in pharmacies
                if ph["id"] == target_id
            ),
            None,
        )

        if found:
            print(
                f"  {found['id']} | {found['name']} | "
                f"{found['district'] or '[район не указан]'}"
            )
        else:
            print(f"  ID {target_id}: не найден")