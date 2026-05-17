# Recipe: pixel_crt

CRT-terminal aesthetic. Sharp, phosphorescent, deliberately retro.

## Palette
- background: deep indigo `#0d0033`
- primary: cyan `#00ffff`
- secondary: hot magenta `#ff00ff`
- accent: phosphor amber `#ffaa00`
- success: signal green `#00ff41`

## Typography
- display: `"Press Start 2P", monospace`
- body: `"JetBrains Mono", monospace`

## Motion vocabulary
- Hard pixel snapping (no sub-pixel interpolation)
- 2–3 frame "flicker" on hits and pickups
- CRT scanline overlay at low opacity
- Phosphor decay glow on neon elements (short fade)

## Asset cues
- Snap everything to 8 px or 16 px grid
- Limited palette indexing — max 4 colours per sprite
- No shadows, no blur, no anti-aliasing
- Use Phaser `Graphics` rectangles to draw pixel art procedurally

## Audio cues
- Square wave / triangle wave only (Web Audio `OscillatorNode`)
- ADSR with sharp attack, no reverb
- Optional hum loop at 60 Hz to evoke CRT

## DO NOT
- Smooth gradients, soft shadows, hover glow blur
- Sans-serif system fonts
- Particle systems with sub-pixel motion
