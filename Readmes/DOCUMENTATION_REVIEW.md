# Dokumentationspruefung

Stand: 2026-09-24, Arbeitsstand einschliesslich Master-Zusammenführung, unabhängiger Punktabdeckung und der Trennung von Kern und
Bioakustik. Diese Beschreibung bestaetigt keinen bereits erfolgten Git-Push oder
produktiven Horeka-/Horeka-2-Lauf.

## Abgeglichen

- Haupt-README, Master-Referenz, lokale Anleitung, Deployment/Recovery und
  deutsche/englische Schritt-READMEs gegen den lokalen Code und `config.horeka.json`.
- Separater Bioakustikstart, phasenspezifische Validierung und begrenztes
  Bioakustik-Master-Update; unveraenderte deutsche Aufnahmezeitregel.
- 104 Master-Spalten in Schema v6, einschliesslich der fuenf unverbindlichen
  Raum-/Zeit-Naeheflags. Eine reine Bioakustik-Aktualisierung migriert ein altes
  Master-Schema nicht automatisch.
- 64 logische Bioakustik-Shards pro Modell, vier Slurm-Worker; HOSTRADA-Raster
  verteilen ihre logischen Variable/Jahr-Aufgaben auf zwei Worker.
- Relative Secrets-/Checkpoint-Pfade, bestehender Checkout und Clusterprofile.
- Fehler-/QC-Codes mit Bedeutung und Quellstelle in allen 18 Schrittbereichen,
  jeweils auf Deutsch und Englisch. Explizite Exceptions und Rueckgabecodes
  stehen getrennt daneben. Dynamische Fremdbibliotheksmeldungen werden nicht als
  erfundene statische Fehlercodes ausgegeben.

Die Referenz erfasst ausdrueckliche Diagnosewerte aus dem zugeordneten Quellcode.
Sie ist kein Versprechen, jede denkbare Bibliotheks-/Netzwerkexception aufzuzaehlen.
Statuswerte ohne Fehlerbedeutung sind als solche getrennt dargestellt.

## Wartung

```bash
python tools/generate_step_readmes.py
```

Erhaelt redaktionelle Texte und aktualisiert ausschliesslich die markierten
Diagnoseabschnitte. Neue Fehlercodes ohne gepflegte Bedeutung fuehren zu einem
Fehler, statt unerklaert in der Dokumentation zu landen.

```bash
python tools/documentation_reference.py --check
```

Prueft, ob diese Abschnitte noch dem Code entsprechen. Die maschinenlesbare
Referenz steht in `diagnostic_catalog.json`. Redaktionelle Aussagen muessen
weiterhin bei Verhaltensaenderungen geprueft werden.

## Historische Berichte

Datierte Audits und Zeitpruefungen sind als historisch gekennzeichnet. Ihre
damaligen Befunde und Zahlen wurden nicht nachtraeglich als aktuelle Messungen
umgeschrieben. Aktuelle Betriebsschritte stehen in den operativen READMEs.

## PDF

Das gemeinsame PDF-Handbuch enthaelt die READMEs und zentralen Betriebsreferenzen
mit Inhaltsverzeichnis und Lesezeichen. Die kurze ci-tec-README ist darin ein
eigenes Kapitel. Die Markdown-Dateien bleiben die wartbare Quelle.
