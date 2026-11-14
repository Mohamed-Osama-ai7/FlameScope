from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.physics_routes import router as physics_router
from app.api.rag_routes import admin_router as rag_admin_router
from app.api.rag_routes import copilot_router
from app.api.rag_routes import router as rag_router
from app.api.routes import router
from app.data_platform.api import router as data_platform_router
from app.vision.api import router as vision_router

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
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(data_platform_router, prefix="/api/v1")
app.include_router(rag_router, prefix="/api/v1")
app.include_router(copilot_router, prefix="/api/v1")
app.include_router(rag_admin_router, prefix="/api/v1")
app.include_router(physics_router, prefix="/api/v1")
app.include_router(vision_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "flamescope-api", "version": "0.1.0"}
