#!/usr/bin/env python3
"""
Parse badminton sports-methodology PDFs to Markdown via LlamaParse.

Usage:
    python scripts/parse_badminton_pdf.py "book sources/example.pdf"
    python scripts/parse_badminton_pdf.py --max-pages 30 "book sources/large.pdf"

Requires LLAMA_CLOUD_API_KEY in backend/.env (or project .env).
Multimodal keys (BYOK, 1 credit/page):
  - openai-gpt-4o-mini  -> OPENAI_API_KEY
  - gemini-2.0-flash    -> GOOGLE_API_KEY or GEMINI_API_KEY
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from llama_parse import LlamaParse

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_INSTRUCTION_FILE = SCRIPT_DIR / "parsing_instruction.txt"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
WARN_SIZE_MB = 50
HARD_MAX_SIZE_MB = 300

# LlamaParse vendor multimodal model ids (see llamaindex multimodal docs)
MULTIMODAL_MODELS = (
    "openai-gpt-4o-mini",
    "openai-gpt-4o",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "anthropic-sonnet-3.5",
)


def load_env() -> None:
    """Load API keys from project .env files (does not override existing env)."""
    for env_path in (
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / "backend" / ".env",
    ):
        if env_path.is_file():
            load_dotenv(env_path, override=False)


def read_parsing_instruction(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Instruction file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Instruction file is empty: {path}")
    lines = text.splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError(
            f"No instruction body in {path}. Replace the placeholder or pass --instruction-text."
        )
    return text


def resolve_api_key() -> str:
    key = os.getenv("LLAMA_CLOUD_API_KEY") or os.getenv("LLAMA_PARSE_API_KEY")
    if not key:
        raise EnvironmentError(
            "Missing API key. Set LLAMA_CLOUD_API_KEY in backend/.env "
            "(get one at https://cloud.llamaindex.ai)."
        )
    return key


def resolve_multimodal_api_key(model_name: str) -> str | None:
    if model_name.startswith("gemini"):
        return (
            os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        )
    if model_name.startswith("openai") or model_name.startswith("gpt"):
        return os.getenv("OPENAI_API_KEY")
    if "anthropic" in model_name or model_name.startswith("claude"):
        return os.getenv("ANTHROPIC_API_KEY")
    return None


def build_parser(
    instruction: str,
    *,
    max_pages: int | None,
    target_pages: str | None,
    multimodal_model: str | None,
    use_multimodal: bool,
) -> LlamaParse:
    """JSON result + JobResult API avoids KeyError on legacy result['markdown']."""
    kwargs: dict = {
        "api_key": resolve_api_key(),
        "result_type": "json",
        "num_workers": 4,
        "verbose": True,
        "language": "en",
        "split_by_page": True,
        "system_prompt_append": instruction,
    }
    if max_pages is not None:
        kwargs["max_pages"] = max_pages
    if target_pages:
        kwargs["target_pages"] = target_pages

    if use_multimodal:
        model = multimodal_model or os.getenv("MULTIMODAL_MODEL", "openai-gpt-4o-mini")
        kwargs["use_vendor_multimodal_model"] = True
        kwargs["vendor_multimodal_model_name"] = model
        vendor_key = resolve_multimodal_api_key(model)
        if vendor_key:
            kwargs["vendor_multimodal_api_key"] = vendor_key
        else:
            print(
                f"Warning: no BYOK key for {model}; LlamaParse will use hosted model (more credits).",
                file=sys.stderr,
            )
    else:
        kwargs["use_vendor_multimodal_model"] = False

    return LlamaParse(**kwargs)


def _normalize_job_results(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    return [raw]


def job_results_to_markdown(job_results: list) -> str:
    if not job_results:
        raise RuntimeError("LlamaParse returned no job results.")

    parts: list[str] = []
    page_offset = 0

    for job_index, job in enumerate(job_results, start=1):
        if getattr(job, "error", None) or getattr(job, "status", None) in (
            "ERROR",
            "CANCELED",
        ):
            code = getattr(job, "error_code", None) or "unknown"
            msg = getattr(job, "error", None) or "parse job failed"
            raise RuntimeError(f"LlamaParse job failed ({code}): {msg}")

        docs = job.get_markdown_documents(split_by_page=True)
        if not docs:
            # Fallback: raw markdown endpoint
            try:
                raw_md = job.get_markdown()
                if raw_md and raw_md.strip():
                    parts.append(raw_md.strip())
                    continue
            except Exception:
                pass
            pages = getattr(job, "pages", None) or []
            if not pages:
                raise RuntimeError(
                    f"Job {getattr(job, 'job_id', job_index)}: no pages/markdown in response. "
                    "File may be too large, corrupted, or blocked by API limits."
                )
            continue

        for doc in docs:
            text = (getattr(doc, "text", None) or "").strip()
            if not text:
                continue
            page_offset += 1
            parts.append(f"<!-- page {page_offset} -->\n\n{text}")

    if not parts:
        raise RuntimeError(
            "Parsed jobs completed but all pages are empty. "
            "Try a smaller PDF, --max-pages, or disable multimodal for text-only books."
        )
    return "\n\n---\n\n".join(parts)


def parse_pdf(pdf_path: Path, parser: LlamaParse) -> str:
    raw = parser.parse(str(pdf_path))
    return job_results_to_markdown(_normalize_job_results(raw))


def save_markdown(
    content: str,
    pdf_path: Path,
    output_dir: Path,
    *,
    append: bool = False,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{pdf_path.stem}.md"
    if append and out_path.is_file():
        prev = out_path.read_text(encoding="utf-8").rstrip()
        content = f"{prev}\n\n---\n\n{content}"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def check_pdf_size(pdf_path: Path, max_pages: int | None) -> None:
    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    if size_mb > HARD_MAX_SIZE_MB:
        raise ValueError(
            f"PDF is {size_mb:.0f} MB (>{HARD_MAX_SIZE_MB} MB). "
            "Compress or split the file before parsing (LlamaParse upload limits)."
        )
    if size_mb > WARN_SIZE_MB and max_pages is None:
        print(
            f"Warning: PDF is {size_mb:.0f} MB. Parsing may fail or be expensive. "
            f"Consider --max-pages 50 for a trial run.",
            file=sys.stderr,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a badminton methodology PDF to Markdown using LlamaParse."
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the input PDF file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for .md output (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--instruction-file",
        type=Path,
        default=DEFAULT_INSTRUCTION_FILE,
        help="Path to parsing instruction text file",
    )
    parser.add_argument(
        "--instruction-text",
        type=str,
        default=None,
        help="Parsing instruction inline (overrides --instruction-file)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limit pages parsed from the start (useful for very large PDFs)",
    )
    parser.add_argument(
        "--target-pages",
        type=str,
        default=None,
        help='Page range, e.g. "31-60" or "1,3,5-10" (LlamaParse target_pages)',
    )
    parser.add_argument(
        "--multimodal-model",
        type=str,
        default=os.getenv("MULTIMODAL_MODEL", "openai-gpt-4o-mini"),
        choices=MULTIMODAL_MODELS,
        help="Vendor VLM for page screenshots (gemini-2.0-flash, openai-gpt-4o-mini, ...)",
    )
    parser.add_argument(
        "--no-multimodal",
        action="store_true",
        help="Disable vendor multimodal (cheaper; worse on diagrams)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing output .md (for batch page ranges)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()

    pdf_path = args.pdf_path.resolve()
    if not pdf_path.is_file():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        return 1
    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: expected a .pdf file, got: {pdf_path}", file=sys.stderr)
        return 1

    try:
        check_pdf_size(pdf_path, args.max_pages)

        if args.instruction_text:
            instruction = args.instruction_text.strip()
            if not instruction:
                raise ValueError("--instruction-text must not be empty.")
        else:
            instruction = read_parsing_instruction(args.instruction_file.resolve())

        print(f"Parsing: {pdf_path}")
        print(f"Instruction: {len(instruction)} chars")
        if args.max_pages:
            print(f"Max pages: {args.max_pages}")
        if args.target_pages:
            print(f"Target pages: {args.target_pages}")
        if not args.no_multimodal:
            print(f"Multimodal model: {args.multimodal_model}")

        llama_parser = build_parser(
            instruction,
            max_pages=args.max_pages,
            target_pages=args.target_pages,
            multimodal_model=args.multimodal_model,
            use_multimodal=not args.no_multimodal,
        )
        markdown = parse_pdf(pdf_path, llama_parser)
        out_path = save_markdown(
            markdown,
            pdf_path,
            args.output_dir.resolve(),
            append=args.append,
        )
        print(f"Saved: {out_path} ({len(markdown):,} characters)")
        return 0

    except (EnvironmentError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Parse failed: {exc}", file=sys.stderr)
        if "MULTIMODAL_ERROR" in str(exc) or "Error rate" in str(exc):
            print(
                "Hint: large PDFs often fail on full multimodal runs. Try:\n"
                "  --multimodal-model gemini-2.0-flash  (add GOOGLE_API_KEY to .env)\n"
                "  --target-pages \"1-40\" then --target-pages \"41-80\" --append\n"
                "  or --max-pages 40 per batch",
                file=sys.stderr,
            )
        return 2


if __name__ == "__main__":
    sys.exit(main())
