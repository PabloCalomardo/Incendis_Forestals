# 🔥 Wildfire Intelligence Platform (WIP)

> Plataforma intel·ligent per a la monitorització, visualització i predicció d'incendis forestals orientada tant a la ciutadania com als serveis d'emergència.

---

# Objectiu

Actualment la informació relacionada amb els incendis forestals està distribuïda entre nombroses fonts (112, Bombers, MITECO, Copernicus, NASA, DGT, AEMET...), provocant desinformació i dificultant la presa de decisions.

L'objectiu del projecte és construir una plataforma única capaç d'integrar totes aquestes fonts oficials, enriquir-les amb models predictius i mostrar-les en dues interfícies diferenciades:

- 👨‍👩‍👧 **Civil** → Informació clara, simple i oficial.
- 🚒 **Bomber** → Informació operativa avançada amb eines de suport a la decisió.

---

# Arquitectura General

```text
                APIs Oficials
──────────────────────────────────────────────

 NASA FIRMS
 Copernicus EFFIS
 MITECO
 112 / Comunitats Autònomes
 AEMET
 CAMS Atmosphere
 DGT
 IGN
 OpenStreetMap

                │
                ▼

        Data Ingestion Layer
    (Connectors + Validació)

                │
                ▼

       Data Normalization Layer

                │
                ▼

      PostgreSQL + PostGIS

                │
 ┌──────────────┼──────────────┐
 │              │              │
 ▼              ▼              ▼

Prediction   Routing      Smoke Model
 Engine       Engine       Engine

 │              │              │
 └──────────────┼──────────────┘
                ▼

          REST / GraphQL API

                │
      ┌─────────┴─────────┐
      ▼                   ▼

 Civil Portal        Firefighter Portal
```

---

# Arquitectura Tecnològica

## Frontend

- Next.js 15
- React 19
- TypeScript
- TailwindCSS
- MapLibre GL JS
- Zustand
- TanStack Query
- Framer Motion

---

## Backend

- Python
- FastAPI
- SQLAlchemy
- GeoAlchemy2
- Celery
- Redis

---

## Base de dades

PostgreSQL + PostGIS

Emmagatzemarà:

- Incendis
- Històric
- Perímetres
- Deteccions
- Carreteres
- Meteorologia
- Restriccions
- Prediccions
- Alertes

---

## Geospatial Engine

- PostGIS
- GDAL
- Shapely
- GeoPandas

Responsable de:

- Intersecció de capes
- Operacions GIS
- Buffers
- Zones d'influència
- Càlculs geogràfics

---

## Prediction Engine

Servei dedicat exclusivament als models.

Responsabilitats:

- Evolució del perímetre
- Direcció probable
- Velocitat de propagació
- Intensitat
- Risc

Aquest servei serà totalment desacoblat del Backend.

---

## Smoke Engine

Servei independent.

Entrades:

- FIRMS
- CAMS
- GFAS
- AEMET

Sortides:

- Núvol estimat
- Concentració
- Visibilitat
- Zones afectades
- Predicció temporal

---

## Routing Engine

Motor de navegació propi.

Possibles tecnologies:

- GraphHopper
- Valhalla
- OpenRouteService

Permetrà:

- Evitar carreteres afectades
- Evitar fum
- Evitar zones calentes
- Recalcular rutes dinàmicament

---

# APIs Integrades

## NASA FIRMS

Funció:

- Detecció d'anomalies tèrmiques
- Potència radiativa
- Coordenades
- Hora

Utilització:

- Localitzar focus actius.

---

## Copernicus EFFIS

Funció:

- Incendis europeus
- Superfície cremada
- Perímetres
- Risc d'incendi

Utilització:

- Estat general dels incendis.

---

## MITECO

Funció:

- Estat oficial
- Mitjans desplegats
- Informes

Utilització:

- Font oficial espanyola.

---

## Comunitats Autònomes

Funció:

- Comunicats
- Evacuacions
- Restriccions

Utilització:

- Informació oficial territorial.

---

## AEMET

Funció:

- Vent
- Humitat
- Temperatura
- Predicció

Utilització:

- Alimentar els models predictius.

