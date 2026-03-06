"""Geo signal helpers extracted from the GUI layer."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


def normalize_geo_token(value: Any) -> str:
    """Normalize free text to a comparable lowercase token for city matching."""
    raw = str(value or "").lower()
    if not raw:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", raw)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def resolve_geo_city(
    value: Any,
    city_coords: Mapping[str, Tuple[float, float]],
    alias_to_city: Mapping[str, str],
) -> str:
    """Resolve arbitrary location text to a known city key when possible."""
    token = normalize_geo_token(value)
    if not token:
        return ""
    if token in city_coords:
        return token
    alias = alias_to_city.get(token)
    if alias:
        return alias
    lead = token.split(" ")[0] if token else ""
    if lead in city_coords:
        return lead
    for city in city_coords.keys():
        if token.startswith(city + " ") or (" " + city + " ") in (" " + token + " "):
            return city
    return ""


def build_geo_place_counts(
    sessions: Sequence[Any],
    city_coords: Mapping[str, Tuple[float, float]],
    alias_to_city: Mapping[str, str],
    location_entity_types: Iterable[str],
) -> tuple[Dict[str, int], int]:
    """
    Aggregate mapped geo mentions from session text + location entities.

    Returns:
        (mapped_place_counts, unmapped_location_entity_mentions)
    """
    place_counts: Dict[str, int] = {}
    unmapped_mentions = 0
    location_types = {str(v).upper() for v in location_entity_types}

    for sess in sessions:
        text_token = normalize_geo_token(getattr(sess, "original_text", "") or "")
        if text_token:
            for city in city_coords.keys():
                hits = len(re.findall(rf"\b{re.escape(city)}\b", text_token))
                if hits > 0:
                    place_counts[city] = place_counts.get(city, 0) + hits

        for ent in (getattr(sess, "entities", None) or []):
            et = str(ent.get("Entity Type", ent.get("entity_type", ""))).upper()
            if et not in location_types:
                continue
            etxt = ent.get("Text", ent.get("text", ""))
            city = resolve_geo_city(etxt, city_coords, alias_to_city)
            if city:
                place_counts[city] = place_counts.get(city, 0) + 1
            elif str(etxt or "").strip():
                unmapped_mentions += 1

    return place_counts, unmapped_mentions
