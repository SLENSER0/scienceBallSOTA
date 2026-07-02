// GENERATED — fulltext index (§3.12)
CREATE FULLTEXT INDEX entity_name_index IF NOT EXISTS FOR (n:Material|Property|Equipment|Lab|Person|ProcessingRegime|TechnologySolution) ON EACH [n.name, n.canonical_name, n.aliases_text];
CREATE FULLTEXT INDEX evidence_text_index IF NOT EXISTS FOR (n:Evidence|Claim) ON EACH [n.text];
