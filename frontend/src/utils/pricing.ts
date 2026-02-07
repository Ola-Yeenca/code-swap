interface PricingRate {
  input: number;
  output: number;
}

const PRICING: Record<string, PricingRate> = {
  "anthropic/claude-sonnet-4-5": { input: 3.0, output: 15.0 },
  "anthropic/claude-sonnet-4": { input: 3.0, output: 15.0 },
  "anthropic/claude-3.5-sonnet": { input: 3.0, output: 15.0 },
  "anthropic/claude-opus-4": { input: 15.0, output: 75.0 },
  "anthropic/claude-3-haiku": { input: 0.25, output: 1.25 },
  "openai/gpt-4.1": { input: 2.0, output: 8.0 },
  "openai/gpt-4o": { input: 2.5, output: 10.0 },
  "openai/gpt-4o-mini": { input: 0.15, output: 0.6 },
  "google/gemini-2.5-pro": { input: 1.25, output: 10.0 },
  "google/gemini-2.0-flash": { input: 0.1, output: 0.4 },
  "deepseek/deepseek-r1": { input: 0.55, output: 2.19 },
  "deepseek/deepseek-chat": { input: 0.14, output: 0.28 },
};

const FALLBACK_PRICING_RATE: PricingRate = { input: 1.0, output: 3.0 };

export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

export function getPricing(modelId: string): PricingRate {
  return PRICING[modelId] ?? FALLBACK_PRICING_RATE;
}

export function calculateCost(
  tokensIn: number,
  tokensOut: number,
  modelId: string
): number {
  const rate = getPricing(modelId);
  return (tokensIn * rate.input + tokensOut * rate.output) / 1_000_000;
}

export function formatCost(cost: number): string {
  if (cost < 0.01) {
    return `$${cost.toFixed(4)}`;
  }
  return `$${cost.toFixed(2)}`;
}

export function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}k`;
  }
  return count.toLocaleString();
}
