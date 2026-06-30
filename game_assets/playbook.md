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
             : state.phase === 'move' ? '← →  swipe / 滑动'
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

## Audio DNA usage with EASY → MEDIUM → HARD curve (REQUIRED)

CLAUDE.md provides concrete integers for the **steady-state** pacing
(Phase 2). The first 20 s MUST be obviously easier so new players get
early wins. Use this 3-phase scaffold — don't just use the raw integers
from frame 0.

```js
// Steady-state values from CLAUDE.md "AUDIO DNA":
const SPAWN_MS_STEADY = 600              // spawn_interval_ms
const MAX_ACTIVE_STEADY = 8              // max_concurrent
const JITTER_PCT_STEADY = 30             // randomness_pct
const ESCALATION = 1.55                  // escalation_per_min (Phase 3 only)

// PHASE 1 — warm-up: slow it WAY down so the first 20 s is winnable.
const SPAWN_MS_WARM = SPAWN_MS_STEADY * 2.0
const MAX_ACTIVE_WARM = Math.max(2, Math.ceil(MAX_ACTIVE_STEADY * 0.5))
const JITTER_PCT_WARM = Math.round(JITTER_PCT_STEADY * 0.3)

const t0 = performance.now()
function elapsedS(now){ return (now - t0) / 1000 }

function currentPacing(now){
  const s = elapsedS(now)
  if (s < 20){
    // Warm-up — easy on purpose
    return { spawnMs: SPAWN_MS_WARM, maxActive: MAX_ACTIVE_WARM, jitter: JITTER_PCT_WARM }
  }
  if (s < 30){
    // Linear ramp warm → standard over 10 s (the spec's escalation_moment
    // banner fires once when the ramp begins at t=20s)
    const k = (s - 20) / 10
    return {
      spawnMs:   SPAWN_MS_WARM + (SPAWN_MS_STEADY - SPAWN_MS_WARM) * k,
      maxActive: Math.round(MAX_ACTIVE_WARM + (MAX_ACTIVE_STEADY - MAX_ACTIVE_WARM) * k),
      jitter:    JITTER_PCT_WARM + (JITTER_PCT_STEADY - JITTER_PCT_WARM) * k,
    }
  }
  if (s < 60){
    return { spawnMs: SPAWN_MS_STEADY, maxActive: MAX_ACTIVE_STEADY, jitter: JITTER_PCT_STEADY }
  }
  // Phase 3 — apply escalation_per_min on top of steady
  const minutesPast = (s - 60) / 60
  const factor = Math.pow(ESCALATION, minutesPast)
  return {
    spawnMs:   Math.max(120, SPAWN_MS_STEADY / factor),
    maxActive: Math.min(20, Math.round(MAX_ACTIVE_STEADY * Math.min(2, factor))),
    jitter:    JITTER_PCT_STEADY,
  }
}

let nextSpawn = performance.now() + SPAWN_MS_WARM
function maybeSpawn(now){
  const { spawnMs, maxActive, jitter } = currentPacing(now)
  if (now < nextSpawn || entities.length >= maxActive) return
  entities.push(makeEntity())
  const j = (Math.random()*2 - 1) * jitter / 100
  nextSpawn = now + spawnMs * (1 + j)
}

// Fire the spec's escalation_moment banner once at t=20s (warm → standard
// handoff). Optionally fire again at t=60s (standard → pressure).
let warmupBannerFired = false, pressureBannerFired = false
function maybeFirePhaseBanner(now){
  const s = elapsedS(now)
  if (!warmupBannerFired && s >= 20){
    escalate('WAVE 2 / 第二波')   // or whatever the spec says
    warmupBannerFired = true
  }
  if (!pressureBannerFired && s >= 60){
    escalate('+SPEED / 加速')
    pressureBannerFired = true
  }
}
```

**Why this matters:** dropping a first-time player straight into steady-state
pacing feels punishing and many quit before the 20 s mark. The warm-up gives
them a couple of free wins, the WAVE 2 banner makes the difficulty step
feel earned, and the steady-state pacing then lands with weight rather than
overwhelming.

## Round-1 floor (REQUIRED for wave / round / level games)

Pacing knobs alone are not enough for round-based games — the QUOTA needs to
drop too. Concrete rules:

