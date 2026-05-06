from functools import lru_cache
import re

import spacy
from spacy.language import Language

from app.core.config import settings
from app.nlp.schemas import ExtractedEntities

COUNTRY_SET = {
    "germany",
    "france",
    "india",
    "china",
    "usa",
    "united states",
    "uk",
    "japan",
    "brazil",
    "singapore",
}

PORT_SET = {
    "hamburg",
    "rotterdam",
    "shanghai",
    "singapore port",
    "los angeles port",
    "long beach",
    "felixstowe",
}

COMMODITY_SET = {
    "crude oil",
    "wheat",
    "maize",
    "corn",
    "lithium",
    "copper",
    "steel",
    "lng",
}


@lru_cache(maxsize=1)
def get_nlp() -> Language:
    try:
        return spacy.load(settings.spacy_model)
    except Exception:  # noqa: BLE001
        return spacy.blank("en")


def _normalize(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        item = value.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_entities(text: str) -> ExtractedEntities:
    doc = get_nlp()(text)

    companies = []
    countries = []
    ports = []
    commodities = []

    for ent in doc.ents:
        if ent.label_ == "ORG":
            companies.append(ent.text)
        if ent.label_ in {"GPE", "LOC"}:
            ent_lower = ent.text.lower()
            if ent_lower in COUNTRY_SET:
                countries.append(ent.text)
            if ent_lower in PORT_SET:
                ports.append(ent.text)

    text_lower = text.lower()
    for name in COUNTRY_SET:
        if re.search(rf"\\b{re.escape(name)}\\b", text_lower):
            countries.append(name.title())
    for name in PORT_SET:
        if re.search(rf"\\b{re.escape(name)}\\b", text_lower):
            ports.append(name.title())
    for name in COMMODITY_SET:
        if re.search(rf"\\b{re.escape(name)}\\b", text_lower):
            commodities.append(name.title())

    return ExtractedEntities(
        companies=_normalize(companies),
        countries=_normalize(countries),
        ports=_normalize(ports),
        commodities=_normalize(commodities),
    )
