-- ARGUS_PLAN.md Phase 8 named "Report generator (Markdown/PDF export)" and
-- left it deferred. Phase 10's evidence-and-calibration migration (010) built
-- the export custody chain — hash, per-access logging, classification,
-- retention — for two formats: json for a machine, html for a person. Neither
-- was ever markdown or pdf, so the deferred box stayed unchecked underneath a
-- system that could have carried it the whole time.
--
-- This adds the other two formats to the same custody chain rather than
-- building a second export path for them: same table, same hash-on-creation,
-- same per-read logging including refused reads, same retention schedule.
-- A report is not a lesser kind of artifact than an investigation export —
-- it is one, so it gets the same guarantees.

ALTER TABLE exports DROP CONSTRAINT exports_format_valid;
ALTER TABLE exports ADD CONSTRAINT exports_format_valid
    CHECK (format IN ('json', 'html', 'markdown', 'pdf'));
