# Zeitkonflikte und LRT-Zellen

> Historischer Stand: Befunde und Zahlen gelten fuer den damaligen Audit/Lauf. Aktuelle Betriebsanweisungen stehen in der Haupt-README und Readmes/pipeline_phases.md.


Prüfung vom 16.09.2026, aktuelle Hauptvariante **no_K_post2017**.

**Keine der 47 Aufnahmen mit widersprüchlichen Quellenzeiten liegt in einer 100-m-Zelle mit LRT-Flächen dieser Variante.**

| Prüfung | Ergebnis |
|---|---:|
| Aufnahmen mit Zeitkonflikt | 47 |
| Zugeordnete, unterschiedliche INSPIRE-100-m-Zellen | 29 |
| Aufnahmen in einer Zelle mit LRT-Flächenüberlappung | 0 |
| Aufnahmen mit 100-m-Mehrheitsformation | 0 |
| Aufnahmepunkte innerhalb oder auf einer LRT-Polygongrenze | 0 |

Die tatsächlichen 29 Zellgeometrien wurden aus dem INSPIRE-GeoPackage gelesen.
Alle 47 Punkte liegen in ihrer zugeordneten Zelle. Für jede Zelle wurde der
LRT-GeoPackage räumlich abgefragt und auf positive Flächenüberlappung sowie
reine Grenzberührung geprüft. Auch reine Grenzberührungen kommen nicht vor.
Zusätzlich wurden die Punktzuordnung, die 100-m-Mehrheitstabelle und die
Master-Flags abgeglichen. Alle Prüfungen stimmen überein.

Ein vorhandener `grid_100m_id` bedeutet daher hier eine INSPIRE-Zuordnung,
aber keine LRT-Zuordnung. Das Ergebnis gilt für `no_K_post2017`; andere
LRT-Varianten wurden in dieser zusätzlichen Geometrieprüfung nicht untersucht.
Die 47 Zeitkonflikte bleiben für andere Auswertungen relevant.

- [Alle 47 Fälle mit Zeitwerten und LRT-Prüfung](time_conflicts_lrt.csv)
- [Alle 29 geprüften Zellen](time_conflict_grid_cells.csv)
- [Prüfergebnis und verwendete Dateien](time_conflicts_lrt_summary.json)
- [Ausführlicher Zeitreport](ZEITKORREKTUR_REPORT.md)
- [Zeitreport als PDF](Zeitreport.pdf) (Stand des lokalen Zeitlaufs vor Git-Übertragung)
- [ci-tec-README](../../README_CI_TEC.pdf)

Reproduzierbare Geometrieprüfung mit den Pfaden einer passenden Konfiguration:

```powershell
python tools/check_time_conflicts_lrt.py --config scripts_local_run/config.local.generated.json --conflicts Readmes/time_review/recording_time_conflicts.csv --output-dir Readmes/time_review
```

Die großen Master-, Geometrie- und vollständigen Auditdateien bleiben im
lokalen/LSDF-Datenbereich. Git enthält Code, Dokumentation, Prüfergebnisse und
die kompakten Falllisten. Es wurden keine Horeka-Jobs gestartet.
