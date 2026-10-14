"""Germany recording-time policy, shared by extraction and cache planning."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

import pandas as pd

TIME_POLICY_VERSION = "german-local-priority-mislabeled-utc-wall-v4-qc"
LEGACY_TIME_POLICY_VERSION = "german-local-priority-utc-fallback-v2"
GERMAN_TIMEZONE = "Europe/Berlin"
UTC = dt_timezone.utc


def text_or_empty(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def parse_iso(value: str) -> datetime | None:
    try:
        # The input contract is ISO 8601; do not guess day/month ordering.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return None


def german_wall_times(values: pd.Series) -> pd.Series:
    """Read canonical aware timestamps or timezone-free German master clocks."""
    result = []
    for value in values:
        try:
            timestamp = pd.Timestamp(value)
            if pd.notna(timestamp) and timestamp.tzinfo is not None:
                timestamp = timestamp.tz_convert(GERMAN_TIMEZONE).tz_localize(None)
        except (ValueError, TypeError):
            timestamp = pd.NaT
        result.append(timestamp)
    return pd.to_datetime(pd.Series(result, index=values.index), errors="coerce")


def resolve_recording_time(local_value, utc_value, timezone: str = GERMAN_TIMEZONE) -> dict:
    """Respect localtimes, then repair Dawn Chorus zero-offset-labeled fallback clocks.

    A local offset can disambiguate the autumn fold only if valid in Germany.
    Otherwise a matching UTC reference may resolve it. Invalid/nonexistent or
    unresolved ambiguous local values never silently fall back or shift.
    """
    if timezone != GERMAN_TIMEZONE:
        raise ValueError("Germany recordings require timezone Europe/Berlin")
    zone = ZoneInfo(timezone)
    local_raw, utc_raw = text_or_empty(local_value), text_or_empty(utc_value)
    reference = parse_iso(utc_raw)
    # Explicit +00:00/Z on the Dawn Chorus fallback often labels a German
    # *wall clock*, not a real UTC instant (website-verified examples).
    # Preserve the genuine UTC reference semantics when localtimes exists.
    mislabeled_zero_offset = (not local_raw and reference is not None
                              and reference.tzinfo is not None
                              and reference.utcoffset().total_seconds() == 0)
    issues = []
    if reference is not None and reference.tzinfo is None:
        # A timezone-free reference cannot establish a reliable UTC instant.
        reference = reference.replace(tzinfo=UTC)
        issues.append("datetime_timezone_missing_assumed_utc")
    reference = reference.astimezone(UTC) if reference is not None else None
    chosen = None
    resolution = ""
    local = parse_iso(local_raw) if local_raw else None
    if local_raw:
        source = "localtimes"
        if local is None:
            issues.append("localtimes_unparseable")
        else:
            wall = local.replace(tzinfo=None)
            candidates = {}
            for fold in (0, 1):
                candidate = wall.replace(tzinfo=zone, fold=fold)
                instant = candidate.astimezone(UTC)
                if instant.astimezone(zone).replace(tzinfo=None) == wall:
                    candidates[instant] = candidate
            if not candidates:
                issues.append("nonexistent_localtime")
            elif len(candidates) == 1:
                chosen = next(iter(candidates.values()))
                resolution = "local_walltime"
            else:
                matching_offset = [c for c in candidates.values()
                                   if local.tzinfo is not None and c.utcoffset() == local.utcoffset()]
                matching_reference = [c for instant, c in candidates.items()
                                      if reference is not None and
                                      instant.replace(microsecond=0) == reference.replace(microsecond=0)]
                if len(matching_offset) == 1:
                    chosen = matching_offset[0]
                    resolution = "autumn_fold_from_valid_local_offset"
                elif len(matching_reference) == 1:
                    chosen = matching_reference[0]
                    resolution = "autumn_fold_from_matching_utc"
                else:
                    issues.append("ambiguous_localtime_unresolved")
            if chosen is not None and local.tzinfo is not None and local.utcoffset() != chosen.utcoffset():
                issues.append("localtimes_offset_mismatch")
        if reference is None:
            issues.append("utc_reference_unavailable")
    else:
        source = "datetime"
        if reference is None:
            issues.append("datetime_missing_or_unparseable")
        elif mislabeled_zero_offset:
            # The +00:00 annotation on the source is not trusted in this
            # case. Interpret its clock fields as Germany local time, then
            # determine real UTC *after* localizing. Never pick a DST fold.
            wall = parse_iso(utc_raw).replace(tzinfo=None)
            candidates = {}
            for fold in (0, 1):
                candidate = wall.replace(tzinfo=zone, fold=fold)
                instant = candidate.astimezone(UTC)
                if instant.astimezone(zone).replace(tzinfo=None) == wall:
                    candidates[instant] = candidate
            if not candidates:
                issues.append("nonexistent_localtime")
            elif len(candidates) != 1:
                issues.append("ambiguous_localtime_unresolved")
            else:
                chosen = next(iter(candidates.values()))
                resolution = "datetime_zero_utc_label_interpreted_as_German_walltime"
            # Source provenance is distinct from time validity. This
            # zero-offset-labeled German clock is now consistently interpreted
            # as Europe/Berlin, so do not flag it only because localtimes
            # was missing. Invalid DST folds/gaps are still flagged above.
        else:
            chosen = reference.astimezone(zone)
            resolution = "datetime_offset_instant_to_Europe/Berlin"
            # A genuine nonzero offset is an explicit, parseable instant;
            # using datetime as a source is not by itself a data-quality issue.

    if not resolution and mislabeled_zero_offset:
        resolution = "datetime_zero_utc_label_unresolved_German_walltime"

    difference = None
    if chosen is not None and reference is not None:
        # Products have whole-second precision; ignore source subsecond noise.
        difference = int((chosen.astimezone(UTC).replace(microsecond=0)
                          - reference.replace(microsecond=0)).total_seconds())
        if local_raw and difference:
            issues.append("utc_local_conflict")
    return {
        "datetime_clean": chosen.isoformat(timespec="seconds") if chosen is not None else pd.NA,
        "datetime_source": source,
        "conversion_needed": chosen is not None,
        "conversion_step": resolution or "unresolved_localtime_no_fallback" if local_raw else resolution or "no_parseable_datetime",
        "timestamp_status": "invalid" if chosen is None else "warning" if issues else "validated",
        "timestamp_issue_codes": "|".join(issues),
        "datetime_utc_reference": reference.isoformat(timespec="seconds") if reference is not None else pd.NA,
        "selected_minus_reference_seconds": difference,
        "time_policy_version": TIME_POLICY_VERSION,
    }
