# 2026-10-25 Reproduction Record — Lab 01

**Scope:** only the toy causal-attention code and its tests in this folder; it is NOT the upstream Datawhale Assignment 1 training.

**Date:** 2026-10-25. **Environment:** Linux container; Python 3.13.5; only Python standard library; CPU. **Upstream reference commit:** `datawhalechina/diy-llm@95a3b81d4b2686d33afc2d533b0f91d295ec9b78`.

## Command A: `python causal_attention.py`

```text
Toy scalar Q=K=V attention (not a trained LLM)
causal     token0: 1.000000 -> 1.000000
non-causal token0: 2.575210 -> 30.000000
causal prefix unchanged: True
PASS: future tokens cannot affect earlier outputs when causal mask is on
```

**Outcome:** PASS; future-token modification does not change earlier causal attention outputs. Unmasked attention does change.

## Command B: `python -m unittest -v`

```text
test_empty_input_rejected (test_attention.CausalAttentionTests.test_empty_input_rejected) ... ok
test_first_output_equals_first_value_in_causal_mode (test_attention.CausalAttentionTests.test_first_output_equals_first_value_in_causal_mode) ... ok
test_future_token_does_not_change_prefix (test_attention.CausalAttentionTests.test_future_token_does_not_change_prefix) ... ok
test_nonnumeric_rejected (test_attention.CausalAttentionTests.test_nonnumeric_rejected) ... ok
test_unmasked_attention_has_future_leakage (test_attention.CausalAttentionTests.test_unmasked_attention_has_future_leakage) ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.001s

OK
```

**Outcome:** PASS, 5/5. No external data or API call.

**Not reproduced:** full Datawhale textbook exercises, PyTorch GPU attention, tokenizer training, any LLM fine-tuning, Python on Windows. **No performance comparison or saved-hours claim.**

**Visual:** `attention-mask-editorial.svg` exactly reflects rounded numbers from command A. A 1600×900 PNG was generated from the SVG, read back as a valid RGB PNG, and visually inspected in this session. GitHub stores editable SVG; current conversation contains actual PNG. ALT and workflow states are recorded in `TUTORIAL-CARD.md`.
