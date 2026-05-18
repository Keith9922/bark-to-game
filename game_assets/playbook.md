# Game Playbook

Reusable patterns Claude can adapt while writing a self-contained HTML5/Canvas
game. Pick what fits the visual recipe — do not paste verbatim if it clashes.

## Single-file scaffold

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>GAME TITLE</title>
  <style> html,body{margin:0;background:#000;overflow:hidden;font-family:monospace} canvas{display:block} </style>
</head>
<body>
  <canvas id="c"></canvas>
  <script>
    const cv = document.getElementById('c')
    const ctx = cv.getContext('2d')
    function fitCanvas() {
      const dpr = devicePixelRatio || 1
      cv.style.width = innerWidth + 'px'
      cv.style.height = innerHeight + 'px'
      cv.width  = Math.floor(innerWidth  * dpr)
      cv.height = Math.floor(innerHeight * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    addEventListener('resize', fitCanvas); fitCanvas()
    // game state, loop, render, input below
    let state = 'title'  // 'title' | 'play' | 'win' | 'lose'
    let last = performance.now()
    function frame(now){
      const dt = Math.min(0.04, (now - last) / 1000); last = now
      update(dt); render()
      requestAnimationFrame(frame)
    }
    function update(dt){ /* ... */ }
    function render(){ /* ... */ }
    requestAnimationFrame(frame)
  </script>
</body>
</html>
```

## Input — keyboard + touch unified

```js
const input = { up:0, down:0, left:0, right:0, action:0 }
const KEY = { ArrowUp:'up', ArrowDown:'down', ArrowLeft:'left', ArrowRight:'right',
              w:'up', s:'down', a:'left', d:'right', ' ':'action', Enter:'action' }
addEventListener('keydown', e => { const k = KEY[e.key]; if (k) input[k] = 1 })
addEventListener('keyup',   e => { const k = KEY[e.key]; if (k) input[k] = 0 })

// Touch: a virtual D-pad zone (left half = movement, right tap = action)
let touch = { x:0, y:0, active:false }
addEventListener('touchstart', e => { touch.active = true; setT(e.touches[0]) }, {passive:true})
addEventListener('touchmove',  e => { setT(e.touches[0]) }, {passive:true})
addEventListener('touchend',   () => { touch.active = false; input.left=input.right=input.up=input.down=0 })
function setT(t){ touch.x = t.clientX; touch.y = t.clientY }
// then in update(): translate touch dx/dy into input.left/right etc.
```

## Web Audio — single AudioContext, lazy boot on first input

```js
let actx
function audio() { if (!actx) actx = new (window.AudioContext||window.webkitAudioContext)(); return actx }

function tone(freq, dur=0.1, type='square', gain=0.08) {
  const a = audio(), now = a.currentTime
  const o = a.createOscillator(), g = a.createGain()
  o.type = type; o.frequency.value = freq
  g.gain.setValueAtTime(0, now)
  g.gain.linearRampToValueAtTime(gain, now + 0.005)
  g.gain.exponentialRampToValueAtTime(0.0001, now + dur)
  o.connect(g).connect(a.destination); o.start(now); o.stop(now + dur + 0.02)
}

function noiseHit(dur=0.08, gain=0.06) {
  const a = audio(), buf = a.createBuffer(1, Math.floor(a.sampleRate*dur), a.sampleRate)
  const d = buf.getChannelData(0)
  for (let i=0;i<d.length;i++) d[i] = (Math.random()*2 - 1) * (1 - i/d.length)
  const src = a.createBufferSource(); src.buffer = buf
  const g = a.createGain(); g.gain.value = gain
  src.connect(g).connect(a.destination); src.start()
}

function kick() {
  const a = audio(), now = a.currentTime
  const o = a.createOscillator(), g = a.createGain()
  o.frequency.setValueAtTime(160, now)
  o.frequency.exponentialRampToValueAtTime(40, now + 0.12)
  g.gain.setValueAtTime(0.4, now); g.gain.exponentialRampToValueAtTime(0.001, now + 0.18)
  o.connect(g).connect(a.destination); o.start(); o.stop(now + 0.2)
}
```

## Canvas helpers

```js
function text(str, x, y, size=16, color='#fff', align='left') {
  ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'top'
  ctx.font = size + 'px monospace'
  ctx.fillText(str, Math.round(x), Math.round(y))
}
function rect(x, y, w, h, color) { ctx.fillStyle = color; ctx.fillRect(Math.round(x), Math.round(y), w, h) }
function dot(x, y, r, color) {
  ctx.fillStyle = color
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI*2); ctx.fill()
}
```

## Always-visible HUD (REQUIRED by spec)

A 24-32 px strip at the top OR bottom of the canvas that persists during play.
Carries: score / lives / progress + a one-line context-aware control hint.
Use the recipe's accent colour for emphasis.

```js
function drawHUD(state) {
  // strip
  rect(0, 0, innerWidth, 28, 'rgba(0,0,0,0.55)')
  // score / lives
  text(`SCORE ${state.score}  ·  ❤ ${state.lives}`, 12, 6, 14, '#fff')
  // contextual control hint — change per game state
  const hint = state.phase === 'aim' ? '点击 / TAP to shoot'
             : state.phase === 'move' ? '← →  swipe  滑動'
             : 'ENTER / TAP'
  text(hint, innerWidth - 12, 6, 14, '#ffd400', 'right')
}
```

## Onboarding affordance (REQUIRED — pulsing target for the first 5 s)

The first interactive element must beg to be touched. Drop the pulse after the
player performs their first action.

```js
let firstActionTaken = false
function drawOnboardingHint(target) {
  if (firstActionTaken) return
  const t = (performance.now() / 1000) % 1.2
  const r = 22 + Math.sin(t * Math.PI * 2) * 6  // 16-28 px breathing
  ctx.strokeStyle = '#ffd400'
  ctx.lineWidth = 3
  ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2); ctx.stroke()
  text('TAP / 点击', target.x, target.y + 32, 12, '#ffd400', 'center')
}
function onFirstAction(){ firstActionTaken = true }
```

## Escalation moment (REQUIRED — visible "now it gets harder")

Use a brief banner + audio sting whenever the difficulty knob ramps. The
banner stays for ~900 ms, then fades.

```js
let banner = null  // { text:string, until:number }
function escalate(label){
  banner = { text: label, until: performance.now() + 900 }
  tone(880, 0.12, 'square', 0.18)  // sting
  tone(440, 0.18, 'square', 0.12)
}
function drawBanner(){
  if (!banner) return
  const left = banner.until - performance.now()
  if (left <= 0) { banner = null; return }
  const a = Math.min(1, left / 400)  // fade out last 400ms
  ctx.fillStyle = `rgba(255,200,0,${0.18 * a})`
  ctx.fillRect(0, innerHeight/2 - 36, innerWidth, 72)
  text(banner.text, innerWidth/2, innerHeight/2 - 12, 28, `rgba(255,255,255,${a})`, 'center')
}
// Trigger at audio-DNA driven moments, e.g. every 25 s:
// setInterval(()=>escalate('WAVE ' + (++wave) + ' / 第' + wave + '波'), 25000)
```

## Audio DNA usage — the bark IS the pacing

CLAUDE.md provides concrete integers. Read them and use them directly:

```js
// example values from the spec:
const SPAWN_MS = 600                    // spawn_interval_ms
const MAX_ACTIVE = 8                    // max_concurrent
const ESCALATION = 1.55                 // escalation_per_min (multiplier/min)
const JITTER_PCT = 30                   // randomness_pct

let nextSpawn = performance.now() + SPAWN_MS
let intervalMs = SPAWN_MS
function maybeSpawn(now){
  if (now < nextSpawn || entities.length >= MAX_ACTIVE) return
  entities.push(makeEntity())
  // jitter the NEXT interval ±JITTER_PCT
  const jitter = (Math.random()*2 - 1) * JITTER_PCT / 100
  nextSpawn = now + intervalMs * (1 + jitter)
}
// minute-by-minute escalation:
setInterval(() => { intervalMs = Math.max(120, intervalMs / ESCALATION) }, 60_000)
```

---

# Common mechanics — sketches to adapt

Each sketch is a starting point. Adapt to the recipe and concept.

### Catch (objects fall, player slides on bottom)

```js
const player = { x: 200, y: 0, w: 60, h: 14, score: 0, lives: 3 }
const items = []  // {x, y, vy, hue}
function spawn(){ items.push({ x: Math.random()*innerWidth, y: -20, vy: 80 + Math.random()*120 }) }
// update(dt): items.forEach(i => i.y += i.vy*dt); collide with player rect; remove or score
```

### Dodge (player moves, threats incoming)

```js
const enemies = []  // {x, y, vx, vy}
// spawn at edges with velocity toward middle; remove when off-screen; lose on collision
```

### Rhythm (incoming beats, tap on the line)

```js
const beats = []                          // {t, lane}
const STRIKE_LINE = innerHeight - 80
const HIT_WINDOW_MS = 140
function spawnBeat(t, lane){ beats.push({t, lane}) }
function tryHit(lane, now){
  // find earliest beat within window on this lane
  const i = beats.findIndex(b => b.lane===lane && Math.abs(b.t - now) <= HIT_WINDOW_MS)
  if (i >= 0) { beats.splice(i,1); score++; flash() } else { miss() }
}
```

### Matching (pair / align by colour or shape)

```js
const cells = []  // {x,y,kind,picked:false}
let pickA = null
function tap(c){
  if (pickA === null) { pickA = c; c.picked = true; return }
  if (pickA.kind === c.kind && pickA !== c) { score++; remove(pickA); remove(c) }
  else { pickA.picked = false; setTimeout(()=> c.picked = false, 300) }
  pickA = null
}
```

### Stacking (drop blocks; tower wobbles)

```js
let crane = { x: 0, vx: 80 }, tower = []  // {x,w}
function update(dt){
  crane.x += crane.vx * dt
  if (crane.x > innerWidth-60 || crane.x < 60) crane.vx *= -1
}
function drop(){
  const prev = tower[tower.length-1] || {x: innerWidth/2, w: 80}
  const block = { x: crane.x, w: prev.w }
  const overlap = Math.max(0, Math.min(block.x+block.w/2, prev.x+prev.w/2) - Math.max(block.x-block.w/2, prev.x-prev.w/2))
  if (overlap <= 0) return lose()
  block.w = overlap; block.x = (Math.max(block.x-block.w/2, prev.x-prev.w/2) + Math.min(block.x+block.w/2, prev.x+prev.w/2)) / 2
  tower.push(block); crane.vx *= 1.05  // crane speeds up — audio DNA escalation
}
```

### Tracing (follow path without leaving it)

```js
// path is a polyline; pointer must stay within RADIUS of the closest path segment
const path = [{x:50,y:50},{x:300,y:80},{x:400,y:200},/* ... */]
const RADIUS = 18
function checkPointer(p){
  const d = minDistToPolyline(p, path)
  if (d > RADIUS) lose()
  else updateProgress(p)  // furthest-reached point along path
}
```

### Memorize (Simon-like sequence)

```js
let sequence = [0]  // grows by 1 each round; values in 0..3 for 4 pads
let showIdx = 0, awaitIdx = 0, phase = 'show'  // show | repeat | success
function tick(now){
  if (phase === 'show'){
    if (showIdx < sequence.length){ flashPad(sequence[showIdx]); showIdx++; pauseUntil(now+500) }
    else { phase = 'repeat'; awaitIdx = 0 }
  }
}
function tapPad(i){
  if (phase !== 'repeat') return
  if (sequence[awaitIdx] === i){ awaitIdx++; if (awaitIdx === sequence.length){ sequence.push(rand(4)); showIdx=0; phase='show' } }
  else lose()
}
```

### Herding (sweep flock to pen)

```js
const flock = []  // {x,y,vx,vy} — each updates with separation + alignment + flee-from-cursor
// Cursor (or finger) acts as a "predator" — flock flees away. Steer them toward the pen rectangle.
// Strays = flock outside pen after T seconds → strikes.
```

### Balancing (counter-steer the tilt)

```js
let tilt = 0, tiltV = 0          // angle, angular velocity
let gust = 0                     // current external torque
function update(dt){
  gust += (Math.random()*2-1) * dt * 0.4
  gust = Math.max(-1, Math.min(1, gust))
  // player input damps tilt
  const corr = (input.left - input.right) * 1.4
  tiltV += (gust - tilt * 0.6 + corr) * dt
  tilt  += tiltV * dt
  if (Math.abs(tilt) > 1.0) lose()
}
```

### Sorting (throw items into correct bins)

```js
const bins = [{x:0.2, kind:'A'},{x:0.5, kind:'B'},{x:0.8, kind:'C'}]  // x = 0..1 of canvas
const incoming = []  // {x, y, vy, kind}
function throwAt(bin){
  const item = incoming[0]; if (!item) return
  if (item.kind === bin.kind) score++
  else strike()
  incoming.shift()
}
```

### Chase (pursue an evader)

```js
const player = {x:0, y:0, sp:160}
const target = {x:200, y:200, sp:120, dir:0}
function update(dt){
  // target jukes every 0.8s
  if ((target.t = (target.t||0) + dt) > 0.8){ target.dir = Math.random()*Math.PI*2; target.t = 0 }
  target.x += Math.cos(target.dir)*target.sp*dt; target.y += Math.sin(target.dir)*target.sp*dt
  // player follows input
  const dx = (input.right-input.left), dy = (input.down-input.up)
  const m = Math.hypot(dx,dy)||1
  player.x += dx/m*player.sp*dt; player.y += dy/m*player.sp*dt
  // tag distance
  if (Math.hypot(player.x-target.x, player.y-target.y) < 30) score++  // tag!
}
```

### Whack (targets briefly appear; tap before they retreat)

```js
const targets = []  // {x,y,until}
function spawnTarget(now, holdMs){ targets.push({x: rand(innerWidth), y: rand(innerHeight), until: now+holdMs}) }
function onTap(now, px, py){
  for (let i=targets.length-1; i>=0; i--){
    const t = targets[i]
    if (Math.hypot(t.x-px, t.y-py) < 36){ targets.splice(i,1); score++; return }
  }
  miss()
}
// audio DNA: holdMs starts at ~1200, shrinks by escalation_per_min
```

### Rotation (rotate falling piece / grid to fit)

```js
let piece = { x: innerWidth/2, y:0, rot: 0, shape: [/* ... */] }
function rotL(){ piece.rot = (piece.rot + 3) % 4 }
function rotR(){ piece.rot = (piece.rot + 1) % 4 }
// piece falls at AUDIO_DNA's spawn_interval_ms cadence; lock-in on bottom
```

### Drawing (reproduce a shown glyph)

```js
const glyphs = [/* arrays of points */]
let demand = null, stroke = []
function showNext(){ demand = glyphs[rand(glyphs.length)]; stroke = [] }
function onMove(p){ if (drawing) stroke.push(p) }
function onUp(){
  const score = fréchetSimilarity(demand, normalize(stroke))
  if (score > 0.7) { hit() } else { miss() }
  showNext()
}
```

### Charge-release (press, hold, release in a band)

```js
let chargeStart = 0, charging = false
const TARGET = 0.7  // 0..1 — band centre
const BAND   = 0.12 // ± width
function onDown(){ chargeStart = performance.now(); charging = true }
function onUp(){
  if (!charging) return
  const t = (performance.now() - chargeStart) / 1500  // full = 1.5s = overload
  charging = false
  if (Math.abs(t - TARGET) <= BAND) hit()
  else if (t > 1.0) overload()
  else miss()
}
function drawMeter(){
  // vertical bar; band highlighted; current charge level animated
}
```

### Routing (lay path tiles before flow overflows)

```js
const grid = []  // 2D of tiles; each {kind:'straight'|'corner'|'cross', rot:0..3, locked:bool}
let flow = { x:0, y:0, dir:0, ms:5000 }  // flow travels along whatever tile it occupies
function tapTile(gx, gy){
  const t = grid[gy][gx]; if (!t || t.locked) return
  t.rot = (t.rot+1) % 4
}
// timer drains; flow must reach the goal tile before timeout
```

### Echo (call-and-respond on a pad)

```js
const pads = ['C','E','G','A']
let call = [], reply = [], phase = 'call'
function newRound(){ call = Array.from({length: 3 + level}, () => pads[rand(4)]); reply = []; phase = 'call'; playSequence(call) }
function tapPad(name){
  if (phase !== 'reply') return
  reply.push(name)
  if (reply[reply.length-1] !== call[reply.length-1]) return lose()
  if (reply.length === call.length){ level++; newRound() }
}
```

### Deflect (aim a bouncer to send incoming back)

```js
let aim = 0  // radians; controlled by pointer or arrows
const incoming = []  // {x,y,vx,vy}
const bouncer = { x: innerWidth/2, y: innerHeight - 80, r: 30 }
function update(dt){
  incoming.forEach(o => { o.x += o.vx*dt; o.y += o.vy*dt })
  // collision with bouncer arc reflects velocity around aim normal
}
function aimAt(p){ aim = Math.atan2(p.y - bouncer.y, p.x - bouncer.x) }
```

---

## Game-over loop

```js
function reset(){ /* restore initial state */ state = 'title' }
addEventListener('pointerdown', () => { if (state === 'title') state = 'play'; else if (state !== 'play') reset() })
addEventListener('keydown', e => { if (e.key === 'Enter' && state !== 'play') state === 'title' ? state = 'play' : reset() })
```

## Visual recipe contract

The recipe in CLAUDE.md is non-negotiable: palette, typography, motion vocabulary, audio cues, DO-NOTs. If the recipe says "pure black background", do not use any other background. If it forbids gradients, do not use linear-gradient. **Follow it literally.**
