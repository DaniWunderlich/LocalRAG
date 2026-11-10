# Retrieval and answer baseline

The 16 questions in `questions.json` refer to the four artificial documents
created by `scripts/acceptance.py initialise`. They cover exact facts,
paraphrases, technical names, two-document questions and unsupported questions.
Use an isolated acceptance stack; these documents contain no private information.

After initialising the acceptance corpus, copy the questions into its backend:

```powershell
docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance cp eval/questions.json backend:/tmp/questions.json
Get-Content -Raw scripts/evaluate.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance exec -T backend python - --questions /tmp/questions.json
```

Add `--model granite3.3:8b` to collect answers for human review. The script
does not automatically grade model prose. Record the embedding model, digest,
chat model, configuration and test date alongside each saved report.

For each answer, check that the relevant excerpts were retrieved, source IDs
refer to the supplied excerpts, every factual statement is supported and
unsupported questions produce an explicit acknowledgement of missing evidence.
The expected terms are reviewer aids rather than exact answer strings.

The [2026-11-10 baseline](baseline-2026-11-10.json) records a live run with
`qwen3-embedding:4b` and `granite3.3:8b`, including both model digests.
All 14 answerable retrieval cases found the expected documents, and both
unsupported questions produced appropriate abstentions. Manual review found
grounded answers and correct source mapping. One answer used a plain
`Source 1` reference rather than the requested bracketed citation format.

A high retrieval score on four short documents is a smoke baseline. It does
not establish performance on long, multilingual or ambiguous real documents.
Dense retrieval still returns the nearest excerpts for unsupported questions;
abstention must therefore be checked separately during answer review.
