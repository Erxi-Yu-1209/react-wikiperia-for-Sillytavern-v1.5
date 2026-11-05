[English](readme.md) | [中文](readme-zh.md)

# ReAct Wiki 1.5

**A small Wikipedia-assisted roleplay proxy for SillyTavern.**

The project explores whether retrieving external references before a fictional continuation can introduce useful variety in character motivation, interpersonal conflict, and worldbuilding. Its contribution is an application and prompt-design experiment, not a new reasoning architecture or a scientifically validated model of human behavior.

**Version documented:** the original supplied `react_proxy.py`, preset, Chinese `readme.txt`, and launcher. This English document incorporates a complete source review and offline characterization. It does not describe the proposed refactor as implemented. No live provider, live Wikipedia, Windows launcher, or SillyTavern end-to-end test was performed in this review.

> **Before running:** the script's direct startup binds to all network interfaces without application authentication. Use the loopback-only command below. Persistent theory counts are not reliably isolated between conversations, and the rule-of-three is a prompt instruction, not a backend prohibition. Use disposable, non-sensitive test scenes.

## Part I. Principles and actual behavior

### Creative purpose and ReAct

The author wrote thematic descriptions and used an LLM to help organize them into nine dimensions and implement the proxy. A scene can be considered through different interpretive lenses: for example, a guild negotiation might involve institutional legitimacy, information asymmetry, or kinship obligations. A writer must still judge whether a lens helps the scene. The preset's psychological and sociological language should not be read as clinical diagnosis or established universal laws.[^original][^preset]

Yao et al. describe ReAct as interleaving reasoning with actions whose observations inform subsequent decisions. This proxy implements a small, text-mediated adaptation: request a model response, recognize a Wikipedia action, execute it, append an observation, and call the model again. The Python source confirms that feedback loop. It does not reproduce the paper's experiments, retrain the model, or optimize prompts using scored candidate solutions.[^react][^loop]

Wikipedia is the external retrieval source implemented here. Model-generated search terms are not evidence of a separate provider-internal RAG database. The script contains no vector index, embedding pipeline, or integration with the additional retrieval services mentioned in the author's personal setup. The nine prompt definitions are not rewritten by the proxy. The persistent store holds declared theory-use counts, not article text or a dynamically revised scientific framework.[^tools][^state]

### The nine dimensions

These are search cues from the original preset, not guarantees of independent dimensions or theoretical validity.[^preset]

| Dimension | Example cues |
| --- | --- |
| Political authority and jurisprudence | Monopoly on violence; legal pluralism |
| Social construction and control | Structural anthropology; biopolitics |
| Character psychology and identity | Psychoanalytic, Gestalt, and identity-related frameworks |
| Interpersonal interaction | Dramaturgy; information asymmetry |
| Rational decision-making | Rational choice theory; homo economicus |
| Political positioning | Political spectrum; horseshoe theory |
| Art, heritage, and cultural value | Sociology of art; cultural capital |
| Transmission of ideas and ontology | Memetics; actor-network theory |
| Kinship and affiliation | Kinship; fictive kinship |

The preset determines which dimensions are included in a request. The proxy does not maintain nine separately validated state objects or guarantee that all nine are researched in a turn.

### Core components

| Component | Function in the original version |
| --- | --- |
| Preset JSON | Roleplay instructions, dimension prompts, action syntax, output metadata, and prompt ordering |
| `execute_tool()` | English Wikipedia search and introductory-extract retrieval |
| `run_react_loop()` | Request preprocessing, count injection, repeated model calls, action detection, final-output extraction, and count updates |
| `get_db_filename()`, `load_theory_db()`, `save_theory_db()` | A JSON file mapping model-declared theory names to counts |
| `chat_completions()` | `/v1/chat/completions`, returning JSON or buffered SSE |
| `get_models()` | `/v1/models`, advertising the local alias `react-engine` |
| Supplied `start.bat` | An optional Windows wrapper; must not overwrite the official SillyTavern launcher |

### What happens during a request

A **turn** is a completion request from SillyTavern. An **iteration** is one upstream model invocation within that request.[^loop]

1. The proxy copies nonempty message strings, retaining only `role` and `content`. It scans them for a `SESSION_ID` marker, defaulting to `default`.
2. It loads theory counts, or immediately clears them when at most two non-system messages remain. It appends counts and an exhaustion warning to the first system message, if one exists.
3. It calls the configured upstream model. The payload contains only the configured `model`, copied `messages`, client `temperature` or its default, and bounded `max_tokens`.
4. It searches the concatenation of returned `reasoning_content` and `content` for the first action marker. A match triggers the tool, followed by an appended assistant-content message and a user-role observation message.
5. Without a recognized action, it extracts a narrative and optional metadata, attempts to update counts, prepends an HTML details panel, and returns the result. A missing narrative is replaced with a warning.
6. The loop allows at most five upstream calls by default. If every call contains an action, the fifth action is still executed, its observation is never used by another call, and the proxy returns `SIMULATION ERROR: Maximum ReAct iterations reached.`

