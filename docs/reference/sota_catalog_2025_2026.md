# §23.35 — SOTA papers-with-code (2025–2026) catalog

Reference catalog for the §23.35 deliverable: a curated list of 2025–2026 state-of-the-art
work **with public code or open weights**, mapped onto our subsystems for one of three
purposes:

- **adopt** — vendor / integrate under §21 (vendoring workflow + LICENSE check).
- **benchmark** — compare against in §23.31 / §18.11 as a baseline or leaderboard.
- **reference** — architectural pattern to learn from; **do not vendor as-is**.

## Purpose & provenance

This catalog is the distilled output of a targeted SOTA scan across our subsystems, produced by
a deep-research pass: **5 research angles → 25 sources → 121 extracted claims → 3-vote
adversarial verification**. Only work with a public repository or open weights was kept. The
canonical, checkbox-tracked version lives in the task file at
[`docs/FULL_SYSTEM_TASKS_science_ball.md` §23.35](../FULL_SYSTEM_TASKS_science_ball.md); this
document is the flattened, reviewer-friendly view.

## How to read the rows

Each entry carries: **name**, **repo / source**, **license**, **arXiv id / reference**,
**status badge**, a **one-line description**, and an **"→ integrates at §X.Y"** mapping to our
sections.

Honesty rules baked into this catalog (do not silently "fix" these downstream):

- **arXiv ids are as reported** by the deep-research pass — *validate before vendoring*. Some are
  flagged **unconfirmed** where the fetch did not confirm the paper/repo details.
- **⚠ marks a licensing/availability risk**: no license (all-rights-reserved), non-commercial,
  a closed component in the pipeline, or unconfirmed status. ⚠ items are **NOT vendored as-is** —
  only used as `reference` or replaced by an open-weight analogue (§23.33).
- **License policy is open-source-only.** Permitted licenses (project rule §7.5 /
  [`docs/LICENSES.md`](../LICENSES.md)): **AGPLv3 / GPLv3 / LGPLv3 / EPL / MPL / Apache-2.0 / MIT**
  (permissive BSD/ISC treated as MIT-class), reinforced for models by the §23.33 open-weight
  allowlist. Non-permissive or unknown licenses → not vendored, `reference` or open-weight
  replacement only.

---

## Document parsing & multimodal (§5 / §23.34)

| Name | Repo / source | License | arXiv / ref (as reported) | Status | Description | Integrates at |
|---|---|---|---|---|---|---|
| Docling | github.com/docling-project/docling | MIT | 2408.09869 | **adopt** | IBM / LF AI & Data. PDF/DOCX/PPTX/HTML → structured (layout, reading order, tables, formulas); exports Markdown/HTML/JSON/DocTags; VLM GraniteDocling/SmolDocling for figures; LangChain/LlamaIndex/Haystack integrations. Pin as the primary parser. | → §5 (main parser), §23.34 |
| MinerU 2.5 | github.com/opendatalab/MinerU | open weights (license per source) | 2509.22186 | **adopt/benchmark** | 1.2B VLM. Decoupled layout → native-resolution recognition; SOTA on OmniDocBench (MinerU2.5-Pro 95.75 / MinerU2.5 93.04) at low compute. VLM parser for formulas/tables. | → §23.34 |
| olmOCR 2 | github.com/allenai/olmocr | Apache-2.0 | 2510.19817 | **adopt/benchmark** | AllenAI. olmOCR-2-7B-1025 on Qwen2.5-VL-7B, trained with RLVR. 82.4 olmOCR-Bench (vs GPT-4o 68.9, MinerU2.5 75.2, Marker 76.1); leads on formulas/tables/multi-column. For OCR-heavy scans. | → §23.34, §23.17 |
| OmniDocBench | github.com/opendatalab/OmniDocBench | Apache-2.0 | 2412.07626 (CVPR2025) | **adopt** | 1651 pages, 10 document types; end-to-end / OCR / table / formula / layout tasks; TEDS / CDM / edit-distance metrics; leaderboard MinerU/olmOCR/Marker/Docling/Nougat + open VLMs (Qwen2-VL-72B 89.78, InternVL2-76B). Parsing acceptance gold. | → §18.11, §23.31 |
| PaddleOCR-VL + formula-extraction benchmark (leads) | (PaddleOCR-VL 0.9B VLM) | not stated | 2510.14528; 2512.09874 | **reference** | ⚠ Leads only — the deep-research fetch did **not confirm** details; validate before vendoring. | → §23.34 |

