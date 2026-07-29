from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IncidentStatus, IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, EmergencyPublication, Incident, IncidentVersion
from app.ingestion.base import ConnectorMetrics, ConnectorRunResult
from app.ingestion.incident_reconciliation import extract_incident_hashtags, reconcile_recent_fires
from app.ingestion.spatial import geojson_geometry_to_polygon_wkt

EVENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "confinement_lift",
        ("aixeca el confinament", "levanta el confinamiento", "levantado el confinamiento", "fin do confinamento", "konfinamendua amaitu"),
    ),
    ("evacuation_lift", ("aixeca l'evacuacio", "levantada la evacuacion", "fin de la evacuacion", "ebakuazioa amaitu")),
    ("evacuation_expansion", ("amplia l'evacuacio", "amplia la evacuacion", "nuevas evacuaciones", "ebakuazioa zabaldu")),
    ("confinement_order", ("ordre de confinament", "orden de confinamiento", "confineu-vos", "confinense", "konfinatzeko agindua")),
    ("evacuation_order", ("ordre d'evacuacio", "orden de evacuacion", "evacueu", "evacuen", "ebakuatzeko agindua")),
    ("es_alert_test", ("simulacre es-alert", "simulacro es-alert", "proba es-alert", "es-alert proba")),
    ("es_alert_cancelled", ("cancel·lat es-alert", "cancelado es-alert", "es-alert cancelada", "es-alert bertan behera")),
    ("es_alert_sent", ("enviat un es-alert", "enviado un es-alert", "ha enviado es-alert", "s'ha enviat es-alert", "es-alert bidali")),
    ("es_alert_received", ("he rebut es-alert", "hem rebut es-alert", "recibido es-alert", "me ha llegado es-alert", "es-alert jaso")),
    ("es_alert_announcement", ("s'enviara un es-alert", "se enviara un es-alert", "previsto enviar es-alert", "es-alert enviarase")),
    ("plan_deactivation", ("desactiva el pla", "desactiva el plan", "plan desactivado", "plana desaktibatu")),
    ("plan_activation", ("activa el pla", "activa el plan", "plan activado", "plana aktibatu")),
    ("plan_update", ("actualitza el pla", "actualiza el plan", "actualizacion del plan", "planaren eguneraketa")),
    ("emergency_deactivation", ("desactiva l'emergencia", "desactiva la emergencia", "fin de la emergencia de interes")),
    ("emergency_activation", ("declara l'emergencia", "declara la emergencia", "emergencia de interes nacional", "larrialdi egoera")),
    ("risk_alert_update", ("alerta per risc", "alerta por riesgo", "aviso por riesgo", "alerta activada", "alerta activa")),
    ("fire_extinguished", ("extinguido", "extinguida", "extingit", "extingida", "lume extinguido", "baso-sutea itzalita")),
    (
        "firefighting_update",
        (
            "tasques d'extincio",
            "labores de extincion",
            "consolidar el perimetre",
            "consolidar el perimetro",
            "eixos de contencio",
            "lineas de contencion",
            "incendio declarado",
            "incendi declarat",
            "incendio activo",
            "incendi actiu",
            "incendio estabilizado",
            "incendi estabilitzat",
            "incendio controlado",
            "incendi controlat",
            "dotaciones de bomberos",
            "dotacions de bombers",
            "medios de extincion",
            "mitjans d'extincio",
            "medios aereos",
            "mitjans aeris",
            "trabajan en la extincion",
            "treballen en l'extincio",
            "evolucion del incendio",
            "evolucio de l'incendi",
            "perimetro del incendio",
            "perimetre de l'incendi",
            "incendi de vegetacio",
            "incendio de vegetacion",
            "incendi forestal",
            "incendio forestal",
            "foc forestal",
            "fuego forestal",
        ),
    ),
)

RISK_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "wildfire",
        (
            "incendi forestal",
            "incendio forestal",
            "incendi de vegetacio",
            "incendio de vegetacion",
            "foc forestal",
            "fuego forestal",
            "lume forestal",
            "baso-sute",
        ),
    ),
    ("flood", ("inundacio", "inundacion", "riada", "uholde", "enchente")),
    ("chemical", ("risc quimic", "riesgo quimico", "fuga quimica", "nube toxica", "arrisku kimiko")),
    ("weather", ("tempesta", "tormenta", "nevades", "nevadas", "fenomeno meteorologico", "ekaitz")),
    ("nuclear", ("nuclear", "radiologic", "radiologico", "erradiologiko")),
)

INSTRUCTION_MARKERS = (
    "confineu-vos",
    "confinense",
    "permanezca",
    "romangueu",
    "evacueu",
    "evacuen",
    "no se acerque",
    "no us acosteu",
    "siga las indicaciones",
    "seguiu les indicacions",
    "itxi ateak",
    "peche portas",
)

EXCLUDED_MUNICIPALITY_NAMES = {"agost"}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return " ".join("".join(char for char in normalized if not unicodedata.combining(char)).split())