---

## CAMS

Funció:

- Qualitat de l'aire
- Aerosols
- Concentració de fum

Utilització:

- Modelització del núvol.

---

## DGT

Funció:

- Carreteres
- Incidències
- Talls

Utilització:

- Mobilitat.

---

## IGN

Funció:

- Cartografia oficial
- MDT
- Relleu
- Topografia

Utilització:

- Models GIS.

---

## OpenStreetMap

Funció:

- Camins
- Pistes forestals
- Xarxa viària

Utilització:

- Navegació.

---

# Data Pipeline

```text
API Polling

        │

        ▼

Raw Data

        │

        ▼

Validation

        │

        ▼

Normalization

        │

        ▼

Geo Processing

        │

        ▼

Database

        │

        ▼

Prediction Engine

        │

        ▼

REST API

        │

        ▼

Frontend
```

---

# Model de Dades

Cada objecte geogràfic tindrà:

```json
{
    "id": "...",
    "type": "...",
    "geometry": "...",
    "source": "...",
    "status": "...",
    "confidence": 0.92,
    "created_at": "...",
    "updated_at": "...",
    "expires_at": "...",
    "version": 5
}
```

---

# Portal Civil

## Funcionalitats

- Mapa interactiu
- Incendis actius
- Perímetres oficials
- Restriccions
- Evacuacions
- Carreteres tallades
- Qualitat de l'aire
- Notícies verificades
- Alertes
- Cerca per municipi
- Històric

---

## Capes

- Incendis
- Perímetres
- Evacuacions
- Carreteres
- Qualitat de l'aire
- Risc
- Notícies

---

# Portal Bomber

## Funcionalitats

- Login segur
- Dashboard operatiu
- Predicció del foc
- Predicció del fum
- Evolució temporal
- Comparació de models
- Visibilitat
- Humitat
- Vent
- Pendent
- Vegetació
- Infraestructures
- Camins forestals
- Rutes òptimes
- Corredors operatius
- Carreteres potencialment afectades
- Històric complet

---

## Càlcul de carreteres afectades

Per cada actualització:

```
Nou perímetre

        │

        ▼

Predicció del fum

        │

        ▼

Intersecció GIS

        │

        ▼

Carreteres afectades

        │

        ▼

Càlcul de risc

        │

        ▼

Ruta alternativa
```

Les carreteres podran tenir diferents estats:

- 🟢 Accessible
- 🟡 Possiblement afectada
- 🟠 Fum intens
- 🔴 Tall oficial
- ⚫ Dades insuficients

---

# Intel·ligència Artificial

## Predicció del foc

Entrades

- Vent
- Humitat
- Temperatura
- Vegetació
- Pendent
- Històric
- Deteccions FIRMS

Sortides

- Propagació
- Direcció
- Intensitat
- Temps estimat

---

## Predicció del fum

Entrades

- GFAS
- CAMS
- Vent
- Temperatura
- Topografia

Sortides

- Núvol
- Concentració
- Visibilitat
- Zones afectades

---

## Sistema de confiança

Cada informació tindrà un nivell de confiança.

```
100%
│
│ Oficial
│
80%
│
│ Confirmat per múltiples fonts
│
60%
│
│ Model predictiu
│
40%
│
│ Satèl·lit
│
20%
│
│ Hipòtesi
│
0%
```

---

# Arquitectura de Microserveis

```text
                API Gateway

                     │

────────────────────────────────────

 Authentication Service

 Incident Service

 Weather Service

 GIS Service

 Prediction Service

 Smoke Service

 Routing Service

 Notification Service

 Analytics Service

────────────────────────────────────

             PostgreSQL

               Redis

             Object Storage
```

---

# Escalabilitat

La plataforma està preparada per ampliar-se a:

- Europa
- Amèrica
- Austràlia
- Canadà

Només caldrà afegir nous connectors de dades mantenint la mateixa arquitectura.

---

# Objectiu Final

Construir la plataforma de referència per al seguiment d'incendis forestals, combinant informació oficial, dades satel·litàries, sistemes GIS i models predictius per oferir una eina fiable tant per a la ciutadania com per als equips d'emergència.