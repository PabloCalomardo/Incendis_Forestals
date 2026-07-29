from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from math import pi, sqrt
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.enums import IncidentStatus
from app.domain.models import (
    EmergencyPublication,
    EvacuationZone,
    FireDetection,
    FirePerimeter,
    Incident,
    OfficialNotice,
    RestrictionZone,
    RiskForecast,
    RoadIncident,
    SmokeForecast,
)

HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\wÀ-ÿ-]{3,80})", re.UNICODE)
MATCH_WINDOW = timedelta(days=14)
FIRMS_DISTANCE_METERS = 5_000
EFFIS_GROUP_MAX_DISTANCE_METERS = 50_000


def effis_area_neighborhood_meters(first_area_hectares: float | None, second_area_hectares: float | None) -> float:
    combined_area_m2 = max(0.0, float(first_area_hectares or 0) + float(second_area_hectares or 0)) * 10_000
    equivalent_radius = sqrt(combined_area_m2 / pi) if combined_area_m2 else 0.0
    return min(float(EFFIS_GROUP_MAX_DISTANCE_METERS), max(1_500.0, 1_000.0 + 2.25 * equivalent_radius))


def effis_group_reasons(
    *,
    distance_meters: float,
    time_delta: timedelta,
    first_hashtags: set[str],
    second_hashtags: set[str],
    first_commune: str | None,
    second_commune: str | None,
    first_province: str | None,
    second_province: str | None,
    first_area_hectares: float | None = None,
    second_area_hectares: float | None = None,
) -> list[str]:
    if time_delta > timedelta(days=7) or distance_meters > EFFIS_GROUP_MAX_DISTANCE_METERS:
        return []
    reasons: list[str] = []
    shared_hashtag = {value.casefold() for value in first_hashtags} & {value.casefold() for value in second_hashtags}
    same_commune = bool(first_commune and second_commune and normalize_match_text(first_commune) == normalize_match_text(second_commune))
    same_province = bool(first_province and second_province and normalize_match_text(first_province) == normalize_match_text(second_province))
    area_neighborhood = effis_area_neighborhood_meters(first_area_hectares, second_area_hectares)
    if shared_hashtag:
        reasons.append("shared_hashtag")
    if same_commune:
        reasons.append("same_commune")
    if same_province:
        reasons.append("same_province")
    if distance_meters <= 1_500 and same_province and time_delta <= timedelta(days=2):
        reasons.extend(("adjacent_1500m", "simultaneous_2d"))
    elif distance_meters <= max(8_000, area_neighborhood) and same_commune and time_delta <= timedelta(days=5):
        reasons.extend(("nearby_8km", "simultaneous_3d"))
    elif distance_meters <= EFFIS_GROUP_MAX_DISTANCE_METERS and shared_hashtag:
        reasons.extend(("nearby_25km", "simultaneous_7d"))
    elif distance_meters <= area_neighborhood and same_province and time_delta <= timedelta(days=7):
        reasons.extend(("area_scaled_neighborhood", f"area_threshold_{round(area_neighborhood)}m", "simultaneous_7d"))
    else:
        return []
    return reasons


def normalize_match_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).split())


def extract_incident_hashtags(text: str) -> set[str]:
    hashtags = {f"#{match.group(1)}" for match in HASHTAG_PATTERN.finditer(text)}
    return {
        hashtag for hashtag in hashtags if hashtag.casefold().startswith("#if") and not hashtag.casefold().startswith("#info") and len(hashtag) > 5
    }


def merge_case_insensitive_values(*groups: Sequence[str]) -> list[str]:
    merged: dict[str, str] = {}
    for group in groups:
        for value in group:
            if value:
                merged.setdefault(value.casefold(), value)
    return sorted(merged.values(), key=str.casefold)


def firms_perimeter_match(perimeter_geometry: object) -> Any:
    geography = Geography(srid=4326)
    return func.ST_DWithin(
        cast(FireDetection.geometry, geography),
        cast(perimeter_geometry, geography),
        FIRMS_DISTANCE_METERS,
    )


