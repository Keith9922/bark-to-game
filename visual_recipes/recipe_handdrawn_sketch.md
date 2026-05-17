# Recipe: handdrawn_sketch

Pencil-on-paper sketchbook. Imperfect, warm, observational.

## Palette
- background: warm paper `#f3ead4`
- primary: graphite `#2a2520`
- secondary: rust red `#a8412c`
- accent: faded blue `#5a7a92`
- subtle wash: `#c8b88a`

## Typography
- display: `"Caveat", "Patrick Hand", cursive`
- body: `"Kalam", sans-serif`
- (fall back to system handwriting fonts if unavailable)

## Motion vocabulary
- 2–4 fps animation (frame-by-frame "boil" effect — redraw shapes with jitter)
- Wobble offset of ±1 px every 100 ms on static elements
- Easing: gentle ease-out, no springs

## Asset cues
- Stroke-only shapes (no fills, or very translucent fills)
- Stroke width 2–3 px, slightly irregular
- Cross-hatching for shadow areas
- Tear-edge borders on panels

## Audio cues
- Acoustic textures only: pencil scratching, paper turning, soft taps
- Avoid synthesised tones — sample-based or filtered noise

## DO NOT
- Solid fills, hard edges, geometric primitives
- Saturated neon colours
- Smooth digital motion
