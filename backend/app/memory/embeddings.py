from openai import AsyncOpenAI

from app.config import Settings


async def embed_query(
    client: AsyncOpenAI,
    model: str,
    text: str,
    *,
    dimensions: int | None = None,
) -> list[float]:
    from app.cache.embedding_cache import get_cached_embedding, set_cached_embedding

    cached = get_cached_embedding(model, text, dimensions=dimensions)
    if cached is not None:
        return cached
    kwargs: dict = {"model": model, "input": text}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    resp = await client.embeddings.create(**kwargs)
    vector = list(resp.data[0].embedding)
    set_cached_embedding(model, text, dimensions=dimensions, vector=vector)
    return vector


async def embed_texts(
    client: AsyncOpenAI,
    model: str,
    texts: list[str],
    *,
    dimensions: int | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    from app.cache.embedding_cache import get_cached_embedding, set_cached_embedding

    out: list[list[float] | None] = [None] * len(texts)
    missing_idx: list[int] = []
    missing_texts: list[str] = []
    for i, text in enumerate(texts):
        hit = get_cached_embedding(model, text, dimensions=dimensions)
        if hit is not None:
            out[i] = hit
        else:
            missing_idx.append(i)
            missing_texts.append(text)
    if missing_texts:
        kwargs: dict = {"model": model, "input": missing_texts}
        if dimensions is not None:
            kwargs["dimensions"] = dimensions
        resp = await client.embeddings.create(**kwargs)
        for j, d in enumerate(resp.data):
            idx = missing_idx[j]
            vector = list(d.embedding)
            out[idx] = vector
            set_cached_embedding(
                model, texts[idx], dimensions=dimensions, vector=vector
            )
    assert all(v is not None for v in out)
    return [v for v in out]  # type: ignore[misc]


def openai_client(settings: Settings) -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings")
    return AsyncOpenAI(api_key=settings.openai_api_key)
