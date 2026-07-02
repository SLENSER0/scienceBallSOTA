// GENERATED — range/property indexes (§3.11)
CREATE INDEX measurement_value_index IF NOT EXISTS FOR (m:Measurement) ON (m.value_normalized);
CREATE INDEX processing_temperature_index IF NOT EXISTS FOR (r:ProcessingRegime) ON (r.temperature_c);
CREATE INDEX processing_time_index IF NOT EXISTS FOR (r:ProcessingRegime) ON (r.time_h);
CREATE INDEX evidence_review_index IF NOT EXISTS FOR (e:Evidence) ON (e.review_status);
CREATE INDEX gap_type_index IF NOT EXISTS FOR (g:Gap) ON (g.gap_type);
CREATE INDEX paper_year_index IF NOT EXISTS FOR (p:Paper) ON (p.year);
CREATE INDEX tech_practice_index IF NOT EXISTS FOR (t:TechnologySolution) ON (t.practice_type);
