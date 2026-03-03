from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Server Shell",
    version="0.1.0",
    description="Cloud Orchestration Shell（云端编排壳层）"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    message: str = Field(..., description="User prompt（用户输入）")


def _not_implemented(feature_name: str) -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "code": "NOT_IMPLEMENTED",
            "message": f"{feature_name} is not implemented in baseline."
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "server", "version": "0.1.0"}


@app.post("/api/v1/chat")
def chat(_: ChatRequest) -> None:
    _not_implemented("Chat Orchestration")
