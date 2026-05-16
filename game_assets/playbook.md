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
// Hard pixel-snap text (works with monospace fonts)
function text(str, x, y, size=16, color='#fff', align='left') {
  ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'top'
  ctx.font = size + 'px monospace'
  ctx.fillText(str, Math.round(x), Math.round(y))
}

// Centered rect
function rect(x, y, w, h, color) { ctx.fillStyle = color; ctx.fillRect(Math.round(x), Math.round(y), w, h) }

// Filled circle
function dot(x, y, r, color) {
  ctx.fillStyle = color
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI*2); ctx.fill()
}
```

## Common mechanics — sketches to adapt

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
const beats = []  // {t} timestamps; the line is at y=300; on input.action, check nearest beat dt
```

## Game-over loop

```js
function reset(){ /* restore initial state */ state = 'title' }
addEventListener('pointerdown', () => { if (state === 'title') state = 'play'; else if (state !== 'play') reset() })
addEventListener('keydown', e => { if (e.key === 'Enter' && state !== 'play') state === 'title' ? state = 'play' : reset() })
```

## Visual recipe contract

The recipe in this CLAUDE.md is non-negotiable: palette, typography, motion vocabulary, audio cues, DO-NOTs. If the recipe says "pure black background", do not use any other background. If it forbids gradients, do not use linear-gradient. **Follow it literally.**
