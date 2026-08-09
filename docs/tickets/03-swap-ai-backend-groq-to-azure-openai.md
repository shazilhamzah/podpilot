# 03 — Swap AI Backend from Groq to Azure OpenAI

**What to build:** Replace the Groq client in the backend with the Azure OpenAI SDK, authenticated via `DefaultAzureCredential`. When running in AKS the credential chain automatically picks up the Workload Identity projected token. When running locally it falls back to `az login` or an `AZURE_OPENAI_API_KEY` environment variable — no code changes required per environment. All existing Chat and full-analysis endpoints should continue to work identically from the caller's perspective; only the underlying model provider changes. The `groq` package is removed from dependencies and `AI_API_KEY`/`MODEL` are retired from the environment contract.

**Blocked by:** 02 — Set Up Azure OpenAI and Workload Identity (the Azure OpenAI endpoint and the identity must exist before the integration can be verified end-to-end in AKS).

**Status:** done

- [x] `groq` dependency removed; `openai` and `azure-identity` packages added to `requirements.txt`
- [x] `analyzer.py` initialises an `AzureOpenAI` client using `DefaultAzureCredential` and a bearer token provider — no hardcoded API key
- [x] The deployment name is read from an environment variable, defaulting to `gpt-4o`
- [x] All existing retry / backoff logic is preserved unchanged
- [x] `.env.example` drops `AI_API_KEY` and `MODEL`; adds `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and a commented-out `AZURE_OPENAI_API_KEY` for local dev
- [x] The Kubernetes secret in `podpilot.yaml` no longer contains `AI_API_KEY` or `MODEL`; instead contains `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT`
- [x] Chat endpoint returns a valid GPT-4o response when the app is deployed to AKS
- [x] Chat endpoint returns a valid response when running locally with `az login` (or `AZURE_OPENAI_API_KEY` set)
