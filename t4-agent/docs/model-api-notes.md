# Model API notes

Last updated: 2026-09-28

## Official House

- Model: `nvidia/nemotron-3-super-120b-a12b`
- Official snapshot: `rl-030326-fp8`
- Runtime model value: injected `MODEL_NAME`
- API: injected origin plus `/v1/chat/completions`
- Authentication: injected `MODEL_TOKEN`
- Thinking: enabled by default; controlled with `chat_template_kwargs.enable_thinking`
- Development participant access: not yet announced as open

The competition does not suppress reasoning. The House model thinks by default, and the official
route lets the client disable it with
`chat_template_kwargs: {"enable_thinking": false}`. Production currently disables thinking by
default because the controlled `thinking-extraction-v1` experiment produced the same final label
while increasing completion tokens from 213 to 2,143; a 700-token thinking-on call did not reach
parseable JSON. Thinking remains available for a later task-specific A/B, but it is not the default
for bounded evidence extraction.

## Development model selection policy

Free price does not mean equal quota consumption. Models use different tokenizers, may emit
different answer lengths, and may spend hidden or returned tokens on reasoning. Google documents
that `max_output_tokens` includes thought tokens. Gemini quotas can also differ by model and may
include RPM, TPM, RPD or TPD controls. The current per-project limits are visible in AI Studio and
are not a stable public number.

Choose development models in this order:

1. no incremental charge;
2. no thinking for extraction unless an A/B justifies it;
3. reliable bounded JSON;
4. enough quota for the planned experiment;
5. similarity to the official House behavior;
6. only then, nominal model size or paid-list price.

Do not assume that a smaller model consumes fewer tokens, or that a lower paid-list price grants a
larger free quota. Count prompt, final-output and reasoning tokens from every response when usage
metadata is available. Use saved responses for deterministic replay instead of repeating calls.

## Google Gemini development capacity

The Gemini credential is stored in the git-ignored project secret directory. Its value must never
appear in commands, logs, traces, reports or Git. A 2026-09-28 connectivity check returned HTTP 200
for both `gemini-2.5-flash-lite` and `gemma-4-26b-a4b-it`; this proves access, not the project's exact
daily quota. Active limits must be read from Google AI Studio.

Recommended roles:

| Model | Free-tier facts | Thinking | Project role |
|---|---|---|---|
| `gemini-2.5-flash-lite` | Free-tier input/output; 1M-token context; designed for high-volume, cost-efficient work | Does not think by default; `thinkingBudget=0` explicitly keeps it off | Default quota-conscious extractor and JSON/schema check |
| `gemma-4-26b-a4b-it` | Gemma 4 input/output are free and no paid API tier is offered; 256K context; 25.2B total and 3.8B active parameters | Supports thinking; reasoning can consume output budget | Weaker-model stress test closer to a small active-parameter model |
| `gemini-3.1-flash-lite` | Free tier is available; 1M-token context; optimized for high-volume simple processing | Gemini 3 thinking controls differ from 2.5 | Secondary compatibility check, not the default while 2.5 Flash-Lite remains available |

`gemini-2.5-flash-lite` is the default for routine development because its documented default does
not spend tokens on thinking. `gemma-4-26b-a4b-it` is not automatically more quota-efficient merely
because only 3.8B parameters are active; use it when weak-model behavior is the point of the test.
Neither model replaces the official House model in the submitted container.

Gemma 4 uses its own thinking control: the Gemini API documentation specifies thinking level
`minimal` to disable or minimize thinking. The Gemini 2.5 `thinkingBudget=0` setting is not the
documented Gemma 4 control. A 2026-09-28 evidence-ID run without `minimal` produced no valid paired
structured rows and encountered 429/500 responses, so that run cannot support an architecture
decision. See `evaluation/reports/evidence-id-remote-ab-v2.json`.

Quota-saving rules:

- use `countTokens` before unusually large prompts;
- set `thinkingBudget=0` for Gemini 2.5 extraction calls;
- cap output to the smallest value that still permits the target JSON;
- run one representative case before a family-wide experiment;
- cache raw responses and replay parsing/calculation locally;
- stop on 429 instead of consuming retries blindly;
- do not use Search grounding for this project unless a separate experiment requires it;
- never send hidden competition material or sensitive inputs to a free provider.

Sources:

- <https://ai.google.dev/gemini-api/docs/pricing>
- <https://ai.google.dev/gemini-api/docs/rate-limits>
- <https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api>
- <https://ai.google.dev/gemini-api/docs/generate-content/thinking>
- <https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite>
- <https://ai.google.dev/gemma/docs/core/model_card_4>
- <https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api>

