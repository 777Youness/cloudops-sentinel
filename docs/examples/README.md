# Real-provider investigation runs

Automated tests never call a real LLM (CLAUDE.md). Runs against a real provider are done
by hand and saved here, so the behaviour of real models stays reviewable.

No run has been recorded yet.

## How to record one (Ollama, local, no key)

1. Install Ollama from its official site and pull a model that follows instructions well.
2. Start the backend with:
   ```bash
   SENTINEL_LLM_PROVIDER=openai_compatible
   SENTINEL_LLM_BASE_URL=http://localhost:11434/v1
   SENTINEL_LLM_MODEL=<the model you pulled>
   ```
3. Sync, open an incident, click **Run investigation**.
4. Save the result as `docs/examples/<date>-<model>-<incident>.json`:
   ```bash
   curl -s http://127.0.0.1:8000/api/v1/incidents/INC-0004/investigation
   ```
5. Note in the file name or a sidecar `.md`: model, hardware, duration, attempts, and
   whether the validator rejected the first reply (attempts = 2).

Never save a run made with a hosted provider's key in a way that includes the key; the API
never returns it, so the JSON above is safe to commit.
