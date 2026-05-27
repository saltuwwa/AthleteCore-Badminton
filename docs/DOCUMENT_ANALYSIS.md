# Document analysis (chat attachments)

## Pipeline

```text
upload → extract text/tables → sanitize → injection scan → parse entities
  → Gemini (safe prompt, UNTRUSTED blocks) → episodic memory (structured only)
```

## Security

- All extracted content is **UNTRUSTED DATA** — never instructions.
- Injection lines redacted; `security_flag=prompt_injection_detected` when needed.
- Raw document text is **not** stored in LTM.

## API

- `POST /api/documents/upload`
- `POST /api/documents/analyze` — `action`: `parse_results` | `find_my_matches` | `compare_past`

## Memory

`event_type`: `competition_document_analysis`  
Key: `competition.document.{document_id}`

Payload: tournament, matches, scores, rounds, insights, recommendations (structured).