```js
// Wave-based example: spec says round 1 should be obviously winnable.
// At MOST half the steady-state quantity in round 1.
const ROUND_QUOTA_STEADY = 6       // e.g. need 6 catches per round at steady state
const ROUND_QUOTA_ROUND1 = Math.max(1, Math.floor(ROUND_QUOTA_STEADY / 2))  // 3

// And mute the fail path entirely for the first 20 s — even if the player
// would lose, treat strikes as ignorable feedback only:
let strikes = 0
function onMiss(){
  strikes++
  if (elapsedS(performance.now()) < 20) return       // no-fail during warm-up
  if (strikes >= 3) lose()
}
```

A first-time player MUST reach "Round 1 cleared" within ~30 s of play, with
zero strikes. If they can't, the round-1 quota / spawn-rate / threat level
needs to drop further — adjust until tested-on-a-friend it's an easy "I won".

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

### Link_pair (连连看 / lianliankan — tap two identical tiles connectable by ≤2 turns)

Mobile: large tap targets, tap highlights tile, tap second to attempt clear.

```js
// Grid sized to viewport, max ~7 cols × 9 rows; tile ≥ 44px each side.
const COLS = Math.min(7, Math.floor(innerWidth / 56))
const ROWS = Math.min(9, Math.floor((innerHeight - 120) / 56))
const TILE = Math.min(72, Math.floor(Math.min(innerWidth/COLS, (innerHeight-120)/ROWS)))
const KINDS = 6  // distinct shapes/colours; keep small so pairs are findable
let board  // 2D: 0=empty, 1..KINDS=tile-kind
let selA = null  // {r,c}
function newBoard(){
  const pairs = (COLS*ROWS)/2|0
  const flat = []
  for (let i=0;i<pairs;i++){ const k = 1 + (i % KINDS); flat.push(k,k) }
  for (let i=flat.length-1;i>0;i--){ const j=(Math.random()*(i+1))|0; [flat[i],flat[j]]=[flat[j],flat[i]] }
  board = Array.from({length:ROWS}, (_,r) => flat.slice(r*COLS,(r+1)*COLS))
}
// BFS-style path with ≤2 right-angle turns. Cells outside grid count as empty
// (so paths can route around the board edges, classic lianliankan rule).
function canConnect(a, b){
  if (board[a.r][a.c] === 0 || board[b.r][b.c] === 0) return false
  if (board[a.r][a.c] !== board[b.r][b.c]) return false
  const W = COLS+2, H = ROWS+2  // padded grid
  const empty = (r,c) => r<0||r>=ROWS||c<0||c>=COLS || board[r][c]===0
  // try every (turn1, turn2) corner pair; with ≤2 turns the path is one of:
  // straight | L-shape | Z-shape. Implementation left as exercise — keep it
  // simple, accept a corner if both segments are clear of non-empty tiles.
  // ... return true/false
}
function tapTile(r, c){
  if (board[r][c] === 0) return
  if (!selA){ selA = {r,c}; return }
  if (selA.r === r && selA.c === c){ selA = null; return }
  if (canConnect(selA, {r,c})){
    board[selA.r][selA.c] = 0; board[r][c] = 0; score += 10; flash()
  } else {
    miss(); shake()
  }
  selA = null
}
// Mobile input: pointer/click directly → tapTile(r,c). NO drag required.
// Visual: highlight selA with a 2-px glow border + breathing scale 1.0→1.08.
```

### Snake (贪吃蛇 — head + body, eat to grow, dies on self/wall)

Mobile-first: swipe-anywhere in the bottom 60% of the screen sets direction.

