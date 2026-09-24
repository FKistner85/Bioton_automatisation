"""Summarize the local read-only review and verify every staged file checksum."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/weather_review'


def main():
    checks = pd.read_csv(OUT/'weather_checks.csv', dtype=str, keep_default_na=False)
    repairs = pd.read_csv(OUT/'staged_repair_manifest.csv', dtype=str, keep_default_na=False)
    audit = json.loads((OUT/'audit_summary.json').read_text())
    summary = json.loads((OUT/'repair_summary.json').read_text())
    other = json.loads((OUT/'other_domain_summary.json').read_text())
    master = pd.read_csv(OUT/'snapshot/Bio_O_Ton_Master.csv', dtype=str, keep_default_na=False)
    assert checks.dawn_chorus_id.is_unique and repairs.dawn_chorus_id.is_unique
    flagged = set(master.loc[master.weather_point_has_issues.str.lower().eq('true'), 'dawn_chorus_id'])
    assert flagged.issubset(set(checks.dawn_chorus_id))
    assert len(checks) == 9672 and len(flagged) == 9172
    for row in repairs.to_dict('records'):
        target = OUT/row['staged_file']
        assert hashlib.sha256(target.read_bytes()).hexdigest() == row['staged_sha256'], target
        source = OUT/'weather_cache'/target.name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row['source_sha256'], source
    for name, expected in audit['snapshot_sha256'].items():
        assert hashlib.sha256((OUT/'snapshot'/name).read_bytes()).hexdigest() == expected, name
    assert len(repairs) == summary['staged_files'] == 6267
    clean = int(repairs.staged_codes.eq('').sum())
    assert clean == summary['fully_clean_after_staging'] == 6241
    remaining = len(flagged)-clean
    checks['missing_hours_numeric'] = pd.to_numeric(checks.missing_hours, errors='coerce')
    checks['extra_hours_numeric'] = pd.to_numeric(checks.extra_hours, errors='coerce')
    action = checks[['dawn_chorus_id','datetime_local','old_codes','issues','classification','missing_hours','extra_hours']].copy()
    action['next_action'] = action.classification.map({'verified_clean':'control_verified', 'values_only':'investigate_missing_source_values', 'missing_file':'investigate_missing_file', 'time_or_structure_issue':'regenerate_correct_window'})
    action.loc[action.dawn_chorus_id.isin(repairs.dawn_chorus_id), 'next_action'] = 'staged_boundary_trim_requires_deployment_and_inventory_refresh'
    action.to_csv(OUT/'actions_by_id.csv',index=False)
    missing = checks.loc[checks.missing_hours_numeric.gt(0)]
    missing[['dawn_chorus_id','datetime_local','missing_hours','extra_hours','issues']].to_csv(OUT/'regenerate_time_window_ids.csv',index=False)
    checks.loc[checks.classification.eq('missing_file'),['dawn_chorus_id','datetime_local']].to_csv(OUT/'missing_weather_ids.csv',index=False)
    validation = {'snapshot_hashes_verified': len(audit['snapshot_sha256']), 'staged_and_original_cache_pairs_verified':len(repairs), 'all_flagged_master_ids_checked':True, 'controls':500,'control_failures':int((checks.loc[checks.control.str.lower().eq('true'),'classification']!='verified_clean').sum()),'expected_remaining_weather_flags_after_deployment':remaining,'master_unchanged':True,'lsdf_modified':False}
    (OUT/'final_validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    report = f'''# Wetterprüfung und lokale Korrekturen

Abschluss: 24. September 2026. Geprüfter LSDF-Datenstand: lokal am 23. September gesichert; Master vom 19. September, Wetterinventar und bereinigte Metadaten vom 17. September. Keine Aussage über spätere Änderungen auf LSDF.

## Ergebnis

Alle **9.172 Aufnahmen mit Wetterflags** wurden erneut geprüft, zusätzlich **500 zufällig ausgewählte Aufnahmen ohne Wetterflag**. Die 500 Kontrollen waren unauffällig. Die übrigen 102.194 bisher ungeflaggten Aufnahmen wurden nicht erneut an ihren Wetterdateien geprüft.

**6.267 Wetterdateien sind lokal korrigiert und nachgeprüft.** Je Datei wurde ausschließlich eine Stunde außerhalb des erwarteten Fensters entfernt. Alle erhaltenen Zeitstempel und Messwerte sind als CSV-Feldinhalte unverändert. Davon bestehen **6.241 Dateien alle implementierten Prüfungen**, bei **26 Dateien bleiben fehlende Messwerte**.

Nach Übernahme dieser Dateien und anschließendem Wetterinventar-/Master-Refresh könnten die Wetterflags von **9.172 auf {remaining:,}** sinken, also um **{clean / len(flagged):.1%}**. Das ist ein geprüftes lokales Ergebnis, **noch kein produktiver Zustand**. LSDF-Dateien und Master wurden nicht überschrieben. Eine Master mit bereits entfernten Flags würde derzeit den tatsächlichen LSDF-Dateistand falsch darstellen und wurde deshalb nicht ausgegeben.

## Ursachen, ohne Überschneidung gezählt

| Befund vor Korrektur | Aufnahmen | Ergebnis / nächster Schritt |
|---|---:|---|
| Eine zusätzliche Randstunde, Fenster über Frühjahrsumstellung | 6.267 | Lokal gekürzt; 6.241 danach ohne QC-Code, 26 weiterhin missing_value |
| Eine fehlende Stunde, Fenster über Herbstumstellung | 242 | Gezielte Neuerzeugung erforderlich; keine Stunde erfunden oder dupliziert |
| Fenster um einen Tag zu früh | 4 | Gezielte Neuerzeugung erforderlich; 24 Stunden fehlen und 24 sind überzählig |
| Nur fehlende Messwerte, Zeitfenster korrekt | 2.087 | Verfügbarkeit und Inhalt der Quelldaten prüfen; NaN ist kein Nachweis eines Downloadfehlers |
| Wetterdatei fehlt | 572 | Alle Aufnahmen aus 2026, vom 1. Mai bis 15. September; Ursache nicht aus dem Fehlen ableitbar |
| Kontrollfälle ohne ursprüngliches Wetterflag | 500 | Alle weiterhin unauffällig |

Die vier um einen Tag verschobenen Dateien gehören zu den IDs **9811988, 9812288, 9814106, 9814310**. Diese wurden nicht durch Umbenennen der Zeitstempel scheinbar repariert.

Die 6.513 Fälle mit `unexpected_time_interval` sind in diesem Datenstand **keine bloßen Fehlalarme durch eine zulässige Zeitumstellung**. Der unabhängige Kalendervergleich bestätigt echte Abweichungen vom Sollfenster: 6.267 zusätzliche Randstunden, 242 fehlende Stunden, vier verschobene Fenster. Der Code war zu unspezifisch erklärt; seine Beschreibung wurde präzisiert.

## Zeitbasis und Prüfmethode

- Alle 111.866 Masterzeiten stimmen mit den bereinigten Metadaten überein, nach Umrechnung der dortigen Zeitstempel nach Europe/Berlin. Keine Aufnahmezeit wurde geändert.
- Sollfenster: zehn vorhergehende vollständige deutsche Kalendertage plus vollständiger Aufnahmetag. Normal 264 Stunden, über den Frühjahrswechsel 263, über den Herbstwechsel 265 Stunden.
- Die produktive Inventarprüfung wurde auf lokalen Kopien ausgeführt. Ein unabhängiger Vergleich mit direkt konstruierten Kalendergrenzen bestätigte die erwarteten Zeitstempel einschließlich ihrer Häufigkeiten. Die doppelte Herbststunde wird ausdrücklich akzeptiert.
- Der Dateistand wurde beim Kopieren über Größe und Änderungszeit kontrolliert. Gesicherte Eingaben und lokale Wetterkopien sind mit SHA-256 dokumentiert. Sämtliche 6.267 Original-/Korrekturpaare wurden abschließend erneut gegen ihre Prüfsummen geprüft.
- Die Prüfung umfasst Lesbarkeit, Pflichtspalten, Zeitfenster, Stundenanzahl, fehlende Werte sowie die implementierten Wertebereichsprüfungen. Kein erneuter Abgleich sämtlicher Messwerte mit den HOSTRADA-NetCDF-Quelldaten; kein wissenschaftliches Qualitätsversprechen über diese Prüfungen hinaus.

## Master und Inventar sind unterschiedlich aktuell

Bei **1.582 IDs** unterscheiden sich die Codes in Master und gespeichertem Inventar. Die neue Dateiprüfung stimmt bei **allen 9.672 geprüften IDs** mit den Codes des gespeicherten Inventars überein. Ein Inventar-Refresh allein würde die Wetterflags daher hier nicht verringern; die Dateikorrekturen sind erforderlich. Die Code-Kombinationen im Master können sich beim anschließenden Refresh trotzdem ändern.

`recording_date_changed_recheck_required` kommt in der untersuchten LSDF-Master bei Wetter aktuell **keinmal** vor. Frühere Aussagen zu diesem Zwischenzustand betreffen einen anderen Stand. Die vier tatsächlich verschobenen Fenster tragen andere Zeitfehlercodes.

## Wichtiger separater Befund zur Eingabedatei

Die am 23. September unter `PointData/dawn-chorus-soundscape.csv` vorgefundene Datei enthält **nur eine Aufnahme (ID 31080426)**. Master und bereinigte Metadaten enthalten dagegen 111.866 Aufnahmen. Ob dies absichtlich eine Testdatei ist, wurde nicht geklärt. **Keinen vollständigen Metadaten-/add_new_ids-Lauf mit dieser Datei starten**, bevor wieder die beabsichtigte vollständige Eingabe vorliegt. Der Wetteraudit hat ausschließlich den vollständigen gesicherten Bestand verwendet.

## Andere große Flag-Zahlen richtig lesen

Diese Angaben stammen aus der Master; Audio, Fotos, Sentinel, Raster und Bioakustik wurden in diesem Auftrag nicht erneut physisch geprüft.

| Bereich | Geflaggte Aufnahmen | Einordnung |
|---|---:|---|
| Sound | 7.826 | 7.528 haben ausschließlich duration_not_60s. Das allein ist kein technischer Ausschlussgrund; 298 haben andere/zusätzliche Codes. |
| Fotos | 80.297 | 80.286 tragen missing_file; 80.283 photo_missing_photo_url. Diese Gruppen überlappen. Fehlende Fotos sperren nicht automatisch eine Audioauswertung. |
| Sentinel | 15.890 | Unter anderem 13.758 missing_file und 2.132 quality_score_missing. Bedarf separater Datei-/Score-Prüfung, kein pauschales Löschen der Flags. |
| HOSTRADA-Raster | 111.866 | Überall missing_raster. Ein globales Sammlungsflag wird auf jede Aufnahme kopiert; dies zählt nicht 111.866 unabhängig defekte Rasterdateien. |
| Bioakustik | 111.866 | Unter anderem required_models_incomplete, model_inference_failed und bioacoustic_result_missing. Diese Ausgabe ist ein eigener Pipelinebereich; Codes sind kein Beweis für unbrauchbare Originalaufnahmen. |

Auch `ready_for_general_analysis` ist kein allgemeines Nutzbarkeitsurteil: Der Code verlangt dabei gleichzeitig unauffällige Audio-, Wetter- und Sentinel-Daten. Für euren Workflow sind die benötigten Domänen und ihre konkreten Codes maßgeblich.

## Kleine Codeänderungen und Tests

1. Die unbenutzte zweite Wetterprüfung im Master-Skript entfernt: Dort war noch eine starre 24-Stunden-/3.600-Sekunden-Prüfung enthalten. Im regulären aktuellen Masterpfad wurde sie nicht aufgerufen; sie erklärt deshalb nicht die gemessenen Fehler. Wetterdateien werden weiterhin ausschließlich durch Step 5_1 geprüft.
2. Eine falsche 264-Stunden-Warnung im Wetterdownload auf die tatsächliche Länge des DST-korrekten Fensters umgestellt. Keine Änderung an extrahierten Messwerten.
3. Lokale, getrennte Audit- und Korrekturwerkzeuge ergänzt. Kürzung lehnt fehlende oder unerlaubt doppelte Sollstunden ab und bewahrt die erhaltenen CSV-Werte.
4. Tests für Wetterinventar, Wetterdownload-Auswahl, Mastertabelle, Dokumentationsreferenzen und die Randstunden-Korrektur erfolgreich ausgeführt. Sommer-/Winterzeitfälle und echte fehlende/duplizierte Stunden sind abgedeckt.

## Nächster produktiver Schritt

Zuerst den vollständigen Eingabestand klären. Für die Wetterkorrektur ist kein vollständiger Pipeline-Neulauf nötig: Die 6.267 vorbereiteten Wetterdateien können nach Vergleich der aktuellen LSDF-Dateien mit den Original-Prüfsummen gezielt ersetzt werden, mit Sicherung der alten Dateien. Anschließend Wetterinventar gegen die vollständigen Metadaten und Master gezielt aktualisieren. Dabei müssen abgeleitete Wetter-/Bereitschaftsstatus mitgeführt und unveränderte IDs, Koordinaten, Aufnahmezeiten und LRT-Zuordnungen bestätigt werden. Nur Flags im Master zu löschen wäre falsch.

Danach bleiben **{remaining} Wetterflags**: 2.113 Fälle mit fehlenden Messwerten, 246 mit fehlenden/verschobenen Stunden und 572 fehlende Dateien. Für die 246 Zeitfälle liegt eine konkrete ID-Liste zur gezielten Neuerzeugung vor. Die Datenquelle für fehlende Werte und fehlende Dateien wurde nicht erneut heruntergeladen.

## Dateien und Nachvollziehbarkeit

- [Prüfergebnisse je ID](weather_checks.csv): alte/neue Codes, Ist-/Sollfenster, fehlende und zusätzliche Stunden, Prüfsummen.
- [Nächste Maßnahme je ID](actions_by_id.csv): keine zweite Mastertabelle, sondern Auditliste.
- [Manifest der vorbereiteten Korrekturen](staged_repair_manifest.csv): Original- und Ziel-Prüfsumme sowie verbleibende Codes.
- `staged_weather/`: 6.267 korrigierte Dateien, ausschließlich lokal vorbereitet.
- [246 IDs für neue Zeitfenster](regenerate_time_window_ids.csv).
- [572 IDs ohne Wetterdatei](missing_weather_ids.csv).
- [Abschlussvalidierung](final_validation.json), [Auditübersicht](audit_summary.json), [Korrekturübersicht](repair_summary.json).
- `snapshot/`: gesicherte unveränderte Eingaben; `weather_cache/`: gelesene Original-Wetterdateien.

**Keine LSDF-Schreiboperation, kein Git-Push, kein Clusterjob und kein Austausch der produktiven Mastertabelle wurden ausgeführt.**
'''
    (OUT/'BERICHT.md').write_text(report,encoding='utf-8')
    print(json.dumps(validation,indent=2))


if __name__ == '__main__':
    main()
