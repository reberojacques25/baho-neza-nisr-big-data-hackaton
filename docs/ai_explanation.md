# Optional AI-assisted explanations ("Explain simply")

| | |
|---|---|
| **Status** | Implemented, **off by default**. No live API call has been made. External transmission is not approved. |
| **Code** | `src/dashboard/explain.py` (facts, plain-language summaries, payload and validation, with no provider code), `src/dashboard/ai_service.py` (configuration, Gemini call, session limits), `src/dashboard/ui.py` (`explanation_panel`) |
| **Tests** | `tests/test_ai_explanation.py`. The provider is mocked; there are no network calls and no real keys. |
| **Verified** | 2026-10-30, against the official Google sources listed in section 2 |

## 1. What it is, and what it is not

On **What if prices rise?** and **Compare support**, every valid result shows **"In plain words"**. This is a deterministic explanation built by Baho Neza from translated templates, with five parts:
1. what you tested;
2. what it means;
3. a simple example;
4. what the support changes (Compare support only);
5. one important limitation.

The optional **Explain simply** button asks Gemini to reword the same verified facts more naturally, in the selected language. The output is labelled **"AI-assisted explanation"**, and the numeric result cards stay separate and authoritative.

The AI explanation is **only an explanation layer**. It is not:
- a calculator;
- a chatbot (there is no free-text input);
- a prediction model;
- an eligibility system;
- a policy adviser.

It explains only outputs Baho Neza has already calculated. It never claims that poverty will go down or that a policy causes an effect.

## 2. Provider, SDK and model (verified 2026-10-30)

