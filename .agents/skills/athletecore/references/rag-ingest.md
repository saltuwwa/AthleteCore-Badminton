# RAG ingest (methodology books)

## Current pipeline

1. Place PDF in `book sources/`
2. Run `scripts/parse_badminton_pdf.py` → `output/<name>.md`
3. MCP `search_sports_methodology` indexes `output/*.md` automatically (in-memory chunks)

## Large PDFs (>50 MB)

- Use `--max-pages` or `--target-pages "1-40"` + `--append`
- Prefer `--multimodal-model gemini-2.0-flash` + `GOOGLE_API_KEY` if OpenAI multimodal fails

## Future (TZ)

- Chunk 512 / overlap 64
- Qdrant collection `sports_methodology`
- Analyst node dual retrieval: LTM + methodology

## Files on disk

- `output/Badminton-Footwork-Pocket-eBook_compressed-V2.md` — full
- `output/Badminton handbook Pages.md` — partial batches OK
