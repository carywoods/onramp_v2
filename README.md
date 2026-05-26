# On Ramp

AI-powered guidance for students exploring Historically Black Colleges and Universities.

Built on data from *Essentials: A Student Guide to the HBCUs* and deployed at [onramp.woodsfoundation.org](https://onramp.woodsfoundation.org).

---

## Digital Staff

This project is a model of human-AI collaboration. The following AI systems contributed to its research, design, development, and content:

- **Claude** (Anthropic) — architecture, code, deployment
- **ChatGPT** (OpenAI) — research and content development
- **Gemini** (Google) — research and content development
- **Perplexity** — research and fact-checking

---

## Stack

- Python / Flask / Gunicorn
- Full-text search index (SQLite FTS5)
- OpenRouter API (model-agnostic inference)
- Docker / Coolify

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | API key for OpenRouter |
| `BASE_URL` | No | OpenAI-compatible endpoint (default: OpenRouter) |
| `CLASSIFIER_MODEL` | No | Model for query classification (default: `google/gemma-3-27b-it`) |
| `ANSWER_MODEL` | No | Model for answer generation (default: `google/gemma-3-27b-it`) |
| `TOP_K` | No | Number of schools to retrieve (default: 5) |