The final-pass restriction is only a prompt warning. It is not enforced before tool dispatch. Neither an upstream generation-length stop nor missing/malformed metadata is reliably treated as an unsuccessful final result. These are known limitations, not intended guarantees.[^loop][^format]

### Legacy tools and action syntax

```text
::: ACTION_CALL: SEARCH_WIKI | Information asymmetry :::
::: ACTION_CALL: READ_WIKI_PAGE | Information asymmetry :::
```

`SEARCH_WIKI` uses the MediaWiki search API and returns up to three titles and snippets. `READ_WIKI_PAGE` requests plain introductory text with `exintro=1`, follows article-title redirects through the API, and takes the first 2,000 Python string characters. It does **not** read the full article. MediaWiki defines `exintro` as content before the first section.[^tools][^extracts]

There is a truncation-notice bug: the text is cut at 2,000 characters, but the notice is added only when the original extract exceeds 3,000 characters. Extracts of 2,001 through 3,000 characters are therefore shortened without a notice. The returned label `FULL TEXT OF` is misleading.

The preset asks for action text inside a `<thinking>` block while also asking for action-only output. The parser does not enforce either structure: it searches anywhere in the latest combined model response and accepts the first matching marker. Even a marker quoted in narrative can trigger a request. When an action occurs only in `reasoning_content`, the next assistant message may have empty `content`. This is a custom text protocol, not native function calling; the upstream payload has no `tools` field.[^loop]

### Theory counts: what they do and do not mean

The preset asks for four metadata fields: `Dominance_Shift`, `Cognitive_Dissonance_Level`, `World_Entropy`, and `Active_Theories_This_Turn`. The first three are generated narrative annotations, not calibrated measurements. The last is a declaration of use, not independent proof of application in the prose.[^preset]

The backend accepts `Active_Theories_This_Turn` and two legacy alternate names. It attempts JSON parsing, then a permissive regex fallback. Each returned name increments its exact string key. Repeated names in the same array can increment twice; alternate spellings can be separate keys; malformed metadata can introduce unrelated strings as theory names.[^state]

A count of three produces an instruction to switch. The code does not reject the theory, require another search, or delete it from the preset. A declaration at count three can be accepted and incremented to four. The original README's claim of guaranteed exclusion is therefore too strong.

The database file is `theory_db_<sanitized-session>.json` in the **process working directory**. The supplied preset contains no `SESSION_ID` marker. Unless another integration adds one, requests use `theory_db_default.json`. This is not reliable per-chat storage. Markers can also be taken from arbitrary message roles, and different identifiers can sanitize to the same filename. The short-history reset happens before generation succeeds; corrupt JSON is silently treated as an empty database.[^state]

There are **no persistent theory hashes, excerpt digests, source snapshots, or independent checksum verifier** in version 1.5. Those are proposed additions.

### Existing display and transport

A final reply includes a collapsible HTML `Cognitive Matrix` panel containing accumulated proxy events, optional reasoning text from the final model call, and extracted metadata. This is post-completion output embedded in the assistant message, not a live popup. The script escapes the panel's inserted text, but it does not remove the panel from later incoming history. If a client sends that reply back unchanged, the panel and reasoning text become ordinary model context.[^format]

With `stream=true`, the server first completes the entire loop. It then sends the whole response in one SSE content chunk, followed by a finish chunk and `[DONE]`. This is buffered SSE, not progressive token streaming. The JSON/SSE envelope uses fixed identifiers and timestamps, does not report token usage, and normally reports `stop` even when the upstream finish reason was `length`.[^transport]

## Part II. User guide for original version 1.5

### 1. Prepare the files and Python environment

Use a working SillyTavern installation and keep its official `Start.bat` intact. The Chinese instructions appear to mean Python 3.11 or later; no minimum-version matrix or dependency lockfile was supplied. The offline review ran under Python 3.13.5, which is not proof of compatibility with every Python or package version.

The direct third-party imports are `fastapi`, `uvicorn`, and `httpx`. For an isolated setup in Windows Command Prompt:

```bat
cd /d "C:\path\to\SillyTavern\EODHCTSiqsxajs-react-wiki1.5\react-proxy"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install fastapi uvicorn httpx
```

