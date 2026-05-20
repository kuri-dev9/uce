from fastapi import FastAPI

from app.api.routes import router


app = FastAPI(
    title="UCE - Universal Context Engine",
    version="0.1.0",
    description="Provider-agnostic Context Pack middleware for LLM applications.",
)
app.include_router(router)
