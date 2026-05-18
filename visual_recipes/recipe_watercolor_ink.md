# Recipe: watercolor_ink

East-Asian ink wash crossed with watercolour bloom. Wet edges, generous
negative space, single brushstroke as composition. Calm and unforced.

## Palette
- background: warm rice paper `#f8f1dc`
- primary ink: 墨黑 `#1c1a17` (true ink, not pure black)
- accent ink: cinnabar 朱砂 `#c43a32`
- water wash 1: indigo bloom `#3a5c7c` (use at 40-60% alpha)
- water wash 2: sage bloom `#7a9a6d` (use at 40-60% alpha)
- highlight: sun-faded gold `#d4a84a`

## Typography
- display: `"Noto Serif SC", "Songti SC", "Cormorant Garamond", serif` (weight 600)
- body: `"Noto Sans SC", "Source Han Sans", sans-serif`
- prefer Chinese characters in headings where the concept allows (e.g. 「鯉」「霧」「雨」)

## Motion vocabulary
- Brushstrokes draw on with a 200-300ms ease-out — never appear instantly
- Wash blooms expand from a point with radial gradient (transparent → wash colour → transparent)
- Subtle paper sway (1-2 px vertical drift, period ~4s) on the whole canvas
- Particles drift slowly downward (max 30 px/s), not gravity-locked

## Asset cues
- Use `ctx.lineCap = "round"` and `ctx.lineJoin = "round"` for all strokes
- Vary stroke width along a path (taper at endpoints) — implement as overlapping circles
- Apply 1-2 px gaussian-style blur (multiple drawImage with offset alpha) on water washes
- 70% of the canvas should remain blank rice paper — composition lives on the right or lower third

## Audio cues
- Single pluck of guzheng / koto (decaying sine + filtered noise)
- Bamboo flute melodic motif (triangle wave with vibrato, 5 Hz)
- Soft rain ambient (filtered noise, very low gain)
- No percussive sharp attack — every onset has a 5-10ms fade-in

## DO NOT
- Use hard outlines or pixel-perfect edges
- Fill the canvas (empty space IS the composition)
- Add neon, glow, or digital-feeling effects
- Animate with snappy linear curves (everything eases)
