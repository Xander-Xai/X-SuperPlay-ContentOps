"""Small educational single-head causal attention; stdlib only, no trained model.

Inspired by Transformer attention taught in datawhalechina/diy-llm chapter 4.
This demonstration uses one scalar per token with identity Q/K/V projections.
"""
from math import exp, sqrt


def attention(values: list[float], *, causal: bool) -> list[float]:
    """Compute scaled dot-product self-attention in a 1-D toy setting."""
    if not values:
        raise ValueError("values must not be empty")
    if not all(isinstance(x, (int, float)) for x in values):
        raise TypeError("values must contain numbers")

    d_k = 1
    result = []
    for i, query in enumerate(values):
        positions = range(i + 1) if causal else range(len(values))
        logits = [query * values[j] / sqrt(d_k) for j in positions]
        # Stabilize softmax by subtracting the row maximum.
        top = max(logits)
        unnormalized = [exp(logit - top) for logit in logits]
        total = sum(unnormalized)
        weights = [w / total for w in unnormalized]
        result.append(sum(w * values[j] for j, w in zip(positions, weights)))
    return result


def main() -> None:
    original = [1.0, 2.0, 3.0]
    modified_future = [1.0, 2.0, 30.0]
    causal_before = attention(original, causal=True)
    causal_after = attention(modified_future, causal=True)
    full_before = attention(original, causal=False)
    full_after = attention(modified_future, causal=False)
    print("Toy scalar Q=K=V attention (not a trained LLM)")
    print(f"causal     token0: {causal_before[0]:.6f} -> {causal_after[0]:.6f}")
    print(f"non-causal token0: {full_before[0]:.6f} -> {full_after[0]:.6f}")
    print(f"causal prefix unchanged: {causal_before[:2] == causal_after[:2]}")
    assert causal_before[:2] == causal_after[:2], "Future-token leakage in causal mode"
    assert abs(full_before[0] - full_after[0]) > 1.0
    print("PASS: future tokens cannot affect earlier outputs when causal mask is on")


if __name__ == "__main__":
    main()