def detect_language(text: str) -> str:
    normalized = f" {normalize_text(text)} "
    scores = {
        "ca": sum(
            token in normalized for token in (" els ", " les ", " amb ", " confinament ", " incendi ", " proteccio ", " enviat ", " confineu-vos ")
        ),
        "es": sum(token in normalized for token in (" los ", " las ", " del ", " confinamiento ", " incendio ")),
        "eu": sum(token in normalized for token in (" eta ", " sute ", " udalerri ", " ebakuazio ", " larrialdi ")),
        "gl": sum(token in normalized for token in (" unha ", " incendio ", " concello ", " evacuacion ", " emerxencia ")),
    }
    language, score = max(scores.items(), key=lambda item: item[1])
    return language if score > 0 else "und"


def classify_event(text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    matching = [(event, terms) for event, terms in EVENT_RULES if event.startswith("es_alert_")] if "es-alert" in normalized else list(EVENT_RULES)
    event_type = next((event for event, terms in matching if any(normalize_text(term) in normalized for term in terms)), "other_emergency_update")
    risk_type = next((risk for risk, terms in RISK_RULES if any(normalize_text(term) in normalized for term in terms)), "other")
    if extract_incident_hashtags(text):
        risk_type = "wildfire"
        if event_type == "other_emergency_update":
            event_type = "firefighting_update"
    if "#iiff" in normalized:
        risk_type = "wildfire"
        if event_type == "other_emergency_update":
            event_type = "firefighting_update"
    return event_type, risk_type


def action_state(event_type: str) -> str:
    if event_type.endswith("_lift") or event_type in {"plan_deactivation", "es_alert_cancelled", "fire_extinguished"}:
        return "ended"
    if event_type in {"evacuation_expansion", "plan_update"}:
        return "updated"
    return "started"


def es_alert_evidence(event_type: str, source_type: str) -> str:
    if event_type == "es_alert_announcement":
        return "announced"
    if event_type == "es_alert_sent" and source_type == "official":
        return "confirmed_sent"
    if event_type in {"es_alert_sent", "es_alert_received"}:
        return "presumed_received"
    if event_type == "es_alert_cancelled":
        return "cancelled"
    if event_type == "es_alert_test":
        return "test"
    return "not_applicable"


def extract_instructions(text: str) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+|[\r\n]+", text)
    selected = [sentence.strip() for sentence in sentences if any(marker in normalize_text(sentence) for marker in INSTRUCTION_MARKERS)]
    return " ".join(selected)[:4000] or None


def extract_es_alert_message(text: str) -> str | None:
    patterns = (
        r"(?:text(?: literal)?|missatge|mensaje)\s*(?:de l['’]es-alert|del es-alert|es-alert)?\s*[:\-]\s*[\"“](.{20,1500}?)[\"”]",
        r"ES-Alert\s*[:\-]\s*[\"“](.{20,1500}?)[\"”]",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return " ".join(match.group(1).split())
    return None


def extract_locations(text: str) -> tuple[str, ...]:
    pattern = re.compile(
        r"(?:municipi(?:o)?|terme municipal|termino municipal|concello|udalerri|urbanitzaci[oó]|urbanizaci[oó]n|poblaci[oó]n?|zona)"
        r"\s+(?:de\s+|d['’])?([A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇ][^,.;:\n()]{1,100})"
    )
    names = []
    for match in pattern.finditer(text):
        name = re.sub(r"^(?:La|El|Les|Los|Las)\s+", "", match.group(1).strip(" ,.;:()"))
        if name and name not in names:
            names.append(name)
    return tuple(names[:20])


def _geographic_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalize_text(value)).split())


def is_excluded_municipality(name: str) -> bool:
    return _geographic_text(name) in EXCLUDED_MUNICIPALITY_NAMES


def _municipality_aliases(name: str) -> tuple[str, ...]:
    aliases = [name]
    if ", " in name:
        base, suffix = name.rsplit(", ", 1)
        if normalize_text(suffix) in {"el", "la", "els", "les", "los", "las", "o", "a"}:
            aliases.append(f"{suffix} {base}")
    return tuple(aliases)


