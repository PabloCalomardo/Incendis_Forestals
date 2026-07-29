# Full de ruta vigent

Estat funcional i guia de represa: [`current-state.md`](current-state.md). El pla seqüencial original es conserva a [`../PlaDimplementacio.md`](../PlaDimplementacio.md) com a registre historic.

## Prioritat 1: estabilitzar el Dashboard Civil

- completar la reparacio i metriques de geometries DATEX;
- reforçar cobertura OSINT/Nitter i deteccio de canvis de portals;
- construir la vista completa de revisio humana;
- afegir proves visuals responsive i de fluxos de seleccio/mapa;
- validar accessibilitat, rendiment geoespacial i cache;
- preparar tiles de produccio, observabilitat i backups.

## Prioritat 2: publicacio

- entorn staging reproduible;
- CI/CD, migracions controlades i rollback;
- secrets, headers, rate limits i escaneigs;
- proves de recuperacio i runbooks d'incident;
- revisio de llicencies i atribucions de totes les fonts;
- criteris de disponibilitat i avisos de cobertura incompleta.

## Prioritat 3: portal professional

Nomes despres d'acceptar el Dashboard Civil:

- OIDC, RBAC, MFA i auditoria;
- capes i eines GIS operatives;
- prediccions validades amb incertesa;
- routing d'emergencia explicable;
- temps real i notificacions amb permisos.

## Criteris de canvi

- No inventar APIs, geometries ni estat oficial.
- Preservar originals, procedencia i historial.
- Escalar proves amb el risc del canvi.
- Actualitzar `current-state.md`, el document d'integracio i el runbook quan canviï una font o contracte.