This command derives from the actual imports; it is not a supplied version lock. Record installed versions for reproducibility. If an interpreter is already configured under another command, select that interpreter consistently.

Suggested file arrangement:

```text
SillyTavern/
  Start.bat                       # Official SillyTavern launcher
  Launch-ReAct.bat                 # Optional renamed wrapper, not supplied under this name
  EODHCTSiqsxajs-react-wiki1.5/
    EODHCTSiqsxajs-react-wiki1.5预设.json
    readme.txt
    react-proxy/
      react_proxy.py
      .venv/
```

**Do not install the supplied `start.bat` over SillyTavern's `Start.bat`.** In a normal Windows installation, the names collide, and the wrapper's final `call Start.bat` can call the wrapper again. The original Chinese instructions used a distinct wrapper name. Start the processes separately until this is corrected.[^launcher]

### 2. Configure the actual upstream endpoint

In a private local copy of `react_proxy.py`, edit the configuration constants near lines 27-30:

```python
REAL_LLM_URL = "https://api.deepseek.com/chat/completions"
REAL_LLM_API_KEY = "YOUR_PRIVATE_API_KEY"
REAL_LLM_MODEL = "deepseek-reasoner"
MAX_REACT_ITERATIONS = 5
```

These are the original endpoint/model defaults; the supplied key is empty. Confirm that the selected provider still accepts the configured model. A different provider must return a compatible response shape, and its behavior has not been tested by this review. The URL is the **complete upstream endpoint**, including `/chat/completions`; the code does not append that suffix.

The client-side alias `react-engine` does not select the real model. `REAL_LLM_MODEL` overrides it in the upstream payload. Likewise, many preset controls, including `top_p`, `seed`, and `reasoning_effort`, are not forwarded at all. A forwarded setting is not necessarily effective at the provider; verify the selected model's documentation.[^loop][^deepseek]

Environment variables and `.env` loading are not implemented in the original script. Do not assume setting an environment variable configures these constants. Never commit a configured key or include it in screenshots.

### 3. Start the proxy on loopback

With the environment active and the working directory containing `react_proxy.py`, use:

```bat
python -m uvicorn react_proxy:app --host 127.0.0.1 --port 8001
```

This imports the existing FastAPI application rather than running the file's `__main__` block. It avoids the original `python react_proxy.py` startup, which explicitly binds to `0.0.0.0`. This is an alternative invocation of the original code, not a claim that its default binding was fixed.[^transport][^uvicorn]

The original app has no client authentication or rate limiting and allows broad CORS access. Loopback reduces network exposure but does not make the app an authenticated service. Do not expose it through a public tunnel or port forwarding. A reachable client can otherwise submit generation requests using the server's configured upstream credentials.

In a separate terminal, run the intact official SillyTavern launcher. The supplied wrapper waits only two seconds; it does not verify readiness or automatically activate the environment created above.

### 4. Import the preset and connect

Import `EODHCTSiqsxajs-react-wiki1.5预设.json` as a Chat Completion preset. Inspect the effective Prompt Manager configuration: the ReAct block, relevant dimension prompts, continuation block, and status tracker must actually be included. The stored `prompt_order` configurations differ, so a prompt's presence in the JSON does not prove it is transmitted.[^preset]

Use the same-machine proxy base URL:

```text
http://127.0.0.1:8001/v1
```

Keep the client-facing base URL distinct from the complete upstream endpoint. The preset's saved wildcard address is not the recommended client destination. Select the locally advertised `react-engine` alias as appropriate for the connection; the Python configuration still determines the real upstream model.

A request to `/v1/models` verifies that this route responds; its model list is static and does not test upstream credentials, model availability, Wikipedia, or successful generation.

Keep requests text-only for this version. The preprocessor assumes each `content` value is a string. Content-part lists and explicit null values can raise exceptions rather than being normalized.

### 5. Set conservative context and output limits

Do not treat the preset's saved 2,000,000-token context setting as an actual backend capacity. The proxy performs no context-window accounting. It clamps valid numeric `max_tokens` values to at most 8,192 but does not subtract history, reference text, metadata, or provider-specific reasoning allowances from a model's context budget.[^loop]

Reserve headroom for every accumulated observation and intermediate assistant message. A conceptual constraint for each call is:

```text
serialized input tokens + provider-appropriate generation reservation + margin
<= supported model context capacity
```

The original fixed character-subtraction formula is not a reliable token budget. A 2,000-character excerpt is not necessarily 2,000 tokens. Reducing history, output length, active dimensions, or iterations is a manual compromise in this version. The proxy cannot recover history SillyTavern never sent.