def extract_arrow_geography(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    pattern = re.compile(r"(?:✅\s*)?([^✅➡→\n:]{2,50}?)\s*(?:➡️?|→|->)\s*([^✅.\n]{2,100})")
    regions: list[str] = []
    targets: list[str] = []
    for match in pattern.finditer(text):
        region = match.group(1).strip(" ,;:-")
        target = match.group(2).strip(" ,;:-")
        if region:
            regions.append(region)
        if target:
            targets.append(target)
    return tuple(dict.fromkeys(regions)), tuple(dict.fromkeys(targets))


class MunicipalityMentionIndex:
    def __init__(self, names: Sequence[str]) -> None:
        self.by_first_token: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        self.by_compact: dict[str, str] = {}
        for name in names:
            if is_excluded_municipality(name):
                continue
            for alias in _municipality_aliases(name):
                normalized = _geographic_text(alias)
                compact = normalized.replace(" ", "")
                if len(compact) < 4:
                    continue
                self.by_first_token[normalized.split()[0]].append((name, alias, normalized))
                self.by_compact.setdefault(compact, name)

    def discover(self, text: str, hinted: Sequence[str] = ()) -> tuple[str, ...]:
        normalized_text = _geographic_text(text)
        padded_text = f" {normalized_text} "
        tokens = set(normalized_text.split())
        administrative_regions, _ = extract_arrow_geography(text)
        normalized_regions = {_geographic_text(value) for value in administrative_regions}
        hinted_names = tuple(
            dict.fromkeys(
                value.strip()
                for value in hinted
                if value.strip() and not is_excluded_municipality(value)
            )
        )
        found: list[str] = []
        normalized_found: set[str] = set()
        matches: list[tuple[int, int, str]] = []
        for token in tokens:
            for canonical, original_alias, normalized_alias in self.by_first_token.get(token, []):
                if " " not in normalized_alias and not re.search(rf"(?<!\w){re.escape(original_alias)}(?!\w)", text):
                    continue
                for match in re.finditer(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", padded_text):
                    matches.append((match.start(), match.end(), canonical))
        selected_spans: list[tuple[int, int]] = []
        for start, end, canonical in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
            if any(start < selected_end and end > selected_start for selected_start, selected_end in selected_spans):
                continue
            selected_spans.append((start, end))
            if any(_geographic_text(alias) in normalized_regions for alias in _municipality_aliases(canonical)):
                continue
            if normalize_text(canonical) not in normalized_found:
                found.append(canonical)
                normalized_found.add(normalize_text(canonical))
        if not found:
            found.extend(hinted_names)
            normalized_found.update(normalize_text(value) for value in hinted_names)
        for hashtag in extract_incident_hashtags(text):
            compact = _geographic_text(hashtag[3:]).replace(" ", "")
            hashtag_location = self.by_compact.get(compact)
            if hashtag_location and normalize_text(hashtag_location) not in normalized_found:
                found.append(hashtag_location)
                normalized_found.add(normalize_text(hashtag_location))
        return tuple(found[:20])


def publication_hash(url: str, text: str) -> str:
    canonical = f"{url.split('#', 1)[0].rstrip('/')}|{normalize_text(text)}"
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class SourceSpec:
    name: str
    authority: str
    url: str
    source_type: str
    format: str
    enabled: bool = True
    reliability: float = 1.0


@dataclass(frozen=True)
class RawPublication:
    external_id: str
    title: str
    text: str
    url: str
    published_at: datetime
    source: SourceSpec
    locations: tuple[str, ...] = ()
    geometry: dict[str, Any] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.current_href = urljoin(self.base_url, href)
                self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href:
            text = " ".join(" ".join(self.current_text).split())
            if len(text) >= 20:
                self.items.append((self.current_href, text))
            self.current_href = None


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def html_text(raw: str) -> str:
    parser = _TextParser()
    parser.feed(raw)
    return " ".join(parser.parts)


def extract_published_at(text: str, fallback: datetime) -> datetime:
    match = re.search(r"\b([0-3]?\d)[/-]([01]?\d)[/-](20\d{2}|\d{2})\b", text)
    if not match:
        return fallback
    day, month, raw_year = (int(value) for value in match.groups())
    year = raw_year + 2000 if raw_year < 100 else raw_year
    try:
        return datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return fallback


def _parse_datetime(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return fallback
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def parse_feed(raw: str, source: SourceSpec, fetched_at: datetime) -> list[RawPublication]:
    root = ET.fromstring(raw)
    records: list[RawPublication] = []
    for node in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):

        def value(*names: str, current_node: ET.Element = node) -> str:
            for name in names:
                child = current_node.find(name)
                if child is not None and child.text:
                    return child.text.strip()
            return ""

        title = value("title", "{http://www.w3.org/2005/Atom}title")
        description = value("description", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content")
        link = value("link")
        atom_link = node.find("{http://www.w3.org/2005/Atom}link")
        if not link and atom_link is not None:
            link = atom_link.attrib.get("href", "")
        guid = value("guid", "id", "{http://www.w3.org/2005/Atom}id") or link
        published = value("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated")
        text = re.sub(r"<[^>]+>", " ", description)
        records.append(
            RawPublication(
                guid or publication_hash(link, title),
                title,
                " ".join(text.split()),
                link or source.url,
                _parse_datetime(published, fetched_at),
                source,
            )
        )
    return records


def parse_nitter_feed(raw: str, account: dict[str, str], base_url: str, fetched_at: datetime) -> list[RawPublication]:
    handle = account["handle"]
    source_type = account.get("source_type", "official")
    reliability = float(account.get("reliability", "0.95"))
    source = SourceSpec(
        name=f"X @{handle} via Nitter",
        authority=account["authority"],
        url=f"{base_url.rstrip('/')}/{handle}",
        source_type=source_type,
        format="nitter_rss",
        reliability=reliability,
    )
    records: list[RawPublication] = []
    for record in parse_feed(raw, source, fetched_at):
        if normalize_text(record.title).startswith("rt by @"):
            continue
        canonical_x_url = re.sub(
            rf"^{re.escape(base_url.rstrip('/'))}/{re.escape(handle)}/status/",
            f"https://x.com/{handle}/status/",
            record.url,
            flags=re.IGNORECASE,
        ).split("#", 1)[0]
        records.append(
            RawPublication(
                external_id=f"nitter:{handle}:{record.external_id}",
                title=record.title,
                text=record.title,
                url=record.url.split("#", 1)[0],
                published_at=record.published_at,
                source=source,
                locations=extract_locations(record.title),
                metadata={"gateway": "nitter", "x_handle": handle, "canonical_x_url": canonical_x_url},
            )
        )
    return records


def parse_html(raw: str, source: SourceSpec, fetched_at: datetime) -> list[RawPublication]:
    parser = _LinkParser(source.url)
    parser.feed(raw)
    return [RawPublication(publication_hash(url, title), title, title, url, fetched_at, source) for url, title in parser.items]


class OfficialBoundaryResolver:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.endpoint = get_settings().osint_ign_municipalities_url
        self._mention_index: MunicipalityMentionIndex | None = None
        self._feature_cache: dict[str, dict[str, Any] | None] = {}

    async def discover(self, text: str, hinted: Sequence[str] = ()) -> tuple[str, ...]:
        if self._mention_index is None:
            self._mention_index = MunicipalityMentionIndex(await self._municipality_names())
        return self._mention_index.discover(text, hinted)

    async def _municipality_names(self) -> list[str]:
        names: list[str] = []
        offset = 0
        while offset < 12_000:
            response = await self.client.get(
                self.endpoint,
                params={
                    "where": "NATLEVNAME='Municipio'",
                    "outFields": "OBJECTID,NAMEUNIT",
                    "returnGeometry": "false",
                    "orderByFields": "OBJECTID",
                    "resultOffset": str(offset),
                    "resultRecordCount": "2000",
                    "f": "geojson",
                },
            )
            response.raise_for_status()
            features = response.json().get("features", [])
            page_names = [feature.get("properties", {}).get("NAMEUNIT") for feature in features]
            names.extend(name for name in page_names if isinstance(name, str) and name)
            if len(features) < 2_000:
                break
            offset += len(features)
        return list(dict.fromkeys(names))

    async def _feature(self, name: str) -> dict[str, Any] | None:
        if name in self._feature_cache:
            return self._feature_cache[name]
        escaped = name.replace("'", "''")
        response = await self.client.get(
            self.endpoint,
            params={
                "where": f"UPPER(NAMEUNIT)=UPPER('{escaped}') AND NATLEVNAME='Municipio'",
                "outFields": "OBJECTID,codine,NATCODE,NAMEUNIT,NATLEVNAME",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultRecordCount": "2",
            },
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        feature = features[0] if len(features) == 1 and isinstance(features[0], dict) else None
        self._feature_cache[name] = feature
        return feature

    async def resolve(self, names: tuple[str, ...]) -> tuple[str | None, list[dict[str, object]], str, str]:
        names = tuple(name for name in names if not is_excluded_municipality(name))
        if not names:
            return None, [], "none", "unknown"
        geometries: list[str] = []
        locations: list[dict[str, object]] = []
        for name in names:
            feature = await self._feature(name.strip())
            if feature is None:
                locations.append({"name": name, "matched": False})
                continue
            geometry = feature.get("geometry")
            wkt = geojson_geometry_to_polygon_wkt(geometry) if isinstance(geometry, dict) else None
            if wkt:
                geometries.append(wkt)
            properties = feature.get("properties", {})
            locations.append(
                {
                    "name": properties.get("NAMEUNIT", name),
                    "kind": "municipality",
                    "official": True,
                    "ine_code": properties.get("codine"),
                    "national_code": properties.get("NATCODE"),
                }
            )
        if not geometries:
            return None, locations, "none", "toponym_unresolved"
        geometry_wkt = geometries[0] if len(geometries) == 1 else f"GEOMETRYCOLLECTION({','.join(geometries)})"
        return geometry_wkt, locations, "ign_official_boundaries_text_mentions", "municipality"


class EmergencyOsintService:
    def __init__(self, session: AsyncSession, client: httpx.AsyncClient | None = None) -> None:
        self.session = session
        self.client = client or httpx.AsyncClient(timeout=get_settings().osint_timeout_seconds)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def ingest(self, records: list[RawPublication]) -> ConnectorMetrics:
        metrics = ConnectorMetrics(received=len(records))
        resolver = OfficialBoundaryResolver(self.client)
        for raw in records:
            title_event, title_risk = classify_event(raw.title)
            body_event, body_risk = classify_event(raw.text)
            body_high_signal = body_event not in {"other_emergency_update", "risk_alert_update"}
            event_type = title_event if title_event != "other_emergency_update" else body_event if body_high_signal else "other_emergency_update"
            risk_type = title_risk if title_risk != "other" else body_risk if event_type != "other_emergency_update" else "other"
            if event_type == "other_emergency_update":
                metrics.discarded += 1
                continue
            deduplication_url = str(raw.metadata.get("canonical_x_url", raw.url))
            digest = publication_hash(deduplication_url, raw.text or raw.title)
            administrative_regions, arrow_targets = extract_arrow_geography(f"{raw.title}. {raw.text}")
            if administrative_regions:
                raw.metadata["administrative_context_locations"] = list(administrative_regions)
            if len(arrow_targets) > 1:
                raw.metadata["multi_incident_summary"] = True
                if risk_type == "wildfire":
                    event_type = "firefighting_update"
            raw_locations = raw.locations or extract_locations(f"{raw.title}. {raw.text}")
            discovery_succeeded = True
            try:
                raw_locations = await resolver.discover(f"{raw.title}. {raw.text}", raw_locations)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                discovery_succeeded = False
                metrics.errors.append(f"toponym-discovery:{raw.external_id}:{type(exc).__name__}")
            geometry = geojson_geometry_to_polygon_wkt(raw.geometry) if raw.geometry else None
            locations = [{"name": name, "matched": False} for name in raw_locations]
            method, precision = ("source_geometry", "source_reported") if geometry else ("none", "unknown")
            if not geometry and raw_locations:
                try:
                    geometry, locations, method, precision = await resolver.resolve(raw_locations)
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    metrics.errors.append(f"geocoding:{raw.external_id}:{type(exc).__name__}")
            rank = {"official": 1, "reliable_media": 2, "multiple_witnesses": 3, "individual": 4}.get(raw.source.source_type, 4)
            confidence = {1: 0.96, 2: 0.78, 3: 0.62, 4: 0.30}[rank] * raw.source.reliability
            existing = await self.session.scalar(select(EmergencyPublication).where(EmergencyPublication.deduplication_hash == digest))
            if existing:
                if raw.metadata.get("gateway") == "nitter":
                    existing.url = raw.url
                existing.raw_metadata = {**existing.raw_metadata, **raw.metadata}
                existing_location_names = {str(item.get("name")) for item in existing.locations if isinstance(item, dict)}
                resolved_location_names = {str(item.get("name")) for item in locations if isinstance(item, dict)}
                if discovery_succeeded and resolved_location_names != existing_location_names:
                    existing.locations = locations
                if discovery_succeeded and (existing.geometry is None or existing.geometry_inference_method.startswith("ign_")):
                    existing.geometry = geometry
                    existing.geometry_inference_method = method
                    existing.spatial_precision = precision
                existing.event_type = event_type
                existing.risk_type = risk_type
                existing.action_state = action_state(event_type)
                current_incident = await self.session.get(Incident, existing.incident_id) if existing.incident_id else None
                if (
                    raw.metadata.get("multi_incident_summary")
                    or current_incident is None
                    or current_incident.original_metadata.get("canonical_source") != "EFFIS"
                ):
                    source = await self._source(raw.source)
                    incident = await self._find_or_create_incident(
                        raw,
                        source,
                        event_type,
                        risk_type,
                        geometry,
                        locations,
                        confidence,
                        allow_canonical=not bool(raw.metadata.get("multi_incident_summary")),
                    )
                    existing.incident_id = incident.id
                    await self._apply_transition(incident, existing)
                    location_label = next((str(item.get("name")) for item in locations if item.get("name")), "Espanya")
                    if (
                        incident.original_metadata.get("canonical_source") != "EFFIS"
                        and not incident.original_metadata.get("multi_incident_summary")
                    ):
                        incident.title = f"{risk_type.replace('_', ' ').title()} - {location_label}"
                metrics.duplicated += 1
                continue
            source = await self._source(raw.source)
            review_status = "accepted" if rank == 1 and event_type != "es_alert_received" else "pending"
            incident = await self._find_or_create_incident(
                raw,
                source,
                event_type,
                risk_type,
                geometry,
                locations,
                confidence,
                allow_canonical=not bool(raw.metadata.get("multi_incident_summary")),
            )
            publication = EmergencyPublication(
                source_id=source.id,
                incident_id=incident.id,
                external_id=raw.external_id[:255],
                deduplication_hash=digest,
                url=raw.url,
                source_type=raw.source.source_type,
                authority=raw.source.authority,
                language=detect_language(raw.text),
                title=raw.title[:500],
                original_text=raw.text,
                event_type=event_type,
                risk_type=risk_type,
                action_state=action_state(event_type),
                es_alert_status=es_alert_evidence(event_type, raw.source.source_type),
                published_at=raw.published_at,
                starts_at=raw.starts_at,
                ends_at=raw.ends_at,
                instructions=extract_instructions(raw.text),
                es_alert_message=extract_es_alert_message(raw.text),
                locations=locations,
                geometry=geometry,
                geometry_inference_method=method,
                spatial_precision=precision,
                evidence_rank=rank,
                confidence=min(1.0, confidence),
                review_status=review_status,
                raw_metadata=raw.metadata,
            )
            self.session.add(publication)
            await self.session.flush()
            if raw.source.source_type == "individual":
                witnesses = await self.session.scalar(
                    select(func.count(func.distinct(EmergencyPublication.authority))).where(
                        EmergencyPublication.incident_id == incident.id,
                        EmergencyPublication.source_type.in_(("individual", "multiple_witnesses")),
                    )
                )
                if int(witnesses or 0) >= 3:
                    publication.source_type = "multiple_witnesses"
                    publication.evidence_rank = 3
                    publication.confidence = 0.62
            await self._apply_transition(incident, publication)
            metrics.persisted += 1
        await self.session.flush()
        await reconcile_recent_fires(self.session)
        await self.session.commit()
        return metrics

    async def _source(self, spec: SourceSpec) -> DataSource:
        source = await self.session.scalar(select(DataSource).where(DataSource.name == spec.name))
        if source:
            return source
        provenance = ProvenanceType.OFFICIAL if spec.source_type == "official" else ProvenanceType.OBSERVED
        source = DataSource(
            name=spec.name,
            source_type=provenance,
            authority=spec.authority,
            base_url=spec.url,
            attribution=spec.authority,
            update_frequency="5 minutes",
            reliability_score=spec.reliability,
            source_metadata={"osint": True, "format": spec.format},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _find_or_create_incident(
        self,
        raw: RawPublication,
        source: DataSource,
        event_type: str,
        risk_type: str,
        geometry: str | None,
        locations: list[dict[str, object]],
        confidence: float,
        *,
        allow_canonical: bool = True,
    ) -> Incident:
        cutoff = raw.published_at - timedelta(days=7)
        location_keys = {normalize_text(str(item.get("name", ""))) for item in locations}
        if raw.metadata.get("multi_incident_summary"):
            summary_external_id = f"osint-summary:{raw.external_id}"[:255]
            summary = await self.session.scalar(select(Incident).where(Incident.external_id == summary_external_id))
            if summary is not None:
                return summary
            location_names = [str(item.get("name")) for item in locations if item.get("name")]
            summary = Incident(
                title=f"Resum d'incendis - {' / '.join(location_names) or 'Espanya'}",
                status=IncidentStatus.ACTIVE,
                summary=raw.title,
                geometry=geometry,
                source_id=source.id,
                external_id=summary_external_id,
                provenance=ProvenanceType.OFFICIAL if raw.source.source_type == "official" else ProvenanceType.OBSERVED,
                observed_at=raw.published_at,
                published_at=raw.published_at,
                received_at=datetime.now(UTC),
                verification_status=VerificationStatus.VERIFIED if raw.source.source_type == "official" else VerificationStatus.PENDING,
                confidence=min(1.0, confidence),
                original_metadata={
                    "osint": True,
                    "risk_type": risk_type,
                    "affected_locations": location_names,
                    "event_type": event_type,
                    "multi_incident_summary": True,
                },
            )
            self.session.add(summary)
            await self.session.flush()
            return summary
        statement = select(Incident).where(
            Incident.observed_at >= cutoff,
            func.coalesce(Incident.original_metadata["risk_type"].astext, "other") == risk_type,
            func.coalesce(Incident.original_metadata["multi_incident_summary"].as_boolean(), False).is_(False),
        )
        if not allow_canonical:
            statement = statement.where(func.coalesce(Incident.original_metadata["canonical_source"].astext, "") != "EFFIS")
        candidates = ((await self.session.execute(statement.order_by(desc(Incident.observed_at)).limit(50))).scalars().all())
        for candidate in candidates:
            metadata = candidate.original_metadata if isinstance(candidate.original_metadata, dict) else {}
            raw_candidate_locations = metadata.get("affected_locations")
            candidate_locations = (
                {normalize_text(str(value)) for value in raw_candidate_locations} if isinstance(raw_candidate_locations, list) else set()
            )
            if location_keys and candidate_locations.intersection(location_keys):
                return candidate
            if not location_keys:
                ignored = {"alert", "emergencia", "emergency", "actualitzacio", "actualizacion", "incendi", "incendio"}
                raw_tokens = {token for token in normalize_text(raw.title).split() if len(token) > 4 and token not in ignored}
                candidate_tokens = {
                    token for token in normalize_text(candidate.summary or candidate.title).split() if len(token) > 4 and token not in ignored
                }
                if len(raw_tokens.intersection(candidate_tokens)) >= 2:
                    return candidate
        location_label = next(iter(location_keys), "espanya").title()
        incident = Incident(
            title=f"{risk_type.replace('_', ' ').title()} - {location_label}",
            status=IncidentStatus.ACTIVE,
            summary=raw.title,
            geometry=geometry,
            source_id=source.id,
            external_id=f"osint:{raw.external_id}",
            provenance=ProvenanceType.OFFICIAL if raw.source.source_type == "official" else ProvenanceType.OBSERVED,
            observed_at=raw.published_at,
            published_at=raw.published_at,
            received_at=datetime.now(UTC),
            verification_status=VerificationStatus.VERIFIED if raw.source.source_type == "official" else VerificationStatus.PENDING,
            confidence=min(1.0, confidence),
            original_metadata={
                "osint": True,
                "risk_type": risk_type,
                "affected_locations": [item.get("name") for item in locations],
                "event_type": event_type,
            },
        )
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def _apply_transition(self, incident: Incident, publication: EmergencyPublication) -> None:
        ending = publication.action_state == "ended"
        incident.status = IncidentStatus.CONTROLLED if ending else IncidentStatus.ACTIVE
        incident.summary = publication.title
        incident.observed_at = max(incident.observed_at or publication.published_at, publication.published_at)
        if incident.geometry is None and publication.geometry is not None:
            incident.geometry = publication.geometry
        metadata = dict(incident.original_metadata)
        metadata.update(
            {
                "event_type": publication.event_type,
                "risk_type": publication.risk_type,
                "es_alert_status": publication.es_alert_status,
                "instructions": publication.instructions,
                "es_alert_message": publication.es_alert_message,
                "affected_locations": [item.get("name") for item in publication.locations],
            }
        )
        raw_evidence_sources = metadata.get("evidence_sources")
        evidence_sources = list(raw_evidence_sources) if isinstance(raw_evidence_sources, list) else []
        source_entry = {
            "authority": publication.authority,
            "url": publication.url,
            "source_type": publication.source_type,
            "confidence": publication.confidence,
        }
        if not any(isinstance(item, dict) and item.get("url") == publication.url for item in evidence_sources):
            evidence_sources.append(source_entry)
        metadata["evidence_sources"] = evidence_sources
        if ending:
            metadata["ended_at"] = publication.ends_at.isoformat() if publication.ends_at else publication.published_at.isoformat()
        elif publication.event_type in {"confinement_order", "evacuation_order"}:
            metadata.setdefault("restriction_started_at", (publication.starts_at or publication.published_at).isoformat())
        incident.original_metadata = metadata
        incident.confidence = max(incident.confidence or 0.0, publication.confidence)
        incident.version += 1
        self.session.add(
            IncidentVersion(
                incident_id=incident.id,
                version=incident.version,
                status=incident.status,
                title=incident.title,
                snapshot={"publication_id": str(publication.id), **metadata},
                change_reason=publication.event_type,
            )
        )


class EmergencyOsintConnector:
    name = "emergency_osint"

    def __init__(self, session: AsyncSession, client: httpx.AsyncClient | None = None) -> None:
        self.session = session
        self.client = client

    def source_specs(self) -> list[SourceSpec]:
        path = Path(__file__).with_name("osint_sources.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [SourceSpec(**item) for item in payload if item.get("enabled", True)]

    async def execute(self) -> ConnectorRunResult:
        started = datetime.now(UTC)
        client = self.client or httpx.AsyncClient(timeout=get_settings().osint_timeout_seconds, follow_redirects=True)
        records: list[RawPublication] = []
        errors: list[str] = []
        monitor_source = await self.session.scalar(select(DataSource).where(DataSource.name == "Emergency OSINT monitor"))
        if monitor_source is None:
            monitor_source = DataSource(
                name="Emergency OSINT monitor",
                source_type=ProvenanceType.OBSERVED,
                authority="Public-source aggregation",
                update_frequency="5 minutes",
                reliability_score=0.7,
                source_metadata={"osint": True, "aggregator": True},
            )
            self.session.add(monitor_source)
            await self.session.flush()
        run = DataIngestionRun(
            source_id=monitor_source.id, connector_name=self.name, status=IngestionRunStatus.STARTED, started_at=started, error_summary={}, metrics={}
        )
        self.session.add(run)
        await self.session.commit()
        try:
            source_results = await asyncio.gather(*(self._fetch_source(client, source) for source in self.source_specs()))
            for parsed, error in source_results:
                records.extend(parsed)
                if error:
                    errors.append(error)
            nitter_records, nitter_errors = await self._fetch_nitter(client)
            records.extend(nitter_records)
            errors.extend(nitter_errors)
            try:
                records.extend(await self._fetch_x(client))
            except httpx.HTTPError as exc:
                errors.append(f"X API:{type(exc).__name__}")
            service = EmergencyOsintService(self.session, client)
            metrics = await service.ingest(records)
            metrics.errors.extend(errors)
            status = "failed" if errors and not records else "partial" if errors else "completed"
            run.status = IngestionRunStatus(status)
            run.finished_at = datetime.now(UTC)
            run.received_count = metrics.received
            run.discarded_count = metrics.discarded
            run.duplicate_count = metrics.duplicated
            run.persisted_count = metrics.persisted
            run.error_summary = {"errors": metrics.errors}
            run.metrics = {"sources": len(self.source_specs()) + bool(get_settings().x_bearer_token)}
            await self.session.commit()
            return ConnectorRunResult(self.name, status, started, datetime.now(UTC), metrics)
        except Exception as exc:
            await self.session.rollback()
            run.status = IngestionRunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.error_summary = {"errors": [f"{type(exc).__name__}: {exc}"]}
            await self.session.commit()
            raise
        finally:
            if self.client is None:
                await client.aclose()

    async def _fetch_source(self, client: httpx.AsyncClient, source: SourceSpec) -> tuple[list[RawPublication], str | None]:
        try:
            response = await client.get(source.url, headers={"User-Agent": "WildfireIntelligenceOSINT/0.1"})
            response.raise_for_status()
            parser = parse_feed if source.format in {"rss", "atom"} else parse_html
            parsed = parser(response.text, source, datetime.now(UTC))
            if source.format == "html":
                parsed = await self._enrich_html_records(client, parsed)
            return parsed, None
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            return [], f"{source.name}:{type(exc).__name__}"

    async def _fetch_nitter(self, client: httpx.AsyncClient) -> tuple[list[RawPublication], list[str]]:
        settings = get_settings()
        if not settings.osint_nitter_enabled:
            return [], []
        path = Path(__file__).with_name("osint_x_accounts.json")
        accounts = json.loads(path.read_text(encoding="utf-8"))

        async def fetch_account(account: dict[str, str]) -> tuple[list[RawPublication], str | None]:
            handle = account["handle"]
            url = f"{settings.osint_nitter_base_url.rstrip('/')}/{handle}/rss"
            try:
                response = await client.get(url, headers={"User-Agent": "WildfireIntelligenceOSINT/0.1"})
                response.raise_for_status()
                return parse_nitter_feed(response.text, account, settings.osint_nitter_base_url, datetime.now(UTC)), None
            except (httpx.HTTPError, ET.ParseError, ValueError, KeyError) as exc:
                return [], f"Nitter @{handle}:{type(exc).__name__}"

        results = await asyncio.gather(*(fetch_account(account) for account in accounts))
        records = [record for account_records, _ in results for record in account_records]
        errors = [error for _, error in results if error]
        return records, errors

    async def _enrich_html_records(self, client: httpx.AsyncClient, records: list[RawPublication]) -> list[RawPublication]:
        keywords = ("es-alert", "emerg", "incendi", "evac", "confin", "inund", "112", "proteccion civil", "proteccio civil")
        candidates = [record for record in records if any(keyword in normalize_text(record.title) for keyword in keywords)][:5]
        enriched: list[RawPublication] = []
        for record in candidates:
            try:
                response = await client.get(record.url, headers={"User-Agent": "WildfireIntelligenceOSINT/0.1"})
                response.raise_for_status()
                text = html_text(response.text)[:100_000]
                enriched.append(
                    RawPublication(
                        record.external_id,
                        record.title,
                        text or record.text,
                        record.url,
                        extract_published_at(text, record.published_at),
                        record.source,
                        extract_locations(text),
                        metadata={"collector": "official_html"},
                    )
                )
            except httpx.HTTPError:
                enriched.append(record)
        return enriched

    async def _fetch_x(self, client: httpx.AsyncClient) -> list[RawPublication]:
        settings = get_settings()
        if not settings.x_bearer_token or not settings.osint_x_query:
            return []
        response = await client.get(
            "https://api.x.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
            params={
                "query": settings.osint_x_query,
                "max_results": "100",
                "tweet.fields": "created_at,lang,author_id",
                "expansions": "author_id",
                "user.fields": "name,username,verified",
            },
        )
        response.raise_for_status()
        payload = response.json()
        users = {user["id"]: user for user in payload.get("includes", {}).get("users", [])}
        records = []
        for post in payload.get("data", []):
            user = users.get(post.get("author_id"), {})
            username = user.get("username", "unknown")
            official = username.lower() in {value.lower() for value in settings.osint_x_official_accounts.split(",") if value.strip()}
            source = SourceSpec(
                f"X @{username}",
                user.get("name", username),
                f"https://x.com/{username}",
                "official" if official else "individual",
                "x",
                reliability=0.95 if official else 1.0,
            )
            url = f"https://x.com/{username}/status/{post['id']}"
            records.append(
                RawPublication(
                    post["id"],
                    post["text"][:500],
                    post["text"],
                    url,
                    _parse_datetime(post.get("created_at"), datetime.now(UTC)),
                    source,
                    metadata={"x_author_id": post.get("author_id"), "x_verified": user.get("verified", False)},
                )
            )
        return records
