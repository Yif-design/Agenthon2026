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
provider condition, not a stable contract. Experiments must stop on 429 and must not compare a
partially served candidate with a fully served baseline.

OpenRouter and House use different thinking controls. The client maps:

- House: `chat_template_kwargs.enable_thinking`
- OpenRouter: `reasoning.enabled`

`T4_ENABLE_THINKING=1` enables thinking in either environment. The current default is off.

Sources:

- <https://openrouter.ai/docs/guides/get-started/sovereign-ai>
- <https://openrouter.ai/docs/api/api-reference/models/get-models>
- <https://openrouter.ai/collections/free-models/>

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
