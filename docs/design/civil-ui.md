# Disseny del Dashboard Civil

## Composicio

El mapa ocupa la superficie principal. No hi ha barra lateral exterior.

- Cerca municipal: cantonada superior esquerra del mapa.
- Incidents i avisos/cronologia: dos panells laterals interns, compactes i scrollejables.
- Filtre de capes: control intern del mapa.
- Llegenda: baix a la dreta, oberta inicialment i tancable.
- Detall: panell complet sota el mapa, vinculat a `Veure tota la informacio`.
- Carrega: popup modal centrat dins del mapa.

Els controls superiors drets deixen espai als botons `+` i `-` de MapLibre. Els panells tenen alçada estable i scroll intern; el seu contingut no allarga la pagina.

## Llenguatge visual

- Dades oficials: formes solides i font visible.
- Dades estimades o inferides: advertiment, procedencia i menor certesa visual.
- FIRMS: deteccions del dia seleccionat; punts originals opcionals i apagats inicialment.
- EFFIS: contorn i farciment gris d'area cremada, clicable a tot l'interior.
- Avisos X/Nitter: blau, diferenciats dels incidents d'incendi.
- Carreteres: taronja per incendi/obstacle ambiental; lila per la resta.
- Avisos meteorologics: groc, taronja o vermell segons nivell CAP/Proteccio Civil.

El color mai es l'unic indicador: etiqueta, font, estat i data reforcen el significat.

## Interaccio

- Clicar una entrada o geometria centra el mapa a la seva zona valida.
- Cap seleccio pot provocar zoom a tota Espanya per falta de geometria.
- Popup d'incendi: resum curt, dates confirmades, hashtag i boto de detall.
- El panell inferior concentra cronologia, FIRMS, EFFIS, instruccions, fonts i posts.
- Els toggles canvien visibilitat MapLibre sense reconstruir el mapa.
- Pan i zoom actualitzen URL sense navegacio Next.js ni refetch.

## Responsive i accessibilitat

En mobil, els controls es mantenen accessibles sobre el mapa amb dimensions limitades i scroll. Llistes i detall ofereixen equivalent textual a les geometries. Inputs i botons son natius, tenen focus visible i el text no depen del color.