```js
const CELL = 24
const COLS = Math.floor(innerWidth / CELL)
const ROWS = Math.floor((innerHeight - 80) / CELL)
let snake, dir, food, tick, tickMs  // dir: {dx,dy}
function reset(){
  snake = [{x: COLS>>1, y: ROWS>>1}]
  dir = {dx: 1, dy: 0}
  tickMs = 180   // warm-up easy speed; Phase 2 drops to 120, Phase 3 to 80
  tick = 0
  placeFood()
}
function placeFood(){
  while (true){
    const f = {x: (Math.random()*COLS)|0, y: (Math.random()*ROWS)|0}
    if (!snake.some(s => s.x===f.x && s.y===f.y)){ food = f; return }
  }
}
function step(){
  const h = snake[0]
  const nx = h.x + dir.dx, ny = h.y + dir.dy
  if (nx<0||nx>=COLS||ny<0||ny>=ROWS) return lose()         // wall
  if (snake.some(s => s.x===nx && s.y===ny)) return lose()  // self
  snake.unshift({x:nx, y:ny})
  if (nx === food.x && ny === food.y){ score++; placeFood() } else snake.pop()
}
function update(dt){ tick += dt*1000; if (tick >= tickMs){ tick = 0; step() } }
// Touch — swipe in any direction:
let t0 = null
addEventListener('touchstart', e => { t0 = e.touches[0] }, {passive:true})
addEventListener('touchend',   e => {
  const t = e.changedTouches[0]; if (!t0) return
  const dx = t.clientX - t0.clientX, dy = t.clientY - t0.clientY
  if (Math.hypot(dx,dy) < 24) return                         // too short
  if (Math.abs(dx) > Math.abs(dy)){
    if (dir.dx === 0) dir = { dx: dx>0?1:-1, dy: 0 }         // can't reverse
  } else {
    if (dir.dy === 0) dir = { dx: 0, dy: dy>0?1:-1 }
  }
  t0 = null
}, {passive:true})
// Keyboard — arrows / WASD set the same direction (still can't reverse).
```

### Sokoban (推箱子 — push crates onto goals; never pull; undo required)

Tight grids (8×8 max), 4-direction dpad, big visible undo button.

```js
// Grid tiles: 0=floor, 1=wall, 2=goal. Crates and player are separate.
let grid, crates, goals, player, history  // history = stack of {player,crates}
function load(level){
  grid = level.grid.map(r => r.slice())
  crates = level.crates.map(c => ({...c}))
  goals = level.goals.slice()
  player = {...level.player}
  history = []
}
function snapshot(){
  history.push({ player: {...player}, crates: crates.map(c => ({...c})) })
  if (history.length > 50) history.shift()
}
function undo(){
  const s = history.pop(); if (!s) return
  player = s.player; crates = s.crates
}
function move(dx, dy){
  const nx = player.x+dx, ny = player.y+dy
  if (grid[ny]?.[nx] === 1) return
  const ci = crates.findIndex(c => c.x===nx && c.y===ny)
  if (ci >= 0){
    const cx = nx+dx, cy = ny+dy
    if (grid[cy]?.[cx] === 1) return
    if (crates.some(c => c.x===cx && c.y===cy)) return
    snapshot(); crates[ci] = {x:cx, y:cy}; player = {x:nx, y:ny}
  } else {
    snapshot(); player = {x:nx, y:ny}
  }
  if (allCratesOnGoals()) winLevel()
}
function allCratesOnGoals(){ return crates.every(c => goals.some(g => g.x===c.x && g.y===c.y)) }
// Mobile dpad — four 44×44px buttons at the bottom + a separate UNDO ↶ button.
// Desktop arrows + Z for undo.
```

### Runner (火柴人快跑 — auto-run; tap to jump, swipe-down to slide)

Single-touch playable. Obstacle spawn cadence + speed driven by AUDIO DNA.

```js
const GROUND_Y = innerHeight - 100
let player = { x: 80, y: GROUND_Y, vy: 0, sliding: 0 }
const GRAVITY = 2200, JUMP_V = -820
const obstacles = []  // { x, w, h, kind: 'low' | 'high' | 'gap' }
function update(dt){
  // physics
  player.vy += GRAVITY*dt; player.y += player.vy*dt
  if (player.y > GROUND_Y){ player.y = GROUND_Y; player.vy = 0 }
  if (player.sliding > 0) player.sliding -= dt
  // scroll obstacles toward player
  const speed = 320 * currentPacingFactor()   // 1.0 base, ramps with DNA
  obstacles.forEach(o => o.x -= speed*dt)
  // collide
  for (const o of obstacles){
    if (o.x < player.x+24 && o.x+o.w > player.x-24){
      const playerH = player.sliding>0 ? 20 : 48
      if (o.kind === 'low'  && player.y > GROUND_Y - playerH) return lose()
      if (o.kind === 'high' && player.sliding <= 0) return lose()
    }
  }
  // spawn next
  if (!obstacles.length || obstacles[obstacles.length-1].x < innerWidth - 240) {
    const r = Math.random()
    obstacles.push({ x: innerWidth + 20, w: 28, h: 48, kind: r<0.6?'low':'high' })
  }
}
function jump(){ if (player.y === GROUND_Y) player.vy = JUMP_V }
function slide(){ if (player.y === GROUND_Y) player.sliding = 0.4 }
// Touch — tap-anywhere to jump, swipe-down to slide.
addEventListener('pointerdown', jump)
let pY = 0
addEventListener('touchstart', e => { pY = e.touches[0].clientY }, {passive:true})
addEventListener('touchmove',  e => {
  if (e.touches[0].clientY - pY > 60){ slide(); pY = 1e9 }
}, {passive:true})
// Keyboard: Space/Up = jump, Down = slide.
```

