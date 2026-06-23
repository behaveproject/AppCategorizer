# appcategorizer

## Description

The application is a CLI app categorizer. It takes an application name and returns one of eight predefined software categories. Two classification backends are available:

- **local_ml**: queries 14 public metadata sources in parallel, classifies each source independently using a local sentence-transformer model, and returns the category selected by majority vote.
- **cloud_llm**: sanitizes the application name and sends it directly to a remote LLM with a strict prompt. No metadata sources are queried.

## Project Structure

The package uses a `src/` layout: the importable code lives under `src/appcategorizer/`, so tests and tools always run against the installed package rather than the working directory.

- `src/appcategorizer/`: importable Python package.
- `src/appcategorizer/cli.py`: CLI entry point, argument parsing, progress display, final result.
- `src/appcategorizer/__main__.py`: enables `python -m appcategorizer`.
- `src/appcategorizer/core.py`: library orchestration class (`Categorizer`), mode routing.
- `src/appcategorizer/gui.py`: Tkinter desktop GUI; run with `python -m appcategorizer.gui` (requires the `[gui]` extra).
- `src/appcategorizer/engine/resolver.py`: orchestrates all data sources asynchronously (local ML mode only).
- `src/appcategorizer/engine/sources/`: one module per metadata source.
- `src/appcategorizer/engine/sources/base.py`: shared relevance matching logic.
- `src/appcategorizer/engine/embedding_classifier.py`: embedding model, category descriptions, similarity scoring.
- `src/appcategorizer/engine/llm_classifier.py`: remote LLM classifier, provider configs, request formatting.
- `src/appcategorizer/engine/logger.py`: shared logging configuration.
- `tests/`: test suite (run with `pytest` after `pip install -e ".[dev]"`).
- `.github/workflows/ci.yml`: CI running the tests on Python 3.10–3.12.
- `pyproject.toml`: build configuration, dependencies, optional extras (`[dev]`, `[gui]`, `[localml]`), and the `appcategorizer` console script.
- `.env.example`: API key template for LLM providers.

## Data Sources

All sources return a `list[str]` of text tokens. These tokens are later embedded and compared against category descriptions in `engine/embedding_classifier.py`.

Name validation is handled through `BaseSource.is_relevant()`, which checks exact matches, normalized matches, prefix matches, and fuzzy matching with `rapidfuzz`.

Sources are only queried in **local ML mode**. In cloud LLM mode the resolver is bypassed entirely.

### Apple Store

**Targeted platform:** macOS / iOS

**Method:** API request

**Endpoint:**

- `https://itunes.apple.com/search?term={app_name}&entity=software&limit=1`

**Notes:** Uses Apple's iTunes Search API. The code only reads the first result and validates it against `trackName`.

**Retrieved fields:**

- `resultCount`
- `results`
- `trackName`
- `primaryGenreName`
- `genres`
- `description`

**Returned tokens:**

- `primaryGenreName`
- `genres`
- first 200 characters of `description`

### Arch Linux

**Targeted platform:** Linux

**Method:** API request, with fallback API request to AUR

**Endpoints:**

- `https://archlinux.org/packages/search/json/`
- `https://aur.archlinux.org/rpc/v5/search/{app_name}`

**Notes:** First queries official Arch repositories. If no valid result is found, it falls back to AUR. Official packages and AUR packages use different JSON field names.

**Retrieved fields:**

- Arch official: `results`, `pkgname`, `pkgdesc`, `groups`
- AUR: `results`, `Name`, `Description`, `Keywords`

**Returned tokens:**

- Arch official: `pkgdesc`, `groups`
- AUR: `Description`, `Keywords`

### Debian

**Targeted platform:** Linux

**Method:** browser-based scraping with Playwright and HTML parsing

**Site:**

- `https://packages.debian.org/stable/{app_name}`

**Notes:** Uses Playwright Chromium instead of plain `httpx`, then parses the rendered HTML with BeautifulSoup. This makes the source heavier and requires:

```bash
playwright install chromium
```

**Retrieved fields/selectors:**

- `div#pdesc`
- inside it: `p`, `ul`, `pre`
- list items: `li`

**Returned tokens:**

- cleaned paragraphs
- cleaned lists as a single text block
- cleaned preformatted blocks

### Fedora

**Targeted platform:** Linux

**Method:** website scraping with `httpx` and BeautifulSoup

**Sites:**

- `https://packages.fedoraproject.org/pkgs/{app_name}/`
- `https://packages.fedoraproject.org/search/`

