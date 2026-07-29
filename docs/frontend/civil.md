# Dashboard Civil

Ruta: `/civil`. Consumeix exclusivament l'API publica `/civil/*`.

## Experiencia actual

El mapa es la superficie principal. Tots els controls viuen dins del mapa:

- cerca de municipi a dalt a l'esquerra;
- mini llistes scrollejables d'incidents i d'avisos/cronologia;
- filtre de capes;
- llegenda oberta per defecte a baix a la dreta;
- popup central `Carregant dades al mapa` durant la carrega inicial;
- panell de detall complet sota el mapa.

Seleccionar una entrada centra el mapa nomes quan disposa d'una geometria valida. No s'utilitza cap `fitBounds` global com a fallback. Els controls de la dreta mantenen marge respecte dels botons de zoom de MapLibre.

## Capes

- **FIRMS**: totes les deteccions del dia seleccionat; el selector temporal agrupa per dia, no per moment. `Punts FIRMS` esta desactivada inicialment, pero els grups i la resta de capes FIRMS continuen visibles. Les deteccions no s'oculten dins d'un perimetre EFFIS.
  Les arees FIRMS es reconstrueixen i s'uneixen visualment abans de pintar el farciment vermell, de manera que un
  solapament MODIS/VIIRS no acumula transparencia. Els contadors continuen separats per grup/sensor i es desplacen
  lleument quan se solapen per evitar que quedin un damunt de l'altre.
- **EFFIS actual**: perimetres de menys de set dies, visibles per defecte, amb farciment gris clicable.
- **Incendis d'aquest any**: entre set dies i un any, desactivada per defecte.
- **Historic d'incendis**: mes d'un any, desactivada per defecte.
- **Avisos socials**: publicacions X/Nitter independents en blau, separades visualment dels incendis.
- **ES-Alert, avisos i carreteres**: geometries oficials o inferides amb la seva procedencia. Restriccions per incendi o obstacle ambiental en taronja; la resta en lila.
- **Aeronaus**: aeronaus d'emergencia actives en fonts ADS-B publiques. Els punts, rumb i etiqueta es renderitzen sempre per sobre de la resta de capes del mapa.

Els popups EFFIS mostren data d'inici, data d'extincio nomes si esta confirmada, hashtag i l'accio `Veure tota la informacio`. El detall inferior agrega perimetres, deteccions, cronologia i publicacions relacionades.

## Dades i estat URL

TanStack Query carrega incidents, deteccions, cronologia FIRMS, perimetres, avisos, ES-Alert, restriccions, risc, fum, OSINT i aeronaus. Una fallada parcial no inutilitza la resta del mapa.

El bbox inicial FIRMS i del mapa civil es `-10.0,35.5,4.5,44.5`, alineat amb la ingesta NASA FIRMS. Les deteccions
usen paginacio de 200 elements i un sostre de 10.000 features FIRMS per no tallar dies densos.

La capa `Aeronaus` es refresca cada 20 segons quan esta activa. Aquest refresc no mostra el popup central de carrega; el text superior del mapa canvia a `Refrescant Aeronaus`.

L'URL conserva municipi, seleccio i viewport:

```text
/civil?municipality=Girona&selected=...&lng=2.82&lat=41.98&z=8
```

El viewport s'actualitza amb `history.replaceState`; moure el mapa no remunta la pagina ni torna a descarregar totes les capes. La cache de capes es de cinc minuts.

## Cerca geografica

`GET /civil/municipalities/search` retorna nom oficial, codi INE, centre i `bbox`. La resolucio de toponims OSINT exigeix coincidencia exacta o contextual: `Santa Coloma de Queralt` no es replica a altres `Santa Coloma`. `Agost` esta exclosa de la geocodificacio textual per evitar confondre el municipi amb el mes.

## Mapa base

```text
NEXT_PUBLIC_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
```

La URL es configurable. Produccio ha d'utilitzar un proveidor amb quota i condicions adequades o tiles propis.

## Estats degradats

- Error d'una capa: la resta continua operativa i la capa mostra error.
- Resposta buida: estat buit i recompte zero, sense dades simulades.
- Carrega inicial: popup centrat dins del mapa.
- Refresc d'aeronaus: indicador compacte a la capcalera, sense bloquejar el mapa.
- Incident sense geometria fiable: visible al detall, sense zoom artificial.