## OpenRouter development analogue

The project has a git-ignored OpenRouter credential. The credential is a free-tier key and was
validated without recording its value. On 2026-09-26 OpenRouter exposed
`nvidia/nemotron-3-super-120b-a12b:free` with zero prompt and completion pricing and 262,144-token
catalog context metadata.

This endpoint is a close model-family analogue, not proof of bit-for-bit equivalence with the
official `rl-030326-fp8` serving snapshot.

The free endpoint requires a provider that may collect prompts for training. Public competition
corpus experiments may opt in with `T4_MODEL_ALLOW_DATA_COLLECTION=1`. The default remains denial.
Never enable this option for private or sensitive inputs.

On 2026-09-28 the free-model endpoint reported a 50-request daily allowance and returned HTTP 429
after it was exhausted, with a reset timestamp of `2026-09-28T00:00:00Z`. This is an observed
provider condition, not a stable contract. The runtime now follows a valid `Retry-After` value when
it fits the 30-second ceiling and the remaining deadline; a longer delay falls back without an
early retry. Experiments must still stop an A/B when quota exhaustion leaves one side only partly
served, and must not compare that sample with a fully served counterpart.

OpenRouter's current Free plan advertises 25+ free models and 50 requests per day. Model availability
is dynamic, so `openrouter/free` is unsuitable for reproducible A/B tests because it may route two
requests to different models. Pin an exact `:free` model ID and record the model ID returned by the
API. The exact-family Nemotron endpoint is reserved for small, high-value comparisons with the
official House behavior; routine prompt/schema development should use Gemini Flash-Lite or saved
replays. Do not spend the daily OpenRouter allowance on tests that deterministic code can answer.

Suggested daily allocation is a ceiling, not a target:

- 0 calls for deterministic, schema, retrieval or replay work;
- 1-3 calls for a new prompt/interface smoke test;
- up to 12 calls for a preregistered representative-family A/B;
- a larger run only when it is the held-out decision experiment and enough allowance remains for
  both baseline and candidate.

OpenRouter and House use different thinking controls. The client maps:

- House: `chat_template_kwargs.enable_thinking`
- OpenRouter: `reasoning.enabled`

`T4_ENABLE_THINKING=1` enables thinking in either environment. The current default is off.

Sources:

- <https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after>
- <https://www.rfc-editor.org/rfc/rfc6585.html#section-4>
- <https://openrouter.ai/docs/guides/overview/auth/byok>
- <https://openrouter.ai/docs/guides/get-started/sovereign-ai>
- <https://openrouter.ai/docs/api/api-reference/models/get-models>
- <https://openrouter.ai/collections/free-models/>
- <https://openrouter.ai/pricing/>

## Reproducible development command

```bash
MODEL_ENDPOINT=https://openrouter.ai/api/v1 \
MODEL_NAME=nvidia/nemotron-3-super-120b-a12b:free \
MODEL_API_KEY_FILE=/absolute/git-ignored/key/path \
T4_MODEL_ALLOW_DATA_COLLECTION=1 \
T4_ENABLE_THINKING=0 \
python -m t4agent.cli analyze --task TASK --corpus CORPUS --out ANSWER
```

No key value may appear in commands committed to the repository, logs, traces or reports.

## Local compute preference

Do not download or run local language models on the user's machine. Local unit tests, deterministic
calculators and official NLI checks already installed for the project remain normal development
work; language-model inference should use a legitimate remote free endpoint or the official House
API. Revisit local LLM inference only if the user explicitly changes this preference.

## Remote official NLI availability

On 2026-09-28, the Hugging Face routed inference API required a user token; an anonymous request to
the deployed MoritzLaurer official-judge model returned HTTP 401. No `HF_TOKEN` is configured for
this project. Hugging Face's model page reports the other pinned official judge,
`cross-encoder/nli-deberta-v3-large`, is not deployed by an Inference Provider. The free account
credit is documented as $0.10 per month, but it cannot be used without a token and does not supply
both fixed judge members. Therefore this is not currently an official-equivalent remote path.

Sources:

- <https://huggingface.co/docs/inference-providers/tasks/text-classification>
- <https://huggingface.co/docs/inference-providers/pricing>
- <https://huggingface.co/cross-encoder/nli-deberta-v3-large>
- <https://huggingface.co/MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli>
