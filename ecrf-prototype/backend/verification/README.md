# Independent verification

**This directory must not import from `ecrf/`.**

Every statistic the application reports is recomputed here from the raw
`observation` table, using plain SQL and arithmetic that shares nothing with
the pipeline. The dashboard shows both numbers side by side with a pass or
fail marker.

A shared helper would defeat the whole exercise: a bug inside it appears
identically in both answers, the comparison passes, and both numbers are
wrong. One number that only checks itself proves nothing.

This code may be slow and ugly. It is not production code, it is evidence.

Ideally a different team member writes and maintains this file.