---

## KG-extraction — schema-guided, evidence-span (§6)

| Name | Repo / source | License | arXiv / ref (as reported) | Status | Description | Integrates at |
|---|---|---|---|---|---|---|
| llm-ie | github.com/daviden1013/llm-ie | ⚠ **none (all-rights-reserved)** | DOI 10.1093/jamiaopen/ooaf012 (JAMIA Open 2025) | **reference** | NER / attribute / relation pipelines; char-level span-grounding (matches our "no span → no fact", §6.10); backends OpenRouter/vLLM/Ollama/HF/LiteLLM, configs for Qwen3/GPT-OSS. Adopt the pattern, do **not** vendor as-is. | → §6, §6.10 |
| OneKE | github.com/zjunlp/OneKE | not stated (verify) | WWW 2025 | **adopt/reference** | Dockerized schema-guided LLM-agent knowledge extraction. | → §6.9, §6.13 |
| KARMA | (repo not confirmed) | not confirmed | 2502.06472 (NeurIPS2025 spotlight) — unconfirmed | **reference** | 9-agent schema-guided extraction + verification (83.1% LLM-verified, −18.6% conflict edges, 1200 PubMed). Eval is biomed, not materials; repo/license/backbones **not confirmed**. | → §6.13 (orchestration), §13.16 (verifier) |
| GLiNER-Relex | (over GLiNER) | not stated | 2605.10108 | **reference / lead** | Joint NER + RE on top of GLiNER (GLiNER already in §6.7). | → §6.7 |
| Anchor-constrained grounded KG extraction | MDPI Computers 15/3/178 | not stated | MDPI Computers 15/3/178 | **reference** | Provenance-anchored extraction pattern. | → §3.7 |
| Survey: LLM-empowered KG Construction | — (no code) | n/a | 2510.20345 | **reference** | Taxonomy schema-based vs schema-free; ontology → extraction → fusion. No code. | → §6 |

---

## Materials NER / ER / units (§7 / §8 / §20.9)

| Name | Repo / source | License | arXiv / ref (as reported) | Status | Description | Integrates at |
|---|---|---|---|---|---|---|
| MatKG | Nature Sci Data | (dataset) | s41597-024-03039-z | **adopt** (ontology/types) | MatBERT-NER, MatScholar schema: 7 types (Material/Property/Application/Synthesis/Characterization/Descriptor/Symmetry); ~2M triplets, TransE embeddings MRR 0.49. ⚠ relations are **co-occurrence, not span-grounded** → do **not** use as evidence. | → §3.2, §20.9 |
| Symbol/entity-marker + LLM | (datasets on HF) | open-weight | 2505.05864 | **adopt** (pattern) | Hybrid encoder+CRF NER → generative structuring; **+58% entity-F1 / +83% relation-F1** vs direct LLM; all open-weight (Llama-3.3-70B, Llama-3.2-3B, MatSciBERT/MatBERT+CRF; Ollama/llama.cpp/Unsloth). SOTA on MatScholar/SOFC/SOFC-Slot. Two-phase extraction pattern. | → §6.13 |
| grobid-quantities | github.com/kermitt2/grobid-quantities | Apache-2.0 | (GROBID module) | **adopt** | CRF + SI normalization; input PDF/XML/text. Complement to `pint` for quantity parsing + SI conversion. | → §7 |
| LELA | (repo "to be released") | open-weight; ⚠ code TBD | 2601.05192 | **reference** | Zero-shot entity linking, 83.11 ZESHEL (+8.84 pp over SOTA), 62.3 GLADIS; open-weight (Magistral-Small-2509, Qwen3-30B-A3B/4B, Qwen3-Reranker/Embedding-4B); BM25/dense → pointwise rerank → self-consistency. ⚠ code "to be released" — verify. | → §8 (ER) |
| Backbones: MatSciBERT / MatBERT / MaterialsBERT / LLaMat(-Chat) | (model hubs) | per model (verify) | — | **reference** (candidates) | Backbones / baselines for materials NER. | → §20.9 |

