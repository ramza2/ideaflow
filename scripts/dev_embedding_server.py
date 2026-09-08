#!/usr/bin/env python3
"""Local OpenAI-compatible embedding server for IdeaFlow smoke / backfill.

Uses sentence-transformers with BAAI/bge-m3 (1024-d) to match IdeaFlow's
``EMBEDDING_DIMENSION`` and default ``EMBEDDING_MODEL_NAME``.

Not used in production. Intended for local/dev validation when an external
embedding endpoint is not available.

Example:

  pip install sentence-transformers uvicorn fastapi
  python scripts/dev_embedding_server.py --host 127.0.0.1 --port 8090

  EMBEDDING_ENABLED=true
  EMBEDDING_PROVIDER=openai_compatible
  EMBEDDING_API_URL=http://127.0.0.1:8090
  EMBEDDING_MODEL_NAME=BAAI/bge-m3
  EMBEDDING_DIMENSION=1024
"""

from __future__ import annotations

import argparse
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    model: str | None = None
    input: str | list[str]


class EmbedData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbedResponse(BaseModel):
    object: str = "list"
    model: str
    data: list[EmbedData]
    usage: dict[str, int] = Field(default_factory=dict)


def build_app(model_name: str) -> FastAPI:
    from sentence_transformers import SentenceTransformer

    app = FastAPI(title="IdeaFlow Dev Embedding Server", version="0.1.0")
    model = SentenceTransformer(model_name)
    dim = int(model.get_embedding_dimension())
    if dim != 1024:
        raise RuntimeError(
            f"Model {model_name!r} outputs dim={dim}; IdeaFlow requires 1024."
        )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "model": model_name, "dimension": dim}

    @app.post("/v1/embeddings", response_model=EmbedResponse)
    def embeddings(body: EmbedRequest) -> EmbedResponse:
        texts = [body.input] if isinstance(body.input, str) else list(body.input)
        if not texts:
            raise HTTPException(status_code=400, detail="input must not be empty")
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        data = [
            EmbedData(index=i, embedding=vectors[i].astype(float).tolist())
            for i in range(len(texts))
        ]
        chars = sum(len(t) for t in texts)
        return EmbedResponse(
            model=body.model or model_name,
            data=data,
            usage={"prompt_tokens": chars, "total_tokens": chars},
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--model", default="BAAI/bge-m3")
    args = parser.parse_args()
    app = build_app(args.model)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
