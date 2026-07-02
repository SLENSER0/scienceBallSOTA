// Smoke-check APOC + GDS are loaded (§3.9).
RETURN apoc.version() AS apoc, gds.version() AS gds;
