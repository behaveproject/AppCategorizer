# AppCategorizer

`appcategorizer` is a Python library and command-line tool that tries to classify an application into a broad software category from its name.

It supports two classification backends: a local embedding model that gathers metadata from 14 public sources and votes across them, and a remote LLM that classifies the application name directly without any network metadata lookups.

## Features

- Queries 14 metadata sources in parallel (local ML mode).
- Uses a local embedding model: `all-MiniLM-L6-v2`.
- Classifies each source result independently and selects the winner by majority vote.
- Supports a remote LLM backend via `--mode cloud_llm` with six provider presets.
- Reads API keys from CLI arguments, environment variables, or a `.env` file.
- Supports verbose logs with `-v`.
- Falls back to `Others` when no reliable category is found.

## Categories

The current classifier can return:

- `Internet Browsers`
- `Productivity Tools`
- `Communication & Collaboration`
- `Out-of-browser Entertainment`
- `Utilities & Maintenance`
- `Media Creation`
- `Development & Programming`
- `Others`

## Installation

Create and activate a virtual environment if needed, then pick the install that matches how you intend to use the tool.

### Lean cloud install (default)

A bare install is lightweight and only pulls in what **cloud LLM mode** needs (`httpx`, `rich`, `platformdirs`, `python-dotenv`) — no embedding model and no headless-browser scraping stack:

```bash
pip install -e .
```

This is all you need to run `--mode cloud_llm`. If you later try to run local ML mode without the backend installed, you get a clear message telling you to install the `[localml]` extra.

### Local ML backend

To use the default **local ML mode** (embedding model + 14 metadata sources), add the `[localml]` extra:

```bash
pip install -e ".[localml]"
```

> **Recommended Python:** 3.10–3.12. The local ML backend depends on `torch`/`sentence-transformers`, whose prebuilt wheels can lag the newest Python releases — if installing the `[localml]` extra fails to find a wheel, use one of these versions.

Some sources rely on Playwright because their pages require JavaScript rendering. Install Chromium for those sources (only needed for local ML mode):

```bash
python -m playwright install chromium
```

The default embedding model is stored in the user cache directory after the first download. You can override the cache location from Python with `Categorizer(model_cache_dir=...)`.

### Full desktop app

The GUI supports both backends. For the complete experience — GUI plus the local ML backend — combine the extras:

```bash
pip install -e ".[gui,localml]"
```

### Windows / running without PATH setup

`pip install -e .` creates `appcategorizer` (and `playwright`) as console scripts in Python's `Scripts\` directory. The bare commands `appcategorizer ...` and `playwright ...` only work if that directory is on your `PATH`, which is often not the case on Windows (Microsoft Store Python, the `py` launcher, or `--user` installs). The `python -m` forms below are equivalent and always work, on any OS:

```bash
python -m playwright install chromium   # instead of: playwright install chromium
python -m appcategorizer Chrome         # instead of: appcategorizer Chrome
```

## Usage

### Local ML mode (default)

Classify using the local embedding model and 14 metadata sources:

```bash
appcategorizer Chrome
```

Enable verbose logs:

```bash
appcategorizer Chrome -v
```

Use a different local sentence-transformer model:

```bash
appcategorizer Chrome --local-model sentence-transformers/all-MiniLM-L12-v2
```

### Cloud LLM mode

Classify by sending the application name directly to a remote LLM. No metadata sources are queried.

```bash
appcategorizer Chrome --mode cloud_llm --llm-provider openai --llm-model gpt-4o --api-key sk-...
```

