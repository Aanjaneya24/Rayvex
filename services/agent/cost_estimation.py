
USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "gpt-4o": (2.50, 10.00),
}


def estimate_cost_usd(model_name: str, *, input_tokens: int, output_tokens: int) -> float:
    prices = USD_PER_MILLION_TOKENS.get(model_name)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