---

## GraphRAG / retrieval (§11 / §12)

| Name | Repo / source | License | arXiv / ref (as reported) | Status | Description | Integrates at |
|---|---|---|---|---|---|---|
| LightRAG | github.com/HKUDS/LightRAG | MIT | 2410.05779 (EMNLP2025) | **adopt/benchmark** | Dual-level graph+vector retrieval, 5 modes (local/global/hybrid/naive/mix); backends **Neo4j/Qdrant/OpenSearch/Milvus/PG**, bge-m3; win-rate vs NaiveRAG 60–85%, ~parity with MS GraphRAG. Light alternative to GraphRAG. | → §11.12, §12 |
| HippoRAG 2 | github.com/OSU-NLP-Group/HippoRAG | MIT | 2502.14802 (ICML2025) / 2405.14831 (NeurIPS2024) | **adopt/benchmark** | KG + Personalized PageRank "long-term memory", non-parametric continual learning; vLLM open-weight (Llama-3.3-70B), NV-Embed-v2/GritLM/Contriever. Graph-proximity / memory. | → §12.5 |
| PathRAG | github.com/BUPT-GAMMA/PathRAG | MIT | 2502.14902 | **benchmark/adopt** | Flow-pruned relational-path retrieval → text for LLM; Qwen/Ollama/vLLM; beats graph-RAG baselines on 6 datasets. | → §12.2, §12.5 |
| KAG | github.com/OpenSPG/KAG | Ant / OpenSPG (verify) | — | **benchmark/reference** | Knowledge-augmented generation for professional domains. | → §11, §12 |

---

## Faithfulness / hallucination / contradiction (§13.16 / §15 / §18)

| Name | Repo / source | License | arXiv / ref (as reported) | Status | Description | Integrates at |
|---|---|---|---|---|---|---|
| PaperQA2 / ContraCrow | github.com/Future-House/paper-qa | (verify) | 2409.13740 | **reference** | Agentic scientific QA ("superhuman synthesis"), contradiction detection 2.34/paper (70% human-validated), benchmark **LitQA2**, cited answers. | → §13 (agent), §15 (contradictions), §23.29 (evidence pack) |
| HalluMatDetector / HalluMat | (materials-specific) | (verify) | 2512.22396 | **reference** | Contradiction-graph (Louvain over semantic similarity) + hybrid FAISS+BM25+NLI (Entail/Neutral/Contradict), −30% hallucinations; benchmark **HalluMatData** (2629 queries) + PHCS metric. | → §15, §13.16 (verifier) |
| FaithJudge / HHEM | github.com/vectara/FaithJudge | (verify) | 2505.04847 (EMNLP2025 Industry) | **benchmark** | LLM-as-judge faithfulness leaderboard over 46 models (Llama/Qwen/Mistral) for summarization/QA/data-to-text. ⚠ judge is **closed o3-mini** → replace with an open-weight judge (§23.33). | → §18, §23.31 |
| FRANQ | github.com/stat-ml/rag_uncertainty | ⚠ **none** | 2505.xxxxx — unconfirmed | **reference** | Claim-level factuality-vs-faithfulness UQ + LFQA dataset with dual annotation. | → §13.16 |

---

## Open-weight models for the allowlist (§23.33)

Candidate open-weight/open-source models to register in the §23.33 allowlist (each still needs an
OpenRouter id + confirmed license per §7.5 before use):