The `--api-key` argument is optional when the corresponding environment variable is set (see [API keys](#api-keys)).

#### Supported providers

| Provider | `--llm-provider` | Default model | Environment variable |
|---|---|---|---|
| OpenAI | `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` |
| Mistral AI | `mistral` | `mistral-small-latest` | `MISTRAL_API_KEY` |
| Google Gemini | `gemini` | `gemini-2.0-flash` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Ollama (local) | `ollama` | `llama3.2` | *(no key required)* |
| Custom OpenAI-compatible | `custom` | *(required)* | `LLM_API_KEY` |

Override the default model for any provider:

```bash
appcategorizer Chrome --mode cloud_llm --llm-provider anthropic --llm-model claude-opus-4-6
```

Use a custom or self-hosted OpenAI-compatible endpoint:

```bash
appcategorizer Chrome --mode cloud_llm --llm-provider custom \
  --llm-model my-model --llm-base-url http://my-server/v1 --api-key my-key
```

Use a local Ollama instance on a non-default port:

```bash
appcategorizer Chrome --mode cloud_llm --llm-provider ollama \
  --llm-base-url http://localhost:11435/v1
```

Example output (both modes):

```text
Internet Browsers
```

### API keys

API keys are resolved in this order for each call:

1. `--api-key` CLI argument.
2. Provider-specific environment variable (see table above).
3. A `.env` file in the current working directory (loaded automatically when `python-dotenv` is installed).

Copy `.env.example` to `.env` and fill in the keys for the providers you use:

```bash
cp .env.example .env
```

## Python API

Use `Categorizer` from your own async Python code:

```python
import asyncio
from appcategorizer import Categorizer

async def main():
    engine = Categorizer()
    result = await engine.resolve_and_classify("firefox")
    print(result)

asyncio.run(main())
```

`resolve_and_classify()` returns the final category as a plain string. The CLI handles argument parsing, Rich spinners, and logging configuration separately from the library API.

### Full signature

```python
await engine.resolve_and_classify(
    app_name: str,
    analysis_mode: str = "local_ml",
    local_model_name: str = "all-MiniLM-L6-v2",
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    llm_base_url: str | None = None,
)
```

Options:

- `app_name`: application name to resolve and classify.
- `analysis_mode`: classification backend. `"local_ml"` uses the local embedding classifier (default). `"cloud_llm"` sends the cleaned name to a remote LLM.
- `local_model_name`: sentence-transformer model name used when `analysis_mode="local_ml"`. Defaults to `"all-MiniLM-L6-v2"`.
- `llm_provider`: LLM provider identifier. Required when `analysis_mode="cloud_llm"`. One of `openai`, `anthropic`, `mistral`, `gemini`, `ollama`, `custom`.
- `llm_model`: model name to use. Falls back to the provider default when omitted.
- `llm_api_key`: explicit API key. Falls back to the environment variable or `.env` file.
- `llm_base_url`: base URL override for the API endpoint. Required for `custom`; optional for `ollama`.

### Examples

Local ML with the default model:

```python
result = await engine.resolve_and_classify("firefox")
```

Local ML with an alternative sentence-transformer model:

```python
result = await engine.resolve_and_classify(
    "firefox",
    local_model_name="sentence-transformers/all-MiniLM-L12-v2",
)
```

Cloud LLM with OpenAI (key from environment):

```python
result = await engine.resolve_and_classify(
    "firefox",
    analysis_mode="cloud_llm",
    llm_provider="openai",
    llm_model="gpt-4o",
)
```

Cloud LLM with Anthropic (key passed explicitly):

```python
result = await engine.resolve_and_classify(
    "firefox",
    analysis_mode="cloud_llm",
    llm_provider="anthropic",
    llm_model="claude-opus-4-6",
    llm_api_key="sk-ant-...",
)
```

Cloud LLM with a local Ollama instance:

```python
result = await engine.resolve_and_classify(
    "firefox",
    analysis_mode="cloud_llm",
    llm_provider="ollama",
    llm_model="llama3.2",
)
```

## Tkinter GUI

Install the GUI dependency. Add `localml` too if you want on-device ML mode in
the GUI (cloud LLM mode works with `[gui]` alone):

```bash
pip install -e ".[gui]"           # GUI, cloud LLM only
pip install -e ".[gui,localml]"   # GUI + on-device ML backend
```

Run the sample desktop app:

```bash
python -m appcategorizer.gui
```

The GUI supports both backends. Use the Preferences panel to switch between
on-device ML and cloud LLM, and to set the provider, model, API key, and base URL
when using cloud mode.

## How It Works

### Local ML mode

1. The input name is normalized by the resolver.
2. Metadata sources are queried concurrently.
3. Each source returns short text tokens such as descriptions, categories, genres, or tags.
4. The classifier embeds each source result and compares it to the category descriptions.
5. The final category is selected by majority vote, ignoring `Others` when stronger votes exist.

### Cloud LLM mode

1. The input name is sanitized (lowercased, extension stripped, separators normalized).
2. The cleaned name is sent to the configured LLM with a strict system prompt listing all valid categories.
3. The LLM response is returned as-is if it matches a known category, or falls back to `Others`.

No metadata sources are queried in this mode.

## Sources

The resolver is used in **local ML mode only**. It currently queries:

- Apple
- Arch Linux
- Debian
- Fedora
- Flathub
- GitHub
- GOG
- itch.io
- Microsoft Store
- MyAbandonware
- Snapcraft
- Steam
- Ubuntu
- Wikidata

GitHub can use a `GITHUB_TOKEN` environment variable when available to increase API rate limits.

All source metadata is fetched from public third-party services and should be treated as untrusted text. The library uses that text only as classifier input.

## Known Limitations

- Public sources may change their HTML or API responses.
- Debian, Microsoft Store, and MyAbandonware are heavier because they rely on Playwright.
- Cloud LLM mode relies on the LLM's training knowledge of the application; unknown or very niche apps may be misclassified.
- Cloud LLM mode incurs API costs and latency proportional to the number of calls.

## Project Layout

```text
src/appcategorizer/__init__.py                     Public Python API
src/appcategorizer/core.py                         Library orchestration class
src/appcategorizer/cli.py                          Installable CLI entry point
src/appcategorizer/gui.py                          Tkinter desktop GUI (python -m appcategorizer.gui)
src/appcategorizer/engine/resolver.py              Source orchestration (local ML mode)
src/appcategorizer/engine/embedding_classifier.py  Embedding-based category classifier
src/appcategorizer/engine/llm_classifier.py        Remote LLM category classifier
src/appcategorizer/engine/logger.py                Shared logger configuration
src/appcategorizer/engine/sources/                 Metadata source implementations
.env.example                                       API key template for LLM providers
```

## License

AppCategorizer is licensed under the GNU LGPL 3 license only (LGPL-3.0-only).

Copyright © 2026, Sorbonne Université, CNRS, LIP6.
All rights reserved. This program and the accompanying materials are made available under the terms of the [GNU Lesser General Public License v3.0 (LGPL-3.0-only)](https://www.gnu.org/licenses/lgpl-3.0.en.html) which accompanies this distribution.
