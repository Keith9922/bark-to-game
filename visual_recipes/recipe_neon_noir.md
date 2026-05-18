# Recipe: neon_noir

Cyberpunk night-city. Wet streets, rain, neon kanji, pure black sky.
Reflective surfaces and chromatic aberration on every light source.

## Palette
- background: pure black `#000000`
- primary: neon cyan `#00e5ff`
- secondary: hot pink `#ff2a8a`
- tertiary: acid yellow `#f5ff00`
- reflection wash: deep teal `#063040` (low alpha overlay for "wet" floor)
- warning red: blood red `#ff1744`

## Typography
- display: `"Orbitron", "Noto Sans Mono CJK SC", monospace` (weight 900)
- body: `"IBM Plex Mono", monospace`
- accent characters: occasional 半角片假名 or 漢字 (e.g. 電脳 / 街 / 雨) used as visual texture, never required reading

## Motion vocabulary
- Soft 4-8 px glow halo around every neon element (use `shadowBlur` + `shadowColor`)
- Rain streaks: thin diagonal lines, `globalAlpha=0.3`, scrolling top→bottom
- 1-pixel RGB shift on bright moving objects (draw three offset copies in R/G/B channels)
- Slow flicker (3% brightness dip, every 200-400ms) on largest neon element

## Asset cues
- Floor reflections: draw the object again, vertically mirrored, at 30% alpha below
- Buildings as silhouette rectangles with random lit windows (1-2 px squares)
- Glow lines should overlap to suggest light bleed on wet glass

## Audio cues
- Synth pads with detuned sawtooth (two oscillators ±5 cents)
- Rain noise loop (filtered pink noise, low-pass at 800 Hz, gain 0.04)
- 808 sub-bass on impact events
- Optional voice-like artefact: short pitch-shifted noise blip on UI confirms

## DO NOT
- Use any non-black background (the contrast IS the recipe)
- Render flat shapes without glow (kills the wet-neon feeling)
- Place neon on light background (always dark behind)
