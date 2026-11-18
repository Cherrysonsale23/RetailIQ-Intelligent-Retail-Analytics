from fastapi import APIRouter

from app.core.auth import CurrentUser

router = APIRouter(tags=["identity"])


@router.get("/me")
async def me(user: CurrentUser) -> dict[str, str | None]:
    return {"id": user["sub"], "email": user.get("email")}
