from openai import AsyncOpenAI

from app.config import Settings


async def embed_query(
    client: AsyncOpenAI,
    model: str,
    text: str,
    *,
    dimensions: int | None = None,
) -> list[float]:
    kwargs: dict = {"model": model, "input": text}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    resp = await client.embeddings.create(**kwargs)
    return list(resp.data[0].embedding)


async def embed_texts(
    client: AsyncOpenAI,
    model: str,
    texts: list[str],
    *,
    dimensions: int | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    kwargs: dict = {"model": model, "input": texts}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    resp = await client.embeddings.create(**kwargs)
    return [list(d.embedding) for d in resp.data]


def openai_client(settings: Settings) -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings")
    return AsyncOpenAI(api_key=settings.openai_api_key)