| Item | Value | Official source (date read) |
|---|---|---|
| SDK | `google-genai==2.34.0` (Google Gen AI Python SDK), pinned in `requirements*.txt` | PyPI release list (2026-10-30) |
| **Recommended model ID** | **`gemini-3.8-flash`**: stable, newest Flash model, structured outputs supported. Thinking runs at `low` (the `minimal` level is not supported). | [Models](https://ai.google.dev/gemini-api/docs/models) (last updated 2026-10-28); [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) (last updated 2026-10-29) |
| Free tier | `gemini-3.8-flash` input and output: **"Free of charge"** on the Free Tier | [Pricing](https://ai.google.dev/gemini-api/docs/pricing) (last updated 2026-10-28) |
| Lighter alternative | `gemini-3.5-flash-lite`: stable, free tier, structured outputs | Same pages |
| Rate limits | Not published as numbers for the Free Tier; shown in Google AI Studio. Applied **per project**, not per key. "Not guaranteed and actual capacity may vary." | [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) (last updated 2026-10-28) |
| Region | Rwanda is listed as available | [Available regions](https://ai.google.dev/gemini-api/docs/available-regions) (last updated 2026-10-22) |
| Structured output | JSON schema output is supported. Length constraints (`maxLength` and similar) are **not enforced** by the API, so Baho Neza validates length itself. | [Structured output](https://ai.google.dev/gemini-api/docs/structured-output) (last updated 2026-10-21) |

**Notes:**
- **Changing the model.** The model ID is configuration only (`model` in secrets). If you choose another model, check its pricing row and model page first.
- **Thinking level.** If the chosen model rejects the `thinking_level` setting, set `thinking_level = ""`.
- **Re-verify** the model ID and free-tier status before deployment. Google changes models and quotas.
- **Not done:** billing has not been enabled, the project has not been upgraded, and no unlimited free use is promised.

## 3. Data-use terms (free tier): read before approving

Google's [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms) (last updated 2026-04-28, effective 2026-03-23) say the following about the free tier ("Unpaid Services"):

- **Use of content.** Google uses submitted content and generated responses "to provide, improve, and develop" its products. The pricing page marks the free tier "Used to improve our products: Yes", and the paid tier "No".
- **Human review.** "Human reviewers may read, annotate, and process your API input and output". Google disconnects this data from the account before review.
- **What not to submit.** "Do not submit sensitive, confidential, or personal information to the Unpaid Services."
- **EEA, Switzerland and the UK.** Only Paid Services may be used when making API clients available to users there. **A public Streamlit app can be reached from these regions.**
- **Age.** Users must be 18 or older, and the terms bar apps directed at, or likely to be accessed by, people under 18.

**What this means for Baho Neza:**
- The payload holds only published, disclosure-controlled aggregate results and fixed text (section 4). It has no personal data.
- Even so, three decisions are needed before external transmission:
  1. **Data owner.** NISR and the programme owner must confirm that sending these derived aggregates to a third party, where they may be reviewed and used for model improvement, is acceptable under the EICV7 microdata terms. **This has not been confirmed.**
  2. **Region rule.** A public deployment must comply with the EEA, UK and Swiss rule. Either restrict the AI feature to permitted use, or use a paid project.
  3. **Free-tier conditions.** The project owner must accept the free-tier data-use conditions.
- Until these are resolved, keep **`external_data_approved = false`**. The app then runs in fallback-only mode: it shows the deterministic explanation, and the AI button is disabled.

## 4. Outbound data contract (exactly what may be sent)

**When something is sent.** Only when a user asks for results (**Show results** or **Compare**) or clicks **Explain simply**, for a **valid** result, and only when the configuration is complete and approved. One request goes to `generate_content`. It contains:
- **`system_instruction`:** the fixed rules in `explain.SYSTEM_INSTRUCTION`, with the language name filled in.
- **`contents`:** a JSON payload with exactly these keys (enforced in `explain.build_payload` and tested).

| Key | Content |
|---|---|
| `scenario_id` | The 16-character result fingerprint (a hash of the calculation inputs and geography) |
| `kind` | `price` or `compare` |
| `language` | `en` or `rw` |
| `facts` | Allowlisted facts. Each has `meaning` (fixed English description), `unit` and `display` (the value as Baho Neza formats it, in the selected language) |
| `limitations` | Fixed, translated limitation sentences, keyed by ID |
| `support_section_required` | `true` for Compare support |
| `word_target` | Fixed text |

**Allowed facts:**

| Page | Facts |
|---|---|
| **Price** | Place and area; baseline (latest CPI) month; horizon in months; the price increase(s) entered; basket change %; average basket today and the extra cost per household per month; purchasing-power loss %; households in the place; total extra cost per month; the illustrative example (a 100,000 RWF monthly budget and its extra cost, computed in Python) |
| **Compare** | Place and area; programme; recipient group; payment text; price-scenario text; duration in months; number of payments; additional households and people; existing recipients (NSDS only); recipient households below the poverty line in the 2023/24 survey; average extra cost, support and uncovered cost per household per month; direct transfers; delivery costs; total cost; the illustrative example (one household's total over the period, computed in Python) |

**Never sent:**
- household records or IDs;
- household-level predictions or scores;
- raw or microdata;
- suppressed or hidden values (suppressed selections produce no result, and any missing value stops payload creation);
- the exposed-groups table and any value not shown on the page;
- model artefacts;
- secrets;
- any free text typed by users.

**Size limits:** the payload is capped at 8,000 characters and the response at 4,000 characters.

## 5. How AI output is checked (untrusted output)

**Request settings:**
- the response must be structured JSON with fixed sections, plus a `limitation_id` chosen from the allowed list;
- temperature is 0.2 and output is capped at 2,048 tokens (thinking included);
- automatic continuation is off;
- no tools, browsing, function calls or external actions are enabled.

**Validation** (`explain.validate_response`). A response is rejected if:
- it is not valid JSON, or has missing or extra keys;
- it references an unknown fact, or uses an unknown `limitation_id`;
- **any digit appears outside a `[[fact_key]]` placeholder**, so the model cannot write or calculate numbers;
- the "meaning" section has no fact reference, or the "example" section does not use an `example_*` fact;
- it contains markup, links or code characters;
- in English, it makes a banned claim (for example "will reduce poverty", "we recommend");
- a section has too many words, or the total falls outside the word limits (English 60–200, Kinyarwanda 60–280);
- it includes a support section on the price page, or lacks one on Compare support.

**Rendering.** Baho Neza inserts every number itself, from the verified facts, and shows the text as escaped plain text.

**If a response fails,** the deterministic explanation stays on screen with a short message.

These checks reduce the risk of wrong or misleading wording but **do not guarantee** factual or translation accuracy. Number words written out in Kinyarwanda, for example, cannot be fully detected. Review AI wording before sharing it.

## 6. State, limits and failure behaviour

**Calls.**
- There are no calls on page load, slider changes or reruns. The provider is called once when the user asks for results (Show results or Compare), or when they click **Explain simply**, and the button is disabled when configuration, approval or a valid result is missing.

**State.**
- Each explanation is stored in **session state only**, keyed by `(page, result fingerprint, language)`.
- Changing any calculation input changes the fingerprint, so an old explanation can never appear under new settings. It reappears only if the user returns to exactly the same inputs.
- Switching language keeps the numeric results valid. It needs a new explanation, because the language is part of the explanation key but not of the result fingerprint.
- There is no shared cache across users.

**Limits per browser session:**
- duplicate requests for the same key are ignored;
- an in-flight lock prevents parallel requests;
- 20 seconds must pass between requests;
- a session may make at most 8 requests.

**These are not a global spending or quota cap.** Google applies quotas per project, so many sessions together can still exhaust the free quota.

**Timeouts and retries:**
- the request timeout is 25 s;
- the SDK's own retries are turned off;
- **at most one retry**, and only for timeouts and HTTP 500/502/503/504;
- quota errors (HTTP 429) and other client errors are never retried.

| Failure | What the user sees |
|---|---|
| Missing secrets file or section, placeholders, `enabled = false`, `external_data_approved = false` | "AI explanations are not configured." The same generic message every time; configuration details are never shown. |
| Timeout | "The AI explanation took too long." The deterministic summary remains. |
| Quota or rate limit (429) | "The AI service is busy or its free limit has been reached. Try again later." |
| Other provider error | "The AI service is not available right now." |
| Validation failure | "The AI explanation did not pass Baho Neza's checks, so it is not shown." |
| Cooldown or session cap | A short message asking the user to wait, or saying the session limit was reached |

**Logging.** Only short error codes are logged. Prompts, responses and keys are never logged or displayed.

**Without AI.** The core app and the deterministic summaries work fully when Gemini, or the `google-genai` package, is unavailable.

## 7. Local setup

`.streamlit/secrets.toml` was created with placeholders, and Git ignores it (`.gitignore`). `.streamlit/secrets.example.toml` is the tracked, placeholder-only template.

1. Create a Gemini API key in Google AI Studio. **Never paste it into chat, code, URLs, tests or documentation.**
2. Edit `.streamlit/secrets.toml` yourself:

   ```toml
   [ai]
   enabled = false
   provider = "gemini"
   api_key = "<your key>"
   model = "gemini-3.8-flash"   # optional: this verified model is the default when omitted
   external_data_approved = false
   ```

3. Complete the review in section 3. Only after approval, set `external_data_approved = true`, then `enabled = true`.
4. Run the app: `streamlit run src/dashboard/app.py`.

## 8. Streamlit Community Cloud

1. Do **not** commit real secrets. `.streamlit/secrets.toml` is ignored by Git, and only `secrets.example.toml` is tracked.
2. In Streamlit Community Cloud, open the app's **Settings → Secrets** (also offered under "Advanced settings" when deploying). Paste the same TOML as in section 7, with your real key, and save. Streamlit serves it to the app as `st.secrets`. It is never shown to visitors.
3. Keep `enabled = false` or `external_data_approved = false` until the decisions in section 3 are made. A public deployment is reachable from the EEA, UK and Switzerland, where the free tier may not be used.
4. Community Cloud installs `src/dashboard/requirements.txt` (next to the entry point), which includes `google-genai==2.34.0`.

## 9. Translation status

All button, loading, error, section and label text, plus the deterministic templates, are in `src/dashboard/i18n/en.yaml` and `rw.yaml` under `explain.*`. Tests check that the keys match.

**The Kinyarwanda text is machine-drafted and has NOT been reviewed by a fluent speaker.** The `rw.yaml` file is flagged accordingly. AI-generated Kinyarwanda also needs human review before it is shared.
