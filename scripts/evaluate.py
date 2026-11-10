"""Measure retrieval on the synthetic acceptance corpus; collect answers for human review."""

import argparse
import json
from pathlib import Path
from typing import Any

import httpx


def evaluate(
    questions_path: Path,
    api_url: str,
    model: str | None,
) -> dict[str, Any]:
    """Report document recall; unsupported questions require manual abstention review."""
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=api_url, timeout=600, trust_env=False) as client:
        for item in questions:
            response = client.post(
                "/api/v1/search",
                json={
                    "query": item["question"],
                    "top_k": item["top_k"],
                },
            )
            response.raise_for_status()
            sources = response.json()
            found = {source["filename"] for source in sources}
            expected = set(item["expected_documents"])
            row = {
                **item,
                "retrieved_documents": sorted(found),
                "retrieval_pass": expected <= found if item["answerable"] else None,
            }
            if model:
                answer = client.post(
                    "/api/v1/chat",
                    json={
                        "message": item["question"],
                        "model": model,
                        "top_k": item["top_k"],
                        "temperature": 0,
                    },
                )
                answer.raise_for_status()
                row["response"] = answer.json()
                row["human_review"] = "pending"
            results.append(row)
    scored = [row for row in results if row["answerable"]]
    return {
        "answerable_cases": len(scored),
        "retrieval_passes": sum(bool(row["retrieval_pass"]) for row in scored),
        "chat_model": model,
        "results": results,
    }


def main() -> None:
    """Print a reproducible JSON report without changing the document collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--model", help="Optionally collect answers for manual review.")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.questions, args.api_url, args.model), indent=2))


if __name__ == "__main__":
    main()
