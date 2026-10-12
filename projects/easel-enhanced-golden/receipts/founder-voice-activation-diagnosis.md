# Founder voice activation — zero-fee root-cause diagnosis (Issue #34)

- Generated: 2026-10-12, baseline `45c9e9c` (PR #42 merged)
- Provider generation requests sent by this diagnosis: **0**. Money spent: **CNY 0.00**
- Machine-readable companion: `founder-voice-activation-diagnosis.json` (same directory)
- Re-runnable evidence: `python scripts/audit_minimax_host_binding.py --probe-readonly`

## Executive summary

The three `insufficient balance` refusals were **not** three different experiments. All
three requests were sent by the official CLI (`mmx-cli` 1.0.27), and its request-auth
resolver never reads the `MINIMAX_API_KEY` environment variable that ContentOps used to
bind the authorised key into it. Every attempt — including the two labelled
"pay-as-you-go" — authenticated with the **Subscription Key stored in
`~/.mmx/config.json`**. On top of that, the balance evidence was read from
`CONTENTOPS_MINIMAX_BASE_URL` (a legacy host) while the CLI sent the synthesis to the
documented CN host it derives from its own config. The billing evidence and the billed
request never addressed the same service.

The pay-as-you-go + cash route — the one the whole recovery design was for — has
**never actually been transmitted**. That is the real reason the refusals repeated
identically; it is not (proven) a funds problem and not a vendor-policy problem.

## Official documentation checked

| Page | What it fixed |
|---|---|
| [同步语音合成](https://platform.minimax.cn/docs/api-reference/speech-t2a-http) | `POST /v1/t2a_v2`, server `https://api.minimax.cn`; `data.audio` is hex; `extra_info.usage_characters`; `extra_info.usage_voice_count` ("本次请求计费的音色数量（音色首次使用时计费）"); top-level `trace_id` |
| [上传复刻音频](https://platform.minimax.cn/docs/api-reference/voice-cloning-uploadcloneaudio) | `POST /v1/files/upload`, multipart, `purpose=voice_clone` for the main 10 s–5 min clone audio |
| [上传示例音频](https://platform.minimax.cn/docs/api-reference/voice-cloning-uploadprompt) | `purpose=prompt_audio` is a **different** upload, < 8 s — the 15 s WAV is **not** this |
| [音色快速复刻](https://platform.minimax.cn/docs/api-reference/voice-cloning-clone) | `POST /v1/voice_clone` (`file_id` + `voice_id`); free at clone time; unused for 168 h ⇒ deleted |
| [M Plan FAQ](https://platform.minimax.cn/docs/m-plan/faq) | Subscription Key chain: plan quota → credit packs only; **account balance is charged only with a pay-as-you-go API Key** |

## Existing clone: verified, do not redo

`founder_primary_v1` was created 2026-10-12T11:59:16Z. The local private registry
records the upload `file_id`, the sample SHA256 and the creation time; the receipt
committed in `21afc42` records `clone_status=CLONED` from a call whose
`base_resp.status_code` was 0 (the provider wrapper only writes the registry after that
check). The clone call sequence therefore satisfies all four checks: correct upload
endpoint, `purpose=voice_clone`, a valid `file_id` was obtained, and `/v1/voice_clone`
answered success. No verifiable error was found in the creation records.

**No re-upload, no second `/v1/voice_clone`.** First-use deadline: **2026-10-19T11:59:16Z**;
after that the provider deletes the voice.

## Host and region audit

```
CLI_REGION            cn
CLI_ACTUAL_HOST       https://api.minimax.cn        (from ~/.mmx/config.json region=cn)
BALANCE_QUERY_HOST    https://api.minimaxi.com      (CONTENTOPS_MINIMAX_BASE_URL in .env)
HOSTS_MATCH           false
```

A read-only probe (balance + quota reads only; both documented as free) shows both hosts
currently return **identical** account data for both keys — so the split is a
proof-chain/configuration defect, not a measured billing difference. The fix pins the
activation call to the documented CN host so the question cannot recur.

## Credential binding audit

```
CREDENTIAL_BINDING_VERIFIED   false
CLI 1.0.27 auth resolver      --api-key flag → OAuth → ~/.mmx/config.json api_key
MINIMAX_API_KEY env           read only by the CLI's interactive onboarding prompt
injected by ContentOps        MINIMAX_API_KEY (child env)
actually used on the wire     ~/.mmx/config.json api_key (Subscription Key, sk-cp-…)
```

All three attempts: same credential → same refusal, three times. `CLI_REGION_MISMATCH_VERIFIED`
and `CLI_CREDENTIAL_BINDING_VOID` are the root cause pair.

## Raw error preservation

```
HISTORICAL_RAW_RESPONSE_UNAVAILABLE
```

The CLI collapsed provider errors into `API error: <msg> (HTTP 200)` inside
`{"error": {"code": 1, …}}`, where `1` is the CLI's own general-error class. No
`trace_id` and no `base_resp.status_code` survived any attempt; nothing will be
reconstructed. From now on the native adapter stores the full raw JSON under
`.private/diagnostics/` and the public receipt carries only a scrubable summary with the
four code layers kept apart: HTTP status / provider status code / CLI exit code
(not in path ⇒ `null`) / local BillingGuard verdict.

## What changed in code (this PR)

- `src/contentops/media/minimax_native_tts.py` — native CN HTTP adapter: documented-fields-only
  payload builder, host pinned to `https://api.minimax.cn` (refuses anything else before the
  transport is touched), full raw parsing, exactly one request with no retry, credential
  never logged or serialised.
- `scripts/recover_cash_voice_activation.py` — the activation call now uses that adapter;
  balance reads use the same host; structured error taxonomy; private raw diagnostics.
- `scripts/audit_minimax_host_binding.py` — this audit, re-runnable, zero-fee.
- Tests: `tests/test_minimax_native_tts.py` (13), `tests/test_host_binding_audit.py` (9),
  both offline with fake transports; CI also now runs the previously unwired
  `tests/test_cash_activation_recovery.py`.

## Activation status

```
READY_FOR_CONTROLLED_ACTIVATION   false
```

The existing ¥10 cash authorisation and the exposed-key exception are consumed and are
**not** restored by this diagnosis. The configured PAYG key is still the exposed key
(`2ac10c6e9029`). A fourth call requires, from the Founder:

1. rotation of `MINIMAX_CLONE_KEY` (or a new scoped exception, explicitly granted), and
2. a new single-use authorisation (projected total **CNY 9.9154**, ceiling CNY 10.00).

Until both exist, nothing is transmitted. If a new authorisation is granted, the call
runs once through the native adapter against the **existing** voice — zero uploads, zero
clones, zero retries — and, on any refusal, the true `trace_id` and full provider error
go to MiniMax support as-is.
