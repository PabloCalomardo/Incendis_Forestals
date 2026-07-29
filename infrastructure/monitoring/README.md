# Monitoratge

La carpeta conserva la configuracio inicial de Prometheus. El projecte encara no te una pila de produccio completa: falten `/metrics` consolidat, dashboards Grafana, alertes de fonts/ingestes, retencio i runbooks d'observabilitat.

Metriques prioritaries:

- estat, durada i antiguitat de cada `DataIngestionRun`;
- fonts OSINT parcials o bloquejades;
- snapshots rebutjats per buit anormal o error;
- geometries DATEX pendents i taxa d'enriquiment CNIG;
- latencia/error/cache de l'API Civil;
- salut de PostgreSQL, Redis, MinIO, Celery i frontend.
