from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Server Shell",
    version="0.1.0",
    description="Cloud Orchestration Shell（云端编排壳层）"
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
    return {"status": "ok", "service": "server-shell", "version": "0.1.0"}


@app.post("/api/v1/chat")
def chat(_: ChatRequest) -> None:
    _not_implemented("Chat Orchestration")
