# AI Providers

LifeHack OS works completely without AI. Every module functions fully in standalone mode. AI is an optional layer that adds two capabilities: nutritional estimation from food descriptions, and personalized insights on your dashboard.

---

## Table of Contents

1. [Standalone Mode (No AI)](#standalone-mode-no-ai)
2. [How AI Integrates with LifeHack OS](#how-ai-integrates-with-lifehack-os)
3. [Ollama (Free, Local)](#ollama-free-local)
4. [OpenAI-Compatible API](#openai-compatible-api)
5. [Choosing a Provider](#choosing-a-provider)
6. [Environment Variables Reference](#environment-variables-reference)
7. [Checking AI Status](#checking-ai-status)

---

## Standalone Mode (No AI)

The default. No configuration required beyond the base `.env` setup.

```dotenv
LIFEHACK_AI_PROVIDER=none
```

In standalone mode:

- All habit, check-in, project, movement, fasting, and challenge features work normally
- Food logging works — you enter nutrition values manually
- The "Analyze with AI" button in the Food module is hidden or returns a graceful "AI not configured" response
- The "Generate Insight" feature is not available
---

## How AI Integrates with LifeHack OS

The AI layer has two functions:

### 1. Food Analysis

When you log a meal in the Food module and click **Analyze with AI**, the app sends your food description to the configured AI provider. The provider returns estimated calories, protein, carbs, and fat. These values are pre-filled in the form — you can adjust them before saving.

This is an estimate, not a precise measurement. The accuracy depends on the model you use.

### 2. Insight Generation

The **Generate Insight** feature (available from the dashboard) sends your current stats — total XP, habits completed today, best streak, mood, and energy — to the AI provider. The provider returns a short, personalized insight (title + 1-2 sentences) which is saved to the database and displayed on the dashboard.

Insights are dismissable. They queue up if multiple are generated.

---

## Ollama (Free, Local)

Ollama runs an LLM on your own machine. Your data never leaves your network. There is no API cost.

### Step 1: Install Ollama

Follow the instructions at [https://ollama.com](https://ollama.com). Ollama supports Linux, macOS, and Windows.

On Linux:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Step 2: Pull a Model

```bash
ollama pull llama3
```

The `llama3` model (8B parameters) is a good default. For a lighter model on slower hardware:

```bash
ollama pull llama3.2:1b
```

For better nutrition analysis accuracy:

```bash
ollama pull mistral
```

Verify the model is available:

```bash
ollama list
```

### Step 3: Confirm Ollama is Running

Ollama starts a local HTTP server at `http://localhost:11434` by default. Verify it is running:

```bash
curl http://localhost:11434/api/tags
```

You should see a JSON response listing your installed models.

### Step 4: Configure .env

```dotenv
LIFEHACK_AI_PROVIDER=ollama

# Optional — only needed if you changed the defaults
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

If `OLLAMA_URL` and `OLLAMA_MODEL` are not set, the defaults shown above are used.

### Step 5: Restart the Server

```bash
cd web
python app.py
```

The AI status endpoint (`GET /api/ai/status`) will confirm the provider is available.

### Troubleshooting Ollama

**"AI not configured" when analyzing food:**
- Check that Ollama is running: `curl http://localhost:11434/api/tags`
- Verify `LIFEHACK_AI_PROVIDER=ollama` in `.env`
- Restart the LifeHack OS server after editing `.env`

**Slow responses:**
- Ollama loads the model into memory on first request. The first call may take 30-60 seconds on slower hardware. Subsequent calls are faster.
- Consider using a smaller model: `ollama pull llama3.2:1b` and set `OLLAMA_MODEL=llama3.2:1b`

**Model not found:**
- Run `ollama list` to see installed models
- The model name in `OLLAMA_MODEL` must match exactly what `ollama list` shows

---

## OpenAI-Compatible API

Works with OpenAI directly, or any API that speaks the OpenAI chat completions format: Azure OpenAI, Groq, Together AI, Mistral API, Anyscale, and others.

### Step 1: Get an API Key

For OpenAI: log in at [https://platform.openai.com](https://platform.openai.com), go to API keys, and create a new key.

For other providers: follow their documentation to obtain an API key and base URL.

### Step 2: Configure .env

**OpenAI:**

```dotenv
LIFEHACK_AI_PROVIDER=openai
OPENAI_API_KEY=sk-...your-key-here...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

**Groq (free tier available):**

```dotenv
LIFEHACK_AI_PROVIDER=openai
OPENAI_API_KEY=gsk_...your-groq-key...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama3-8b-8192
```

**Together AI:**

```dotenv
LIFEHACK_AI_PROVIDER=openai
OPENAI_API_KEY=...your-together-key...
OPENAI_BASE_URL=https://api.together.xyz/v1
OPENAI_MODEL=meta-llama/Llama-3-8b-chat-hf
```

`OPENAI_BASE_URL` and `OPENAI_MODEL` have these defaults if not set:
- `OPENAI_BASE_URL` defaults to `https://api.openai.com/v1`
- `OPENAI_MODEL` defaults to `gpt-4o-mini`

### Step 3: Restart the Server

```bash
cd web
python app.py
```

### Model Recommendations

| Use Case | Recommended Model | Notes |
|---|---|---|
| Best accuracy | `gpt-4o` | Highest cost |
| Balanced | `gpt-4o-mini` | Default, good accuracy at low cost |
| Free/cheap | Groq `llama3-8b-8192` | Free tier, fast |
| Local alternative | Ollama `llama3` | Zero cost, private |

### Troubleshooting OpenAI

**"AI not configured" response:**
- Verify `LIFEHACK_AI_PROVIDER=openai` and `OPENAI_API_KEY` are set in `.env`
- The provider availability check is: `bool(api_key)` — if the key is set, the provider reports as available

**API errors in logs:**
- Check your API key is valid and has credits
- Verify `OPENAI_BASE_URL` ends in `/v1` (required for the chat completions path)

---

## Choosing a Provider

| Factor | Ollama | OpenAI |
|---|---|---|
| Cost | Free | Pay per token |
| Privacy | 100% local | Data sent to API |
| Setup complexity | Medium (install Ollama) | Low (just a key) |
| Speed | Depends on hardware | Fast |
| Quality | Good with llama3 | Excellent with gpt-4o |
| Internet required | No | Yes |

If privacy matters to you, use Ollama. If you want the best accuracy with minimal setup, use OpenAI with `gpt-4o-mini`.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `LIFEHACK_AI_PROVIDER` | `none` | `none`, `ollama`, or `openai` |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Model to use with Ollama |
| `OPENAI_API_KEY` | _(empty)_ | API key for OpenAI-compatible API |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible API |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model to use |

---

## Checking AI Status

Query the status endpoint to confirm which provider is active and available:

```bash
curl -b "session=..." http://localhost:8420/api/ai/status
```

Response when Ollama is running:

```json
{
  "provider": "ollama",
  "available": true,
  "provider_class": "OllamaProvider"
}
```

Response in standalone mode:

```json
{
  "provider": "none",
  "available": false,
  "provider_class": "NullAIProvider"
}
```

Note: the `/api/ai/status` endpoint requires a valid browser session (login first).
