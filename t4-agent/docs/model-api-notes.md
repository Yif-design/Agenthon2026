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
provider condition, not a stable contract. The runtime now follows a valid `Retry-After` value when
it fits the 30-second ceiling and the remaining deadline; a longer delay falls back without an
early retry. Experiments must still stop an A/B when quota exhaustion leaves one side only partly
served, and must not compare that sample with a fully served counterpart.

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
