# graph-llm

Compact demo and utilities for converting documents into a Neo4j graph and querying it with an LLM-backed QA chain.

Contents

- `main.py` — demo: convert short text into graph documents, ingest `movies_small.csv`, and create a `GraphCypherQAChain`.
- `main2.py` — fuller example: PDF ingestion pipeline, safe Cypher wrapper, transform chunks into graph documents, and run a sample query.
- `pdf_utils.py` — PDF -> text extraction helper using MarkItDown.
- `notes.md` — design notes, architecture diagrams, data model, and troubleshooting ([notes.md](notes.md#L1)).

Requirements

- Python 3.9+
- See `requirements.txt` for exact packages and versions.

Environment
Create a `.env` file in the project root with the following variables (example):

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
GROQ_API_KEY=sk-xxxx
```

Quickstart

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Populate `.env` with your Neo4j credentials and Groq API key.

3. Option A — ingest the sample movies CSV and create the graph schema:

```bash
python main.py
```

3. Option B — ingest a PDF and run the example query (edit `main2.py` to point to your PDF):

```bash
python main2.py
```

Notes & safety considerations

- `main2.py` installs a safe wrapper around `graph.query` that blocks non-Cypher outputs from the LLM and writes them to `generated_cypher_debug.txt` to avoid sending arbitrary text to Neo4j.
- On LLM-to-graph conversion failures, `main2.py` writes chunk error files like `groq_chunk_error_{idx}_{ts}.txt` so you can inspect inputs and tracebacks.

Troubleshooting

- Neo4j connection errors: check `NEO4J_URI`, credentials, and that the DB is running.
- MarkItDown failures extracting PDFs: verify `markitdown` is installed and the PDF file is readable.
- LLM errors or rate limits: inspect network errors and your Groq quota; add retries/backoff if needed.

Next steps

- Add token-based chunking, retry/backoff for LLM calls, and unit tests for `pdf_utils` and `safe_query`.
- See [notes.md](notes.md#L1) for architecture diagrams and more details.

License
This repo contains examples and is provided as-is. Add a license if you plan to redistribute.