**Notes:** First tries the direct package page. If needed, it searches Fedora packages and then opens the matched package detail page.

**Retrieved fields/selectors:**

- overview page: `ul li`, then `b`
- search page: `a.package-name`, `td a[href*='/pkgs/']`
- detail page: `p`

**Returned tokens:**

- first paragraph longer than 30 characters, excluding generic Fedora interface text

### Flathub

**Targeted platform:** Linux

**Method:** API request

**Endpoint:**

- `https://flathub.org/api/v2/search`

**Notes:** Uses a POST request. The response may be either a dictionary containing `hits` or a direct list.

Request body:

```json
{
  "query": "app_name",
  "filters": []
}
```

**Retrieved fields:**

- `hits`
- `app_id`
- `name`
- `summary`
- `categories`
- category `name`

**Returned tokens:**

- `name`
- `summary`
- category `name`

### GitHub

**Targeted platform:** Universal

**Method:** API request

**Endpoint:**

- `https://api.github.com/search/repositories`

**Notes:** Can use a `GITHUB_TOKEN` environment variable to increase rate limits.

Query parameters:

- `q`: `{app_name} in:name`
- `per_page`: `5`

**Retrieved fields:**

- `items`
- `name`
- `full_name`
- `description`
- `topics`

**Returned tokens:**

- semantic hint for game/emulator repositories: `"This is an open-source video game or gaming project hosted on GitHub."`
- semantic hint otherwise: `"This is an open-source software project, development tool, or application hosted on GitHub."`
- `description`
- `topics`

### GOG

**Targeted platform:** Universal (gaming)

**Method:** API-like catalog request

**Endpoint:**

- `https://catalog.gog.com/v1/catalog?limit=5&locale=en-US&query={query}`

**Notes:** The query is normalized by replacing `:` and `-` with spaces. The request forces English/US context while the language is normally based on IP address.

**Retrieved fields:**

- `products`
- `title`
- `slug`
- `productType`
- `genres`
- genre `name`

**Returned tokens:**

- one semantic sentence built from `productType` and genre `name`

### itchio

**Targeted platform:** Universal (gaming)

**Method:** website scraping with `httpx` and BeautifulSoup

**Sites:**

- `https://itch.io/search?q={query}`
- then the matched product page URL from the search result

**Notes:** Search results are parsed from HTML. The code validates result names using the title and URL slug variants, including compact slug matching.

**Retrieved fields/selectors:**

Search selectors:

- `div.game_cell`
- `div.title`
- `div.game_title`
- nested `a`
- `href`
- link text as title

Detail selectors:

- `table.game_info_panel`
- table row labels containing `genre`
- table row labels containing `tags`
- `meta[name="description"]`
- fallback: `div.formatted_description`
- fallback paragraphs: `p`

**Returned tokens:**

- semantic hint based on genres and tags:
  - if it is not a game: `"This software is distributed on itch.io. Categories and tags: ..."`
  - otherwise: `"This is a video game, indie game, or gaming entertainment software distributed on itch.io."`
- SEO description or first useful HTML description block

### Microsoft Store

**Targeted platform:** Windows

**Method:** browser-based scraping with Playwright, then HTML parsing with `httpx` and BeautifulSoup

**Sites:**

- `https://apps.microsoft.com/search?query={app_name}&hl=en-us&gl=US`
- then the matched `/detail/` product page

**Notes:** Search requires Playwright because the page generates components dynamically. After finding a product URL, the detail page is fetched with `httpx`.

**Retrieved fields/selectors:**

Search selectors and attributes:

- links matching `a[href*='/detail/']`
- link `href`
- link `inner_text()`
- link `aria-label`

Detail selectors and data:

- `script[type="application/ld+json"]`
- JSON-LD field `@type`
- JSON-LD field `description`
- fallback: `meta[name="description"]`

**Returned tokens:**

- up to 3 cleaned description blocks from `description`

### MyAbandonware

**Targeted platform:** Universal (gaming)

**Method:** browser-based scraping with Playwright and HTML parsing

**Sites:**

- `https://www.myabandonware.com/search/q/{query}/`
- then the matched `/game/` page

**Notes:** Uses Chromium because MyAbandonware requires JavaScript and may show Cloudflare checks. The code waits up to 10 seconds for Cloudflare by watching the page title.

**Retrieved fields/selectors:**

Search data:

- current page URL
- all links with `href`
- links containing `/game/`
- `span.name`
- link text
- game slug extracted from `/game/{slug}`

