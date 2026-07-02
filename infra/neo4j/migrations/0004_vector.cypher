// GENERATED — vector index for :Entity embeddings (§3.13)
CREATE VECTOR INDEX entity_embedding_index IF NOT EXISTS FOR (n:Entity) ON (n.embedding) OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: 'cosine' } };
