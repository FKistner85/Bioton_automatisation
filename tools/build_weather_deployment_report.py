"""Write the final report only after a verified, completed LSDF publication."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/weather_deployment'


def main():
    published=json.loads((OUT/'publish_result.json').read_text())
    assert published['status']=='complete' and published['lock_released']
    assert len(published['files'])==7 and published['weather_files_written']==0
    verified=json.loads((OUT/'prepared_validation.json').read_text())
    before=verified['weather_flags_before']
    after=verified['weather_flags_after']
    report=f'''# Wetterdaten und ci-tec: abgeschlossener Abgleich

Stand: 24. September 2026. Veröffentlichung: `{published['run_id']}`.

## Was jetzt auf LSDF steht

**Wetterinventar und die gemeinsame Bio_O_Ton_Master.csv sind aktualisiert und passen wieder zusammen.** CSV, Parquet, Master-Zusammenfassung, detailliertes/kompaktes Wetterinventar, Inventarstatus und Statusereignisse wurden gesichert, veröffentlicht und auf LSDF per SHA-256 zurückgeprüft. Die sieben Zieldateien sind im Veröffentlichungsprotokoll aufgelistet.

| Merkmal | Vorherige Master | Aktualisierte Master |
|---|---:|---:|
| Aufnahmezeilen | 111.866 | 111.866 |
| Spalten | 99 | 99 |
| weather_point_has_issues=True | {before} | {after} |
| Wettercodes | Zeitfehler, fehlende Dateien, fehlende Werte | ausschließlich missing_value |
| Wetterdatei laut Inventar vorhanden | 111.294 | 111.866 |

**6.557 Wetterflags weniger ({(before-after)/before:.1%}).** Die übrigen 2.615 Aufnahmen haben fehlende Messwerte. Das kann je nach benötigten Variablen und Stunden teilweise nutzbar sein; die Werte wurden nicht erfunden oder aufgefüllt.

## Warum keine Wetterdateien hochgeladen wurden

Die zunächst lokal vorbereiteten 6.267 Kürzungen bezogen sich auf den Stand des ersten Audits. Vor dem geplanten Upload wurde jede betroffene LSDF-Datei erneut gelesen: Alle waren inzwischen vom alten Horeka-Lauf neu geschrieben worden und enthielten das korrekte 263-Stunden-Fenster. Die lokalen älteren Kopien hätten neuere Daten überschrieben und wurden deshalb bewusst nicht hochgeladen.

Auch die übrigen Fälle wurden erneut geprüft. Von den ursprünglichen 6.513 Zeitfehlern bestehen jetzt 6.487 alle implementierten Wetterprüfungen; 26 haben nur noch fehlende Werte. Von den vorher fehlenden 572 Dateien sind inzwischen alle vorhanden: 70 ohne QC-Code und 502 mit missing_value. Die 2.087 vorherigen Fälle ausschließlich mit missing_value bleiben bestehen. Alle 500 ungeflaggten Kontrollfälle blieben unauffällig.

**Prüfumfang:** 9.172 zuvor geflaggte Aufnahmen plus 500 zufällige Kontrollen. Unmittelbar vor Veröffentlichung wurden alle 9.672 Wetterdateien nochmals gegen die Prüfsummen dieses aktuellen Audits geprüft. Die übrigen 102.194 bisher ungeflaggten Wetterdateien wurden nicht neu gelesen; ihre Inventarergebnisse wurden erhalten. Daher ist die Verfügbarkeit aller 111.866 Dateien eine Inventaraussage, keine neue Vollprüfung aller Dateien. Die Wetterwerte wurden nicht nochmals vollständig mit den NetCDF-Quelldaten verglichen.

## Kontrollierter Abschluss des alten Laufs

Der alte Workflow vom 17. September hatte noch zehn wartende Jobs, darunter zwei mit DependencyNeverSatisfied. Die vom Nutzer bereitgestellte squeue-Ausgabe enthielt keine laufenden Jobs. Der Nutzer hat genau diese zehn Jobs abgebrochen und danach eine leere Queue bestätigt. Erst danach wurde der alte Lock archiviert und ein eigener Veröffentlichungs-Lock erworben. Dieser wurde nach erfolgreicher Veröffentlichung freigegeben.

Die hängen gebliebenen Bioakustik-Schritte wurden dadurch nicht nachträglich ausgeführt. Es wurde kein neuer Clusterjob gestartet. Ihr Abschluss bleibt eine separate Aufgabe.

## Was unverändert blieb

IDs, Zeilenreihenfolge, Aufnahmezeiten, Koordinaten, LRT-/Grid-Zuordnungen, Audio, Fotos, Sentinel, Grid-Wetterflags und Bioakustikfelder bleiben unverändert. Nur die geprüften Punktwetterfelder und davon abhängige Gesamt-/Bereitschaftsstatus wurden aktualisiert; keine Quelle wurde neu eingelesen und keine Aufnahme herausgefiltert. CSV und Parquet sind nach äquivalenter Leerwert-/Null-Normalisierung inhaltlich gleich.

7.085 Zeilen haben Statusänderungen: die 6.513 vorherigen Zeitfehler und 572 zuvor fehlenden Dateien. Dass nur 6.557 Issue-Flags verschwinden, ist kein Widerspruch: Ein Teil dieser Zeilen bleibt wegen missing_value geflaggt. 35.720 Feldänderungen wurden in die bestehenden Statusereignisse aufgenommen.

## ci-tec-README und Filter

Das [aktualisierte ci-tec-README](../../README_CI_TEC.md) und seine [dreiseitige PDF](../../README_CI_TEC.pdf) beziehen sich jetzt auf die gemeinsame vollständige Master, statt auf einen separaten Kurzexport. Alle 18 verschiedenen relevanten Codes der vorgefundenen Master sind erklärt; weitere typische Diagnosepräfixe sind ergänzt. Hinweise, fehlende Daten, technische Probleme und offene Prüfungen sind mit ihrer jeweiligen Konsequenz beschrieben.

- Dauerabweichung allein ist ein anwendungsabhängiger Hinweis, kein allgemeiner Audioausschluss.
- Audiofilter: Datei vorhanden; keine Codes bei negativem Issue-Flag oder ausschließlich duration_not_60s. Unbekannte/zusätzliche Codes prüfen.
- Strenger Wetterfilter: Datei vorhanden, kein Issue-Flag und keine Codes. Optional ausschließlich missing_value zulassen und dann benötigte Werte selbst prüfen.
- Fotos sind für die genannten Prioritäten kein Ausschlusskriterium; Sentinel und Wetter sperren reine Audio-/LRT-Auswertungen nicht automatisch.
- Grid-Embeddings und die Vollständigkeit separater Gridprodukte werden durch Aufnahmeflags nicht zertifiziert.
- is_final wurde nicht erfunden: Die Spalte existiert nicht. Ein Vorschlag zur Trennung von Verarbeitungsabschluss und Qualität steht im README. Eine dauerhaft unveränderliche Freigabe setzt einen eingefrorenen, versionierten Stand voraus. Die Nutzungskriterien sind Vorschläge zur fachlichen Abstimmung.

Die lokalen Refresh-Starter erzeugen keinen automatischen zweiten ci-tec-Kurzexport mehr. Der manuelle Altexport bleibt verfügbar; vorhandene ältere Kopien wurden nicht gelöscht. Diese Code-/Dokumentationsänderungen sind lokal und wurden nicht auf Git oder in den Horeka-Codecheckout übertragen. Das README liegt als Lieferdatei lokal; die LSDF-Veröffentlichung umfasste die sieben Daten-/Statusprodukte.

## Vor dem nächsten kompletten Pipeline-Lauf

Die beim Audit vorgefundene ursprüngliche LSDF-Eingabedatei enthielt nur eine Aufnahme. Der vollständige Wetter-/Masterabgleich nutzte die 111.866 bereits bereinigten Metadaten, deren Prüfsumme vor Veröffentlichung kontrolliert wurde. Vor einem neuen Gesamt- oder add_new_ids-Lauf muss geklärt werden, ob wieder die vollständige beabsichtigte Quelldatei vorliegt. Dieser Auftrag hat die Quelldatei nicht ersetzt.

## Sicherung und Nachweise

Sicherungsverzeichnis auf LSDF: `{published['backup_directory']}`. Dort liegen alle ersetzten Dateien mit ihren bisherigen Inhalten, der archivierte alte Lock und das Veröffentlichungsprotokoll.

- [Veröffentlichung und Ziel-Prüfsummen](publish_result.json)
- [Änderungen je ID und Feld](master_change_log.csv)
- [Aktuelle Wetterprüfung](current_weather_checks.csv)
- [Validierung der vorbereiteten Master](prepared_validation.json)
- [Abgleich der ursprünglichen Uploadkandidaten](preflight_summary.json)

Die frühere lokale Kürzung und ihr Bericht bleiben als historischer Auditstand erhalten; für die aktuelle Lage gilt dieser Bericht.
'''
    (OUT/'BERICHT.md').write_text(report,encoding='utf-8')
    print(OUT/'BERICHT.md')


if __name__=='__main__':
    main()