### Jumper (蹦蹦跳跳 — auto-bounce, steer left/right to land on platforms)

Doodle-jump style. Single horizontal-input axis. Mobile = tilt via swipe-anywhere; desktop = A/D or ←/→.

```js
let player = { x: innerWidth/2, y: innerHeight - 200, vx: 0, vy: 0 }
const GRAVITY = 1400, BOUNCE_V = -780, MAX_VX = 320
const platforms = []  // {x,y,w,kind:'static'|'moving'|'breakable'}
function reset(){
  platforms.length = 0
  for (let i=0;i<7;i++) platforms.push({ x: Math.random()*innerWidth, y: innerHeight - i*80, w: 80, kind:'static' })
}
function update(dt){
  player.vy += GRAVITY*dt; player.y += player.vy*dt
  player.x += player.vx*dt
  // wrap horizontally — classic doodle-jump feel
  if (player.x < 0) player.x += innerWidth
  if (player.x > innerWidth) player.x -= innerWidth
  // land on platform if falling and crossing it
  if (player.vy > 0){
    for (const p of platforms){
      if (player.x > p.x && player.x < p.x+p.w &&
          player.y > p.y - 4 && player.y < p.y + 12){
        player.y = p.y; player.vy = BOUNCE_V; ping()
        if (p.kind === 'breakable') p.dead = true
      }
    }
  }
  // recycle platforms that scroll off bottom; spawn new ones above
  // ... (camera scrolls when player goes above screen midpoint)
  if (player.y > innerHeight + 80) lose()
}
// Horizontal input — tilt via touch drag delta OR keyboard
let dragX = 0
addEventListener('touchmove', e => {
  const x = e.touches[0].clientX
  player.vx = Math.max(-MAX_VX, Math.min(MAX_VX, (x - innerWidth/2) * 4))
}, {passive:true})
addEventListener('touchend', () => { player.vx = 0 }, {passive:true})
// Keyboard: hold A/← / D/→ sets vx.
```

### Roguelike_dive (micro-roguelike — descend floors, pick cards that mutate next floor)

Tight scope: 5–8 floors per run, 4×4 procedural grid each, 3 cards offered between floors.

```js
let floor = 0, hp = 3, deck = []  // active modifier cards
const CARDS = [
  { id:'haste',   name:'快走 / Haste',   apply: state => state.moveSpeed *= 1.5 },
  { id:'thorn',   name:'反伤 / Thorns',  apply: state => state.reflect = true },
  { id:'shield',  name:'护盾 / Shield',  apply: state => state.shield = 1 },
  { id:'fork',   name:'多视野 / Fork',   apply: state => state.vision += 1 },
  { id:'frenzy', name:'狂热 / Frenzy',   apply: state => { state.dmg *= 2; hp -= 1 } },
]
function newRun(){ floor = 0; hp = 3; deck = []; descend() }
function descend(){
  floor++
  if (floor > 7){ winRun(); return }
  generateFloor()              // 4×4 grid, 2-3 enemies, 1 stair, 1 chest
  deck.forEach(c => c.apply(playerState))
}
function clearFloor(){
  // Offer 3 random cards from CARDS — player taps one, it joins deck, descend.
  const offer = pickRandom(CARDS, 3)
  showCardChoice(offer, chosen => { deck.push(chosen); descend() })
}
// Combat is one-hit-trade per adjacent step into enemy tile.
function attack(target){
  target.hp -= playerState.dmg
  if (target.hp <= 0) { removeEnemy(target); maybeClearFloor() }
  else { hp -= target.dmg; if (hp <= 0) gameOver() }
}
// Mobile: 4 large dpad buttons OR tap-an-adjacent-cell to move/attack.
// Card-choice screen: 3 big tap-cards centred, each 280×180 px.
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
