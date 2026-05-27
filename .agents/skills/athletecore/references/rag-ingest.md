# RAG ingest (methodology books)

## Pipeline

1. Place PDF in `book sources/`
2. Run `scripts/parse_badminton_pdf.py` → `output/<name>.md`
3. `docker compose up -d qdrant`
4. Run `scripts/ingest_methodology_qdrant.py --recreate`
5. Analyst / MCP `search_sports_methodology` → Qdrant (fallback: lexical)

## Chunking (ingest)

- Split on `<!-- page N -->` from LlamaParse
- Sub-chunks: ~900 tokens, overlap 120 (`METHODOLOGY_CHUNK_TOKENS`)
- Strip fliphtml5 junk lines before embed

## Embeddings & store

- Model: `text-embedding-3-small` (1536d)
- Collection: `sports_methodology` @ `QDRANT_URL`

## Large PDFs (>50 MB)

- `--target-pages "31-40" --append` (10-page batches)
- Pages 31+: often `--no-multimodal`; multimodal may use `openai-gpt-4o-mini`

## Health check

`GET /health` → `methodology_rag: qdrant`, `methodology_vectors` > 0