Detail selectors:

- `div#desc`
- `div#description`
- `div.desc`
- `div.gameDescription`
- fallback: `meta[name="description"]`
- paragraphs: `p`

**Returned tokens:**

- semantic hint: `"This is a retro video game and single-player entertainment software."`
- up to 2 cleaned description blocks

### Snapcraft

**Targeted platform:** Linux

**Method:** API request, with fallback API search

**Endpoints:**

- `https://api.snapcraft.io/v2/snaps/info/{app_name}`
- `https://api.snapcraft.io/v2/snaps/find`

**Notes:** First tries a direct snap lookup. If it fails, it searches by name.

Direct lookup parameters:

- `fields`: `title,name,summary,categories`

Search parameters:

- `q`: `{app_name}`
- `fields`: `title,name,summary,categories`

**Retrieved fields:**

Direct response:

- root `name`
- `snap`
- `snap.title`
- `snap.summary`
- `snap.categories`

Search response:

- `results`
- `snap`
- `snap.name`
- `snap.title`
- `snap.summary`
- `snap.categories`
- category `name`

**Returned tokens:**

- display title
- summary
- category `name`

### Steam

**Targeted platform:** Universal (mostly gaming)

**Method:** API request

**Endpoints:**

- `https://store.steampowered.com/api/storesearch/`
- `https://store.steampowered.com/api/appdetails/`

**Notes:** First searches Steam to get the app ID, then fetches genres and categories for that app.

Search parameters:

- `term`: `{app_name}`
- `l`: `english`
- `cc`: `US`

Detail parameters:

- `appids`: `{appid}`
- `filters`: `genres,categories`

**Retrieved fields:**

Search:

- `items`
- first item `name`
- first item `id`

Detail:

- `{appid}.data`
- `genres`
- genre `description`
- `categories`
- category `description`

**Returned tokens:**

- genre `description`
- category `description`

### Ubuntu

**Targeted platform:** Linux

**Method:** website scraping with `httpx` and BeautifulSoup

**Sites:**

- `https://packages.ubuntu.com/noble/{app_name}`
- `https://packages.ubuntu.com/search/`

**Notes:** Targets Ubuntu suite `noble`, which corresponds to Ubuntu 24.04 LTS. First tries the direct package page, then falls back to package search.

Search parameters:

- `keywords`: `{app_name}`
- `searchon`: `names`
- `suite`: `noble`
- `section`: `all`

**Retrieved fields/selectors:**

- search results: `h3 a`
- package title: `h1`
- description container: `div#pdesc`
- short description: `h2`
- long description: `p`
- section: `a[href*='/section/']`
- Debtags: `a[href*='tag=']`

**Returned tokens:**

- short description from `h2`
- first non-empty paragraph from `p`
- package section text
- Debtags containing `::`

### Wikidata

**Targeted platform:** Universal

**Method:** API request

**Endpoint:**

- `https://www.wikidata.org/w/api.php`

**Notes:** Uses the Wikidata API in two phases: search for an entity, then fetch entity data. Classification claims are QIDs, so the code resolves each QID to an English label with another API call.

Search parameters:

- `action`: `wbsearchentities`
- `search`: `{app_name}`
- `format`: `json`
- `language`: `en`
- `type`: `item`
- `limit`: `5`

Entity parameters:

- `action`: `wbgetentities`
- `ids`: `{qid}`
- `format`: `json`
- `languages`: `en`
- `props`: `descriptions|claims`

Label resolution parameters:

- `action`: `wbgetentities`
- `ids`: `{qid}`
- `format`: `json`
- `languages`: `en`
- `props`: `labels`

**Retrieved fields:**

Search:

- `search`
- `label`
- `id`

Entity:

- `entities`
- `descriptions.en.value`
- `claims`
- claim properties:
  - `P31` = instance of
  - `P136` = genre
  - `P452` = industry
- `mainsnak.datavalue.value.id`

Label:

- `labels.en.value`

**Returned tokens:**

- English entity description
- resolved labels for `P31`, `P136`, and `P452` claims

## Categories

- Internet Browsers
- Productivity Tools
- Communication & Collaboration
- Out-of-browser Entertainment
- Utilities & Maintenance
- Media Creation
- Development & Programming
- Others

## Algorithm

### Local ML mode

It uses sentence embeddings with sentence-transformers, specifically `all-MiniLM-L6-v2`. Each category is represented by a handcrafted text description in `engine/embedding_classifier.py`. The app embeds the collected source text, compares it to each category embedding with cosine similarity, and keeps the best category when its score is above the confidence threshold. Otherwise, the result is `Others`.