def score_fire_match(
    *,
    commune: str | None,
    province: str | None,
    canonical_hashtags: set[str],
    canonical_locations: set[str],
    candidate_text: str,
    candidate_locations: set[str],
    candidate_hashtags: set[str],
    spatial_match: bool,
    time_delta: timedelta,
    spatial_distance_meters: float | None = None,
) -> tuple[int, list[str]]:
    normalized_text = normalize_match_text(candidate_text)
    normalized_locations = {normalize_match_text(value) for value in candidate_locations}
    score = 0
    reasons: list[str] = []

    hashtag_overlap = {value.casefold() for value in canonical_hashtags} & {value.casefold() for value in candidate_hashtags}
    if hashtag_overlap:
        score += 100
        reasons.append("shared_hashtag")
    if candidate_hashtags:
        reasons.append("fire_hashtag")

    normalized_canonical_locations = {normalize_match_text(value) for value in canonical_locations}
    if normalized_canonical_locations & normalized_locations:
        score += 70
        reasons.append("shared_location")

    normalized_commune = normalize_match_text(commune or "")
    if normalized_commune and normalized_commune in normalized_locations:
        score += 70
        reasons.append("commune_location")
    elif len(normalized_commune) >= 5 and normalized_commune in normalized_text:
        score += 45
        reasons.append("commune_text")

    if spatial_match:
        score += 50
        reasons.append("spatial_intersection")
    elif spatial_distance_meters is not None and spatial_distance_meters <= 5_000:
        score += 45
        reasons.append("spatial_nearby_5km")
    elif spatial_distance_meters is not None and spatial_distance_meters <= 15_000:
        score += 40
        reasons.append("spatial_nearby_15km")

    normalized_province = normalize_match_text(province or "")
    if normalized_province and normalized_province in normalized_text:
        score += 10
        reasons.append("province")

    if time_delta <= timedelta(days=3):
        score += 20
        reasons.append("time_3d")
    elif time_delta <= MATCH_WINDOW:
        score += 10
        reasons.append("time_14d")
    return score, reasons


def is_fire_match(score: int, reasons: Sequence[str]) -> bool:
    reason_set = set(reasons)
    strong_evidence = {"shared_hashtag", "shared_location", "commune_location", "spatial_intersection", "spatial_nearby_5km"}
    named_match = "commune_text" in reason_set and bool({"spatial_intersection", "fire_hashtag"} & reason_set)
    nearby_named_fire = "spatial_nearby_15km" in reason_set and "fire_hashtag" in reason_set
    return score >= 60 and (bool(strong_evidence & reason_set) or named_match or nearby_named_fire)


