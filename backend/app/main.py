from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.data_platform.api import router as data_platform_router

app = FastAPI(
    title="FlameScope API",
    version="0.1.0",
    description=(
        "Independent research prototype for traceable microgravity-combustion evidence. "
        "Not a NASA product or an operational fire-safety system."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(data_platform_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "flamescope-api", "version": "0.1.0"}
