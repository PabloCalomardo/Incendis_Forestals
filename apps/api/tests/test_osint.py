from datetime import UTC, datetime

from app.ingestion.osint import (
    MunicipalityMentionIndex,
    SourceSpec,
    action_state,
    classify_event,
    detect_language,
    es_alert_evidence,
    extract_arrow_geography,
    extract_es_alert_message,
    extract_instructions,
    extract_locations,
    parse_feed,
    parse_nitter_feed,
    publication_hash,
)


def test_multilingual_event_classification_and_es_alert_evidence() -> None:
    catalan = "Proteccio Civil ha enviat un ES-Alert per l'incendi forestal. Confineu-vos a casa."
    spanish = "Se levanta el confinamiento por el incendio forestal."
    basque = "Baso-suteagatik ebakuatzeko agindua eman da."

    assert classify_event(catalan) == ("es_alert_sent", "wildfire")
    assert classify_event(spanish) == ("confinement_lift", "wildfire")
    assert classify_event(basque) == ("evacuation_order", "wildfire")
    assert detect_language(catalan) == "ca"
    assert es_alert_evidence("es_alert_sent", "official") == "confirmed_sent"
    assert es_alert_evidence("es_alert_received", "individual") == "presumed_received"
    assert action_state("confinement_lift") == "ended"
    assert "Confineu-vos" in (extract_instructions(catalan) or "")


def test_specific_fire_hashtags_and_extinction_updates_are_retained() -> None:
    assert classify_event("Set dotacions treballen al flanc nord #IFSierraOeste") == (
        "firefighting_update",
        "wildfire",
    )
    event_type, risk_type = classify_event("Incendio forestal extinguido en Artana")
    assert (event_type, risk_type) == ("fire_extinguished", "wildfire")
    assert action_state(event_type) == "ended"
    assert classify_event("15 dotacions en un incendi de vegetació a Santa Coloma de Queralt") == (
        "firefighting_update",
        "wildfire",
    )
    assert classify_event("Resum d'#IIFF: La Vall d'Uixó actiu") == ("firefighting_update", "wildfire")


def test_literal_message_and_toponym_extraction() -> None:
    text = (
        'Missatge de l’ES-Alert: "Incendi a la urbanització Can Soler. ' 'Evacueu immediatament i seguiu les indicacions dels serveis d’emergència."'
    )

    assert extract_es_alert_message(text) == (
        "Incendi a la urbanització Can Soler. Evacueu immediatament i seguiu les indicacions dels serveis d’emergència."
    )
    assert extract_locations("Incendi al municipi de Villa del Prado.") == ("Villa del Prado",)


def test_official_municipality_index_finds_plain_text_and_fire_hashtags() -> None:
    index = MunicipalityMentionIndex(["Súria", "Santa Coloma", "Santa Coloma de Queralt", "Vall d'Uixó, la", "Agost", "Prado", "Villa del Prado"])

    assert index.discover("A Súria, incendi extingit") == ("Súria",)
    assert index.discover("Incendi de vegetació a Santa Coloma de Queralt") == ("Santa Coloma de Queralt",)
    assert index.discover(
        "Incendi de vegetació a Santa Coloma de Queralt",
        ("Santa Coloma", "Santa Coloma de Cervelló", "Santa Coloma de Gramenet"),
    ) == ("Santa Coloma de Queralt",)
    assert index.discover("Comboi desplaçat a #IFLaValldUixó") == ("Vall d'Uixó, la",)
    assert index.discover("Suport a Villa del Prado") == ("Villa del Prado",)
    assert index.discover("L'episodi continuarà durant el mes d'agost") == ()
    assert index.discover("La calor s'allargarà fins al 5 d'agost") == ()
    assert index.discover("Incendi forestal declarat al municipi d'Agost") == ()


def test_arrow_summary_keeps_targets_and_excludes_administrative_regions() -> None:
    text = "✅Castelló ➡️ La Vall d'Uixó. Actiu ✅Alacant ➡️Pedreguer. Extingit ✅València ➡️Cortes de Pallás. Extingit"
    index = MunicipalityMentionIndex(["Castelló", "Alacant", "València", "Vall d'Uixó, la", "Pedreguer", "Cortes de Pallás"])

    assert extract_arrow_geography(text) == (
        ("Castelló", "Alacant", "València"),
        ("La Vall d'Uixó", "Pedreguer", "Cortes de Pallás"),
    )
    assert index.discover(text) == ("Vall d'Uixó, la", "Pedreguer", "Cortes de Pallás")


def test_feed_parser_and_deduplication_hash_are_stable() -> None:
    source = SourceSpec("112 Test", "Servei 112", "https://example.test/feed", "official", "rss")
    raw = """<rss><channel><item><guid>notice-1</guid><title>Ordre de confinament</title>
    <description>Incendi forestal. Confinense.</description><link>https://example.test/1</link>
    <pubDate>Mon, 27 Jul 2026 12:30:00 GMT</pubDate></item></channel></rss>"""

    records = parse_feed(raw, source, datetime.now(UTC))

    assert len(records) == 1
    assert records[0].published_at == datetime(2026, 7, 27, 12, 30, tzinfo=UTC)
    assert publication_hash(records[0].url, records[0].text) == publication_hash(records[0].url + "#fragment", records[0].text)


def test_nitter_rss_keeps_original_x_url_and_skips_retweets() -> None:
    raw = """<rss><channel>
    <item><guid>123</guid><title>Ordre de confinament al municipi de Artana.</title>
    <description>Ordre de confinament</description><link>https://nitter.net/bomberscat/status/123#m</link>
    <pubDate>Tue, 28 Jul 2026 18:27:32 GMT</pubDate></item>
    <item><guid>124</guid><title>RT by @bomberscat: contingut aliè</title>
    <link>https://nitter.net/bomberscat/status/124#m</link></item>
    </channel></rss>"""
    account = {"handle": "bomberscat", "authority": "Generalitat de Catalunya"}

    records = parse_nitter_feed(raw, account, "https://nitter.net", datetime.now(UTC))

    assert len(records) == 1
    assert records[0].url == "https://nitter.net/bomberscat/status/123"
    assert records[0].metadata["gateway"] == "nitter"
    assert records[0].metadata["canonical_x_url"] == "https://x.com/bomberscat/status/123"
    assert records[0].locations == ("Artana",)