class CanonicalFireReconciler:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reconcile_recent(self) -> dict[str, int]:
        cutoff = datetime.now(UTC) - MATCH_WINDOW
        perimeters = (
            (
                await self.session.execute(
                    select(FirePerimeter)
                    .where(
                        FirePerimeter.perimeter_kind == "effis_official_burnt_area",
                        FirePerimeter.observed_at >= cutoff,
                    )
                    .order_by(FirePerimeter.observed_at.desc())
                )
            )
            .scalars()
            .all()
        )
        rows: list[tuple[FirePerimeter, Incident]] = []
        for perimeter in perimeters:
            canonical = await self.session.scalar(select(Incident).where(Incident.external_id == f"{perimeter.external_id}:incident"))
            if canonical is None:
                continue
            perimeter.incident_id = canonical.id
            metadata = self._metadata(canonical)
            for key in (
                "merged_into",
                "hidden",
                "reconciliation_score",
                "reconciliation_reasons",
                "merged_incident_ids",
                "reconciliation_matches",
                "hashtags",
                "primary_hashtag",
                "affected_locations",
                "evidence_sources",
            ):
                metadata.pop(key, None)
            metadata.update({"canonical_fire": True, "canonical_source": "EFFIS"})
            canonical.original_metadata = metadata
            rows.append((perimeter, canonical))
        await self.session.flush()

        metrics = {"canonical_incidents": len(rows), "merged_incidents": 0, "linked_detections": 0}
        canonical_ids = [canonical.id for _, canonical in rows]
        if canonical_ids:
            await self.session.execute(
                update(EmergencyPublication).where(EmergencyPublication.incident_id.in_(canonical_ids)).values(incident_id=None)
            )
            await self.session.flush()
        await self._assign_publications(rows, cutoff, only_unassigned=True)
        for perimeter, canonical in rows:
            await self._refresh_canonical(canonical, perimeter)
        rows, merged_perimeters = await self._group_adjacent_effis(rows)
        metrics["merged_incidents"] += merged_perimeters
        metrics["canonical_incidents"] = len({canonical.id for _, canonical in rows})
        await self._assign_publications(rows, cutoff, only_unassigned=False)
        grouped_rows: dict[object, tuple[Incident, list[FirePerimeter]]] = {}
        for perimeter, canonical in rows:
            grouped_rows.setdefault(canonical.id, (canonical, []))[1].append(perimeter)
        for canonical, grouped_perimeters in grouped_rows.values():
            for perimeter in grouped_perimeters:
                metrics["linked_detections"] += await self._link_firms(canonical, perimeter)
            await self._refresh_canonical_group(canonical, grouped_perimeters)
        await self._hide_empty_osint_incidents()
        await self.session.flush()
        return metrics

    async def _group_adjacent_effis(
        self,
        rows: Sequence[tuple[FirePerimeter, Incident]],
    ) -> tuple[list[tuple[FirePerimeter, Incident]], int]:
        if len(rows) < 2:
            return list(rows), 0
        perimeter_by_id = {perimeter.id: (perimeter, canonical) for perimeter, canonical in rows}
        first = aliased(FirePerimeter)
        second = aliased(FirePerimeter)
        geography = Geography(srid=4326)
        candidate_pairs = (
            await self.session.execute(
                select(
                    first.id,
                    second.id,
                    func.ST_Distance(cast(first.geometry, geography), cast(second.geometry, geography)),
                ).where(
                    first.id.in_(perimeter_by_id),
                    second.id.in_(perimeter_by_id),
                    first.id < second.id,
                    func.ST_DWithin(
                        cast(first.geometry, geography),
                        cast(second.geometry, geography),
                        EFFIS_GROUP_MAX_DISTANCE_METERS,
                    ),
                )
            )
        ).all()
        parent = {perimeter_id: perimeter_id for perimeter_id in perimeter_by_id}
        reasons_by_pair: dict[frozenset[UUID], list[str]] = {}

        def find(perimeter_id: UUID) -> UUID:
            while parent[perimeter_id] != perimeter_id:
                parent[perimeter_id] = parent[parent[perimeter_id]]
                perimeter_id = parent[perimeter_id]
            return perimeter_id

        for first_id, second_id, distance in candidate_pairs:
            first_perimeter, first_incident = perimeter_by_id[first_id]
            second_perimeter, second_incident = perimeter_by_id[second_id]
            first_metadata = self._metadata(first_incident)
            second_metadata = self._metadata(second_incident)
            first_time = first_perimeter.observed_at or first_incident.observed_at or datetime.now(UTC)
            second_time = second_perimeter.observed_at or second_incident.observed_at or datetime.now(UTC)
            reasons = effis_group_reasons(
                distance_meters=float(distance),
                time_delta=abs(first_time - second_time),
                first_hashtags=set(self._string_list(first_metadata.get("hashtags"))),
                second_hashtags=set(self._string_list(second_metadata.get("hashtags"))),
                first_commune=self._string(first_metadata.get("commune")),
                second_commune=self._string(second_metadata.get("commune")),
                first_province=self._string(first_metadata.get("province")),
                second_province=self._string(second_metadata.get("province")),
                first_area_hectares=first_perimeter.area_hectares,
                second_area_hectares=second_perimeter.area_hectares,
            )
            if not reasons:
                continue
            first_root = find(first_id)
            second_root = find(second_id)
            if first_root != second_root:
                parent[second_root] = first_root
            reasons_by_pair[frozenset((first_id, second_id))] = reasons

        groups: dict[UUID, list[tuple[FirePerimeter, Incident]]] = {}
        for perimeter_id, row in perimeter_by_id.items():
            groups.setdefault(find(perimeter_id), []).append(row)
        result: list[tuple[FirePerimeter, Incident]] = []
        merged = 0
        for members in groups.values():
            members.sort(key=lambda row: (float(row[0].area_hectares or 0), row[0].observed_at or datetime.min.replace(tzinfo=UTC)), reverse=True)
            primary_perimeter, primary = members[0]
            for perimeter, duplicate in members[1:]:
                pair_reasons = reasons_by_pair.get(frozenset((primary_perimeter.id, perimeter.id)), ["transitive_adjacent_group"])
                await self._merge_effis_incident(primary, duplicate, pair_reasons)
                perimeter.incident_id = primary.id
                merged += 1
            result.extend((perimeter, primary) for perimeter, _ in members)
        await self.session.flush()
        return result, merged

    async def _merge_effis_incident(self, primary: Incident, duplicate: Incident, reasons: list[str]) -> None:
        if primary.id == duplicate.id:
            return
        for model in (
            FireDetection,
            FirePerimeter,
            OfficialNotice,
            EvacuationZone,
            RestrictionZone,
            RoadIncident,
            SmokeForecast,
            RiskForecast,
        ):
            await self.session.execute(update(model).where(model.incident_id == duplicate.id).values(incident_id=primary.id))
        await self.session.execute(
            update(EmergencyPublication).where(EmergencyPublication.incident_id == duplicate.id).values(incident_id=primary.id)
        )
        primary_metadata = self._metadata(primary)
        duplicate_metadata = self._metadata(duplicate)
        merged_hashtags = merge_case_insensitive_values(
            self._string_list(primary_metadata.get("hashtags")),
            self._string_list(duplicate_metadata.get("hashtags")),
        )
        merged_locations = merge_case_insensitive_values(
            self._string_list(primary_metadata.get("affected_locations")),
            self._string_list(duplicate_metadata.get("affected_locations")),
        )
        evidence_by_url: dict[str, dict[str, Any]] = {}
        primary_evidence = primary_metadata.get("evidence_sources")
        duplicate_evidence = duplicate_metadata.get("evidence_sources")
        evidence_items = [
            *(primary_evidence if isinstance(primary_evidence, list) else []),
            *(duplicate_evidence if isinstance(duplicate_evidence, list) else []),
        ]
        for evidence in evidence_items:
            if isinstance(evidence, dict):
                evidence_by_url[str(evidence.get("url") or evidence)] = evidence
        merged_ids = set(self._string_list(primary_metadata.get("merged_incident_ids")))
        merged_ids.add(str(duplicate.id))
        matches = list(primary_metadata.get("reconciliation_matches", []))
        matches.append({"incident_id": str(duplicate.id), "score": 100, "reasons": reasons})
        primary_metadata.update(
            {
                "merged_incident_ids": sorted(merged_ids),
                "reconciliation_matches": matches,
                "hashtags": merged_hashtags,
                "primary_hashtag": primary_metadata.get("primary_hashtag")
                or duplicate_metadata.get("primary_hashtag")
                or (merged_hashtags[0] if merged_hashtags else None),
                "affected_locations": merged_locations,
                "evidence_sources": list(evidence_by_url.values()),
            }
        )
        primary.original_metadata = primary_metadata
        duplicate.original_metadata = {
            **duplicate_metadata,
            "merged_into": str(primary.id),
            "hidden": True,
            "reconciliation_score": 100,
            "reconciliation_reasons": reasons,
        }

    async def _assign_publications(
        self,
        rows: Sequence[tuple[FirePerimeter, Incident]],
        cutoff: datetime,
        *,
        only_unassigned: bool,
    ) -> None:
        statement = select(EmergencyPublication).where(
            EmergencyPublication.published_at >= cutoff,
            EmergencyPublication.review_status != "rejected",
        )
        if only_unassigned:
            statement = statement.where(EmergencyPublication.incident_id.is_(None))
        publications = (await self.session.execute(statement)).scalars().all()
        for publication in publications:
            if publication.raw_metadata.get("multi_incident_summary"):
                continue
            normalized_text = normalize_match_text(publication.original_text)
            if publication.risk_type != "wildfire" and not any(
                token in normalized_text for token in ("incendi", "incendio", "forestal", "baso sute", "#if")
            ):
                continue
            locations = {str(location.get("name")) for location in publication.locations if isinstance(location, dict) and location.get("name")}
            publication_hashtags = extract_incident_hashtags(publication.original_text)
            best: tuple[int, Incident] | None = None
            for perimeter, canonical in rows:
                observed_at = perimeter.observed_at or canonical.observed_at or publication.published_at
                time_delta = abs(publication.published_at - observed_at)
                if time_delta > MATCH_WINDOW:
                    continue
                metadata = self._metadata(canonical)
                spatial_distance = await self.session.scalar(
                    select(
                        func.ST_Distance(
                            cast(EmergencyPublication.geometry, Geography(srid=4326)),
                            cast(FirePerimeter.geometry, Geography(srid=4326)),
                        )
                    ).where(EmergencyPublication.id == publication.id, FirePerimeter.id == perimeter.id)
                )
                spatial_distance_meters = float(spatial_distance) if spatial_distance is not None else None
                spatial_match = spatial_distance_meters is not None and spatial_distance_meters <= 1
                score, reasons = score_fire_match(
                    commune=self._string(metadata.get("commune")),
                    province=self._string(metadata.get("province")),
                    canonical_hashtags=set(self._string_list(metadata.get("hashtags"))),
                    canonical_locations=set(self._string_list(metadata.get("affected_locations"))),
                    candidate_text=publication.original_text,
                    candidate_locations=locations,
                    candidate_hashtags=publication_hashtags,
                    spatial_match=spatial_match,
                    time_delta=time_delta,
                    spatial_distance_meters=spatial_distance_meters,
                )
                if is_fire_match(score, reasons) and (best is None or score > best[0]):
                    best = (score, canonical)
            if best is not None:
                publication.incident_id = best[1].id
            elif not only_unassigned and publication.incident_id is not None:
                current_incident = await self.session.get(Incident, publication.incident_id)
                if current_incident and self._metadata(current_incident).get("canonical_source") == "EFFIS":
                    publication.incident_id = None
        await self.session.flush()

    async def _hide_empty_osint_incidents(self) -> None:
        incidents = (
            (
                await self.session.execute(
                    select(Incident).where(
                        Incident.original_metadata["osint"].as_boolean().is_(True),
                        func.coalesce(Incident.original_metadata["canonical_source"].astext, "") != "EFFIS",
                    )
                )
            )
            .scalars()
            .all()
        )
        for incident in incidents:
            publication_count = await self.session.scalar(
                select(func.count(EmergencyPublication.id)).where(EmergencyPublication.incident_id == incident.id)
            )
            if int(publication_count or 0) == 0:
                incident.original_metadata = {**self._metadata(incident), "hidden": True}

    async def _merge_matching_osint(self, canonical: Incident, perimeter: FirePerimeter) -> int:
        observed_at = perimeter.observed_at or canonical.observed_at or datetime.now(UTC)
        lower = observed_at - MATCH_WINDOW
        upper = observed_at + MATCH_WINDOW
        candidates = (
            (
                await self.session.execute(
                    select(Incident).where(
                        Incident.id != canonical.id,
                        Incident.observed_at.between(lower, upper),
                        Incident.original_metadata["osint"].as_boolean().is_(True),
                        Incident.original_metadata["merged_into"].astext.is_(None),
                        func.coalesce(Incident.original_metadata["canonical_source"].astext, "") != "EFFIS",
                    )
                )
            )
            .scalars()
            .all()
        )
        merged = 0
        canonical_metadata = self._metadata(canonical)
        canonical_hashtags = set(self._string_list(canonical_metadata.get("hashtags")))
        canonical_locations = set(self._string_list(canonical_metadata.get("affected_locations")))
        commune = self._string(canonical_metadata.get("commune"))
        province = self._string(canonical_metadata.get("province"))
        for candidate in candidates:
            candidate_metadata = self._metadata(candidate)
            publications = (
                (await self.session.execute(select(EmergencyPublication).where(EmergencyPublication.incident_id == candidate.id))).scalars().all()
            )
            candidate_text = " ".join([candidate.title, candidate.summary or "", *(publication.original_text for publication in publications)])
            normalized_candidate_text = normalize_match_text(candidate_text)
            wildfire_signal = candidate_metadata.get("risk_type") == "wildfire" or any(
                token in normalized_candidate_text for token in ("incendi", "incendio", "forestal", "baso sute", "#if")
            )
            if not wildfire_signal:
                continue
            candidate_locations = set(self._string_list(candidate_metadata.get("affected_locations")))
            for publication in publications:
                candidate_locations.update(
                    str(location.get("name")) for location in publication.locations if isinstance(location, dict) and location.get("name")
                )
            candidate_hashtags = extract_incident_hashtags(candidate_text)
            spatial_match = bool(
                await self.session.scalar(
                    select(
                        func.coalesce(
                            func.ST_Intersects(Incident.geometry, FirePerimeter.geometry),
                            False,
                        )
                    ).where(Incident.id == candidate.id, FirePerimeter.id == perimeter.id)
                )
            )
            candidate_time = candidate.observed_at or observed_at
            time_delta = abs(candidate_time - observed_at)
            score, reasons = score_fire_match(
                commune=commune,
                province=province,
                canonical_hashtags=canonical_hashtags,
                canonical_locations=canonical_locations,
                candidate_text=candidate_text,
                candidate_locations=candidate_locations,
                candidate_hashtags=candidate_hashtags,
                spatial_match=spatial_match,
                time_delta=time_delta,
            )
            if not is_fire_match(score, reasons):
                continue
            await self._merge_incident(canonical, candidate, publications, score, reasons)
            canonical_hashtags.update(candidate_hashtags)
            merged += 1
        return merged

    async def _merge_incident(
        self,
        canonical: Incident,
        duplicate: Incident,
        publications: Sequence[EmergencyPublication],
        score: int,
        reasons: list[str],
    ) -> None:
        linked_models = (
            FireDetection,
            FirePerimeter,
            OfficialNotice,
            EvacuationZone,
            RestrictionZone,
            RoadIncident,
            SmokeForecast,
            RiskForecast,
        )
        for model in linked_models:
            await self.session.execute(update(model).where(model.incident_id == duplicate.id).values(incident_id=canonical.id))
        for publication in publications:
            publication.incident_id = canonical.id

        canonical_metadata = self._metadata(canonical)
        duplicate_metadata = self._metadata(duplicate)
        hashtags = set(self._string_list(canonical_metadata.get("hashtags")))
        hashtags.update(
            extract_incident_hashtags(" ".join([duplicate.title, duplicate.summary or "", *(item.original_text for item in publications)]))
        )
        locations = set(self._string_list(canonical_metadata.get("affected_locations")))
        locations.update(self._string_list(duplicate_metadata.get("affected_locations")))
        merged_ids = set(self._string_list(canonical_metadata.get("merged_incident_ids")))
        merged_ids.add(str(duplicate.id))
        matches = list(canonical_metadata.get("reconciliation_matches", []))
        matches.append({"incident_id": str(duplicate.id), "score": score, "reasons": reasons})
        canonical_metadata.update(
            {
                "osint": True,
                "canonical_fire": True,
                "canonical_source": "EFFIS",
                "hashtags": sorted(hashtags, key=str.casefold),
                "affected_locations": sorted(locations, key=str.casefold),
                "merged_incident_ids": sorted(merged_ids),
                "reconciliation_matches": matches,
            }
        )
        canonical.original_metadata = canonical_metadata
        duplicate.original_metadata = {
            **duplicate_metadata,
            "merged_into": str(canonical.id),
            "hidden": True,
            "reconciliation_score": score,
            "reconciliation_reasons": reasons,
        }

    async def _link_firms(self, canonical: Incident, perimeter: FirePerimeter) -> int:
        observed_at = perimeter.observed_at or canonical.observed_at or datetime.now(UTC)
        lower = observed_at - timedelta(days=2)
        upper = observed_at + MATCH_WINDOW
        perimeter_geometry = select(FirePerimeter.geometry).where(FirePerimeter.id == perimeter.id).scalar_subquery()
        result = await self.session.execute(
            update(FireDetection)
            .where(
                FireDetection.incident_id.is_(None),
                FireDetection.observed_at.between(lower, upper),
                firms_perimeter_match(perimeter_geometry),
            )
            .values(incident_id=canonical.id)
        )
        return int(result.rowcount or 0)

    async def _refresh_canonical(self, canonical: Incident, perimeter: FirePerimeter) -> None:
        publications = (
            (
                await self.session.execute(
                    select(EmergencyPublication)
                    .where(
                        EmergencyPublication.incident_id == canonical.id,
                        EmergencyPublication.review_status != "rejected",
                    )
                    .order_by(EmergencyPublication.published_at.desc())
                )
            )
            .scalars()
            .all()
        )
        detection_stats = (
            await self.session.execute(
                select(
                    func.count(FireDetection.id),
                    func.min(FireDetection.observed_at),
                    func.max(FireDetection.observed_at),
                    func.sum(FireDetection.frp_mw),
                ).where(FireDetection.incident_id == canonical.id)
            )
        ).one()
        metadata = self._metadata(canonical)
        hashtags = set(self._string_list(metadata.get("hashtags")))
        hashtag_counts: Counter[str] = Counter()
        affected_locations = set(self._string_list(metadata.get("affected_locations")))
        evidence_sources: list[dict[str, object]] = []
        for publication in publications:
            publication_hashtags = extract_incident_hashtags(publication.original_text)
            hashtags.update(publication_hashtags)
            hashtag_counts.update(publication_hashtags)
            affected_locations.update(
                str(location.get("name")) for location in publication.locations if isinstance(location, dict) and location.get("name")
            )
            evidence_sources.append(
                {
                    "authority": publication.authority,
                    "url": publication.url,
                    "source_type": publication.source_type,
                    "confidence": publication.confidence,
                }
            )
        metadata.update(
            {
                "canonical_fire": True,
                "canonical_source": "EFFIS",
                "perimeter_id": str(perimeter.id),
                "hashtags": sorted(hashtags, key=str.casefold),
                "primary_hashtag": hashtag_counts.most_common(1)[0][0] if hashtag_counts else None,
                "affected_locations": sorted(affected_locations, key=str.casefold),
                "evidence_sources": evidence_sources,
                "firms_detection_count": int(detection_stats[0] or 0),
                "firms_oldest_detection_at": detection_stats[1].isoformat() if detection_stats[1] else None,
                "firms_newest_detection_at": detection_stats[2].isoformat() if detection_stats[2] else None,
                "firms_total_frp_mw": float(detection_stats[3]) if detection_stats[3] is not None else None,
            }
        )
        canonical.observed_at = perimeter.observed_at
        canonical.status = IncidentStatus.REPORTED
        canonical.summary = "Perimetre publicat per EFFIS. Sense comunicacions operatives associades."
        for key in (
            "osint",
            "event_type",
            "risk_type",
            "es_alert_status",
            "instructions",
            "es_alert_message",
        ):
            metadata.pop(key, None)
        if publications:
            latest = publications[0]
            metadata.update(
                {
                    "osint": True,
                    "event_type": latest.event_type,
                    "risk_type": latest.risk_type,
                    "es_alert_status": latest.es_alert_status,
                    "instructions": latest.instructions,
                    "es_alert_message": latest.es_alert_message,
                }
            )
            canonical.summary = latest.title
            canonical.observed_at = max(canonical.observed_at or latest.published_at, latest.published_at)
            canonical.status = IncidentStatus.CONTROLLED if latest.action_state == "ended" else IncidentStatus.ACTIVE
        hashtag_list = self._string_list(metadata.get("hashtags"))
        commune = self._string(metadata.get("commune")) or self._string(metadata.get("province")) or "zona identificada"
        primary_hashtag = self._string(metadata.get("primary_hashtag"))
        canonical.title = f"Incendi {primary_hashtag} - {commune}" if primary_hashtag else f"Incendi - {commune}"
        canonical.original_metadata = metadata
        perimeter.original_metadata = {
            **self._metadata(perimeter),
            "canonical_title": canonical.title,
            "canonical_summary": canonical.summary,
            "hashtags": hashtag_list,
            "primary_hashtag": primary_hashtag,
            "firms_detection_count": metadata["firms_detection_count"],
            "firms_oldest_detection_at": metadata["firms_oldest_detection_at"],
            "firms_newest_detection_at": metadata["firms_newest_detection_at"],
            "firms_total_frp_mw": metadata["firms_total_frp_mw"],
            "osint_publication_count": len(publications),
        }

    async def _refresh_canonical_group(
        self,
        canonical: Incident,
        perimeters: Sequence[FirePerimeter],
    ) -> None:
        representative = max(perimeters, key=lambda item: float(item.area_hectares or 0))
        await self._refresh_canonical(canonical, representative)
        publications = (
            (
                await self.session.execute(
                    select(EmergencyPublication)
                    .where(
                        EmergencyPublication.incident_id == canonical.id,
                        EmergencyPublication.review_status != "rejected",
                    )
                    .order_by(EmergencyPublication.published_at.asc())
                )
            )
            .scalars()
            .all()
        )
        confirmed_endings = [
            publication.ends_at or publication.published_at
            for publication in publications
            if publication.risk_type == "wildfire" and publication.action_state == "ended"
        ]
        metadata = self._metadata(canonical)
        perimeter_metadata = [self._metadata(perimeter) for perimeter in perimeters]
        communes = sorted(
            {value for item in perimeter_metadata if (value := self._string(item.get("commune")))},
            key=str.casefold,
        )
        provinces = sorted(
            {value for item in perimeter_metadata if (value := self._string(item.get("province")))},
            key=str.casefold,
        )
        fire_dates = sorted(value for item in perimeter_metadata if (value := self._string(item.get("firedate"))))
        last_updates = sorted(value for item in perimeter_metadata if (value := self._string(item.get("lastupdate"))))
        metadata.update(
            {
                "area_ha": sum(float(perimeter.area_hectares or 0) for perimeter in perimeters),
                "firedate": fire_dates[0] if fire_dates else metadata.get("firedate"),
                "lastupdate": last_updates[-1] if last_updates else metadata.get("lastupdate"),
                "communes": communes,
                "provinces": provinces,
                "grouped_perimeter_count": len(perimeters),
                "effis_perimeter_ids": [str(perimeter.id) for perimeter in perimeters],
                "extinction_confirmed": bool(confirmed_endings),
                "confirmed_extinction_at": max(confirmed_endings).isoformat() if confirmed_endings else None,
            }
        )
        affected_locations = set(self._string_list(metadata.get("affected_locations")))
        affected_locations.update(communes)
        metadata["affected_locations"] = sorted(affected_locations, key=str.casefold)
        canonical.original_metadata = metadata
        location_label = " / ".join(communes[:2]) or " / ".join(provinces[:2]) or "zona identificada"
        primary_hashtag = self._string(metadata.get("primary_hashtag"))
        canonical.title = f"Incendi {primary_hashtag} - {location_label}" if primary_hashtag else f"Incendi - {location_label}"
        union_geometry = await self.session.scalar(
            select(func.ST_Multi(func.ST_Union(FirePerimeter.geometry))).where(FirePerimeter.id.in_([perimeter.id for perimeter in perimeters]))
        )
        if union_geometry is not None:
            canonical.geometry = union_geometry
        for perimeter in perimeters:
            perimeter.original_metadata = {
                **self._metadata(perimeter),
                "canonical_title": canonical.title,
                "canonical_summary": canonical.summary,
                "hashtags": metadata.get("hashtags", []),
                "primary_hashtag": metadata.get("primary_hashtag"),
                "firms_detection_count": metadata.get("firms_detection_count", 0),
                "firms_oldest_detection_at": metadata.get("firms_oldest_detection_at"),
                "firms_newest_detection_at": metadata.get("firms_newest_detection_at"),
                "firms_total_frp_mw": metadata.get("firms_total_frp_mw"),
                "osint_publication_count": len(publications),
                "grouped_perimeter_count": len(perimeters),
                "extinction_confirmed": metadata.get("extinction_confirmed", False),
                "confirmed_extinction_at": metadata.get("confirmed_extinction_at"),
            }

    @staticmethod
    def _metadata(record: Any) -> dict[str, Any]:
        return dict(record.original_metadata) if isinstance(record.original_metadata, dict) else {}

    @staticmethod
    def _string(value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _string_list(value: object) -> list[str]:
        return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


async def reconcile_recent_fires(session: AsyncSession) -> dict[str, int]:
    return await CanonicalFireReconciler(session).reconcile_recent()