Algorithm flow:

1. Normalize the input name.
2. Query all sources concurrently.
3. Validate returned results with exact, prefix, normalized, and fuzzy matching.
4. Convert each source's tokens into one text string.
5. Embed that text with a ML algorithm (`all-MiniLM-L6-v2`).
6. Compare it to category embeddings using cosine similarity.
7. Vote across source-level predictions.
8. Print out the final category.

### Cloud LLM mode

The resolver and all metadata sources are bypassed. The application name is sanitized and sent directly to the configured LLM.

Algorithm flow:

1. Sanitize the input name (lowercase, strip file extension, normalize separators).
2. Send the cleaned name to the LLM with a strict system prompt listing all valid category names.
3. Return the LLM response if it matches a known category exactly; fall back to `Others` otherwise.

## LLM Classifier

Implemented in `engine/llm_classifier.py`. Supports six provider presets and one generic fallback.

### Provider configurations

| Provider | `llm_provider` | Wire format | Default model | API key env var |
|---|---|---|---|---|
| OpenAI | `openai` | OpenAI Chat Completions | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | Anthropic Messages API | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` |
| Mistral AI | `mistral` | OpenAI Chat Completions | `mistral-small-latest` | `MISTRAL_API_KEY` |
| Google Gemini | `gemini` | Gemini `generateContent` | `gemini-2.0-flash` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Ollama | `ollama` | OpenAI Chat Completions | `llama3.2` | *(none required)* |
| Custom | `custom` | OpenAI Chat Completions | *(required)* | `LLM_API_KEY` |

### API key resolution

For each request the key is resolved in this order:

1. `llm_api_key` parameter (or `--api-key` CLI argument).
2. Provider-specific environment variable listed in the table above.
3. `.env` file in the working directory (requires `python-dotenv`).

Ollama skips key resolution entirely. `custom` requires an explicit `llm_base_url`.

### Request formats

**OpenAI Chat Completions** (used by `openai`, `mistral`, `ollama`, `custom`):

```
POST {base_url}/chat/completions
Authorization: Bearer {api_key}

{
  "model": "{model}",
  "messages": [
    {"role": "system", "content": "{system_prompt}"},
    {"role": "user",   "content": "{cleaned_app_name}"}
  ],
  "temperature": 0,
  "max_tokens": 20
}
```

Response field: `choices[0].message.content`

**Anthropic Messages API**:

```
POST {base_url}/messages
x-api-key: {api_key}
anthropic-version: 2023-06-01

{
  "model": "{model}",
  "system": "{system_prompt}",
  "messages": [{"role": "user", "content": "{cleaned_app_name}"}],
  "max_tokens": 20
}
```

Response field: `content[0].text`

**Google Gemini generateContent**:

```
POST {base_url}/models/{model}:generateContent?key={api_key}

{
  "system_instruction": {"parts": [{"text": "{system_prompt}"}]},
  "contents": [{"parts": [{"text": "{cleaned_app_name}"}]}],
  "generationConfig": {"temperature": 0, "maxOutputTokens": 20}
}
```

Response field: `candidates[0].content.parts[0].text`

### System prompt

```
You are an application classifier. Given an application name, respond with
EXACTLY one of the following categories and nothing else:
Internet Browsers
Productivity Tools
Communication & Collaboration
Out-of-browser Entertainment
Utilities & Maintenance
Media Creation
Development & Programming
Others
```

## CLI Reference

```
appcategorizer [-h] [-v] [--mode {local_ml,cloud_llm}]
               [--local-model MODEL]
               [--llm-provider PROVIDER] [--llm-model MODEL]
               [--api-key KEY] [--llm-base-url URL]
               app_name
```

| Argument | Default | Description |
|---|---|---|
| `app_name` | *(required)* | Application name to categorize |
| `-v`, `--verbose` | `False` | Enable debug logs |
| `--mode` | `local_ml` | Classification backend: `local_ml` or `cloud_llm` |
| `--local-model` | `all-MiniLM-L6-v2` | Sentence-transformer model used in `local_ml` mode |
| `--llm-provider` | `None` | LLM provider (required with `cloud_llm`) |
| `--llm-model` | provider default | Model identifier |
| `--api-key` | env / `.env` | API key for the LLM provider |
| `--llm-base-url` | provider default | Base URL override (required for `custom`) |