# Recipe: papercut_layered

Stacked paper silhouettes. Five depth planes — each a single flat colour shape
separated by a soft drop shadow. Pure 2D but reads as diorama.

## Palette
- background plane (furthest): pale parchment `#f4ead0`
- mid-back plane: dusty sage `#8aa380`
- midground plane: terracotta `#c4675b`
- mid-front plane: indigo `#3a4a6d`
- foreground plane / silhouettes: near-black `#1a1614`
- accent (UI / score / target highlight): saffron `#f0a437`

## Typography
- display: `"Cormorant Garamond", "Songti SC", serif` (high contrast serif, weight 700)
- body: `"Inter", "PingFang SC", sans-serif`

## Motion vocabulary
- Layers translate at different x-speeds (parallax) — back slow, front fast
- Silhouettes pop in with a 60ms scale-from-0.92 ease-out (origin = bottom-centre)
- Soft drop shadow `0 6px 0 rgba(0,0,0,0.18)` between planes only — not inside a plane
- No rotation; everything stays axis-aligned (papercut grain)

## Asset cues
- Draw everything as solid polygons (`ctx.fill()`) — no strokes except outline silhouettes
- Background hills as rounded blob polygons; foreground objects as cleaner silhouettes
- Add subtle grain via 1-px noise overlay at 4% opacity on the whole canvas

## Audio cues
- Soft mallet / kalimba tones (sine + triangle, decay ~0.6s)
- Cut-paper "swish" via short filtered noise burst on UI events
- Bass drum (low sine) for layer transitions or escalation cues

## DO NOT
- Use gradients (papercut is flat — colour stops kill the illusion)
- Apply blur or glow effects to silhouettes
- Animate by rotating sprites (the depth comes from translation + scale, not spin)
