from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.config import settings


async def verify_optional_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    token = settings.memory_auth_token
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    got = authorization.removeprefix("Bearer ").strip()
    if got != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