- **LLM:** Llama-3.3-70B / 3.1-8B, Qwen2.5 / Qwen3 (30B-A3B, 4B), Mistral / Magistral-Small-2509, DeepSeek, GPT-OSS.
- **VLM (parsing / figures):** Qwen2.5-VL-7B, olmOCR-2-7B-1025, MinerU2.5 (1.2B), InternVL2, GraniteDocling/SmolDocling, PaddleOCR-VL (0.9B).
- **Embeddings / rerankers:** BAAI/bge-m3, Qwen3-Embedding-4B, Qwen3-Reranker-4B, NV-Embed-v2, GritLM, Contriever.
- **Materials backbones:** MatSciBERT, MatBERT, MaterialsBERT, LLaMat / LLaMat-Chat.

> Note: some Llama-family / Gemma weights are **excluded** from our runtime by §7.5 /
> [`docs/LICENSES.md`](../LICENSES.md) (Llama Community / Gemma licenses are not on the permitted
> list). Where a paper's SOTA depends on such a backbone, use it as a `reference` and substitute a
> permitted open-weight model (Qwen/Mistral/DeepSeek) in our runtime.

---

## Benchmarks / datasets for golden & eval (§18.6 / §23.31)

| Dataset | Track | Caveat | Integrates at |
|---|---|---|---|
| OmniDocBench | Parsing | — | → §18.11, §23.31 |
| olmOCR-Bench | Parsing (OCR) | — | → §23.31 |
| SciNLP | Extraction | ⚠ **CC BY-NC** (non-commercial) | → §18.6 |
| MatSciNLP | Extraction | — | → §18.6 |
| LitQA2 | Scientific QA | — | → §23.31 |
| MACBENCH | QA | — | → §23.31 |
| LLM4Mat-Bench | QA | — | → §23.31 |
| FaithJudge / HHEM | Faithfulness | ⚠ closed o3-mini judge → open-weight judge | → §18, §23.31 |
| HalluMatData | Faithfulness (materials) | — | → §15, §23.31 |
| ZESHEL | Entity linking | — | → §8 |
| GLADIS | Entity linking | — | → §8 |
| MatScholar | Corpus / NER | — | → §20.9 |

---

## Already in our build

Several `adopt` items overlap what the current build already ships or wires — these are
partial/existing, so integration means extending rather than greenfielding:

- **Docling** — already our §5 document-ingestion parser (Docling Serve, `DOCLING_SERVE_URL`);
  §23.35 pins it as the primary parser and adds the VLM figure path (§23.34).
- **GLiNER** — already vendored and wired as the flexible-NER extractor in **§6.7**
  (`packages/kg_extractors/gliner`); GLiNER-Relex is the joint NER+RE lead on top of it.
- **bge / embeddings** — bge-class embedding & reranker models already used in **§4** search
  (dense embeddings + `BAAI/bge-reranker-*` cross-encoder candidates); the allowlist adds bge-m3 /
  Qwen3-Embedding-4B for GraphRAG parity.
- **LightRAG backends** — our live **server profile already runs Neo4j + Qdrant + OpenSearch**
  stores, which exactly match LightRAG's supported backends → LightRAG can be benchmarked against
  our own retrieval without new infra.
- **pint** — already the §7 units/quantity engine; **grobid-quantities** (Apache-2.0) is the
  `adopt` complement for CRF-based quantity extraction + SI normalization.

---

## Acceptance / governance (mirrors §23.35)

- Every **adopt** item is registered in §21 (vendoring method + LICENSE check) and has an
  integration task in its owning section.
- Every **benchmark** item is wired into §23.31 as a baseline/leaderboard with a reproducible run.
- **⚠ items** (no license / non-commercial / closed component / unconfirmed) are **NOT vendored
  as-is** — used only as `reference` or replaced by an open-weight analogue (§23.33).
- The catalog is revisited whenever the ontology or the model set changes.