The 120-second upstream HTTPX timeout and 10-second Wikipedia timeout are network-operation timeouts, not a total turn deadline. HTTPX separates connect, read, write, and pool timeouts. Repeated requests can therefore take substantially longer than one configured timeout.[^loop][^tools][^timeouts]

### 6. Run a disposable smoke test

Use a short fictional scene with one or two relevant dimensions. Watch the proxy console for an iteration, actual tool execution, an observation, and a subsequent final reply. The final details panel is supplementary evidence, not a live progress display.

Check the exact JSON database file in the launch working directory. Interpret its values as model-declared counts, not proof of theory application. Back up state before experiments; do not rely on opening a new chat or retaining a short history to provide safe isolation. The original version is best limited to controlled, sequential experiments until state management is repaired.

A tool failure is returned as text to the model, which may still generate a story. A story alone therefore does not prove retrieval succeeded. Enabling streaming does not make progress appear earlier.

### 7. Troubleshooting

| Symptom | Relevant limitation or check |
| --- | --- |
| Repeated command windows or port conflicts | Wrapper name collides with official `Start.bat`; stop the wrapper and restore the official launcher |
| Import error | Activate the intended environment and check `fastapi`, `uvicorn`, `httpx` |
| Static model list works, generation fails | Model list does not test upstream credentials or the configured provider model |
| All chats affect one count file | No session marker is supplied by this preset; default storage is shared |
| Counts disappear after a failed request | Short-history reset occurs before upstream success; corrupt files also load as empty |
| Theory used beyond count three | Exclusion is a model instruction, not a backend check |
| Long wait, then one large reply | Whole-loop buffering; synchronous Wikipedia requests can also block the event loop |
| Maximum-iterations error | Final-only warning was not followed; the last action was not prevented in code |
| Partial story reported as complete | Normal final path overwrites the upstream finish reason with `stop` |
| Generic internal-server error | Exceptions and upstream status codes are not consistently translated into client errors |
| Current context grows unexpectedly | Final HTML diagnostics may return in later history; no automatic context budget exists |

### 8. Data handling and credits

The proxy can run locally while inference remains remote. It sends the assembled chat context to the configured model provider and sends queries/article titles to English Wikipedia. The final reply can contain returned reasoning text; treat logs and chats as private unless deliberately sanitized.

The original app persists theory-name counts but not a structured audit trail of source revisions or excerpt hashes. Its post-completion console/panel events are not a complete provenance record. The proposed status popup and independent hash verifier belong to a future version.

Record the project source hash or commit, effective preset, Python/dependency versions, SillyTavern version, real provider model, settings actually transmitted, and external extensions. Keep secrets, private stories, and generated state out of a public repository.

Credit the author for domain framing and prompt design, disclose LLM assistance with grouping and implementation, and credit ReAct to Yao et al. Preserve this document as original-version documentation when publishing a refactored release.

## Documentation basis

Local references describe the supplied files; external links clarify the relevant API/framework behavior, not a successful live integration.

[^original]: Supplied Chinese `readme.txt`, working-logic items 1 and 6-8 and setup notes.
[^preset]: Supplied `EODHCTSiqsxajs-react-wiki1.5预设.json`, core protocol, nine dimensions, status/continuation prompts, connection settings, and `prompt_order`.
[^tools]: Supplied `react_proxy.py`, `execute_tool()`, lines 59-111.
[^state]: Supplied `react_proxy.py`, lines 35-57, 113-152, and 231-261.
[^loop]: Supplied `react_proxy.py`, `run_react_loop()`, lines 113-290.
[^format]: Supplied `react_proxy.py`, lines 175-288.
[^transport]: Supplied `react_proxy.py`, lines 292-334.
[^launcher]: Supplied `start.bat`, lines 12-18; the earlier Chinese guide names the wrapper differently.
[^react]: Yao, S., et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023, Figure 1 and Section 2. https://arxiv.org/abs/2210.03629
[^extracts]: MediaWiki, *Extension:TextExtracts*, `exintro`. https://www.mediawiki.org/wiki/Extension:TextExtracts
[^deepseek]: DeepSeek, *Thinking Mode*. Provider-specific parameter and reasoning-continuation rules must be checked for the actual endpoint/model. https://api-docs.deepseek.com/guides/thinking_mode/
[^uvicorn]: Uvicorn, *Settings*, application import strings and socket binding. https://uvicorn.dev/settings/
[^timeouts]: HTTPX, *Timeouts*. https://www.python-httpx.org/advanced/timeouts/
