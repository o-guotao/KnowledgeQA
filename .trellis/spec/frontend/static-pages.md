# Standalone Static Pages (`frontend/public/`)

> Pages that are not part of the React app: plain HTML/CSS/JS, no imports, no build step,
> openable by double-clicking the file. Source of truth: `frontend/public/showcase/`
> (`index.html`, `showcase.css`, `showcase.js`, `ripple.js`).

## What "outside the build" actually means

`frontend/tsconfig.app.json` is `include: ["src"]` and `tsconfig.node.json` is
`include: ["vite.config.ts"]`. A page under `frontend/public/` is in **neither** program.
Vite copies `public/` verbatim into `dist/`.

Two consequences that are easy to get wrong:

1. **Nothing type-checks, bundles, or minifies this code.** No `import`, no npm package, no
   `@/` alias, no TS syntax. A typo'd selector is not a build error — it is a silent
   `querySelector() → null` at runtime.
2. **`npm run build` passing tells you nothing about these files.** Do not use it as a gate
   for them, in either direction.

So the verification has to happen some other way — see *Offline verification* below.

## Classic scripts only

```html
<!-- Wrong: CORS-blocked under file://, page is dead on double-click -->
<script type="module" src="showcase.js"></script>

<!-- Correct -->
<script src="showcase.js"></script>
```

`file://` gives every module an opaque origin, so `type="module"` fails to load. Make the
page work from `file://` and it works everywhere.

## Offline verification (no browser in the loop)

Two layers of assertions, both runnable with `node`:

- **Pure functions** — keep the decision logic (`segmentOf`, `progressToTime`, `beatIndexAt`,
  the seek-write gate) at module top level, free of DOM access, and export it. Aggregation
  loop and DOM access live inside `init()`.
- **HTML ↔ JS ↔ CSS contract** — text-match every selector the JS queries against the HTML,
  and every class the HTML uses against the CSS. This is the layer that catches a
  misspelled selector, which is the dominant silent failure mode here.

> **Warning**: Strip CSS comments before matching against CSS text.
> A header comment reading `all backgrounds are constant` will otherwise match a
> `background` assertion, and a comment saying `no #000 / #fff` will fail a
> "no pure black/white" assertion. Use `css.replace(/\/\*[\s\S]*?\*\//g, '')`.

> **Warning**: Strip HTML comments too, for the same reason and one more. A comment
> that *explains* an attribute — `<!-- data-section="2" picks the folder section -->`
> — contains the attribute verbatim, so `html.match(/data-section="/g).length` counts
> one too many and the "exactly N" assertion fails on a file that is correct. Use
> `html.replace(/<!--[\s\S]*?-->/g, '')` for anything that counts.

### Write assertions structurally, never by copying config values

An assertion that hard-codes a value from `CONFIG` stops testing the code and starts
testing the copy. When the config legitimately changes, the assertion goes red on its
own — so "the test is red" and "the code is wrong" become indistinguishable, and the
usual response is to edit the assertion, which is how a real regression gets waved
through.

Note that `html.match(...)` returns the first match, so a base rule and a media-query
override of the same selector are easy to confuse. Slice the media-query block first
and match inside it.

```js
// Wrong: copies [0.30, 0.70] out of CONFIG — changing beatCuts reddens the test
eq('beatIndexAt(p=0.3)', beatIndexAt(0.3), 1);

// Correct: derive the expectation from the config, assert the structure
const cuts = CONFIG.beatCuts;
cuts.forEach((c, i) => {
  eq(`cut ${i} left neighbour -> beat ${i}`,   beatIndexAt(c - 1e-6), i);
  eq(`cut ${i} itself -> beat ${i + 1}`,       beatIndexAt(c),        i + 1);
});
// plus: cuts are ascending and in (0,1); p 0..1 covers every beat exactly once;
// segment count === cuts.length + 1; monotone non-decreasing across 1000 samples
```

The same applies to derived positions. A nav tab should store **which section** it
targets (`data-section="2"`), not a progress value — a stored progress value is a copy
of the config that goes stale silently when the cuts move, and a stale target reads as
"clicking this nav item does nothing", with no error anywhere.

### The ESM trap when testing a file under `frontend/`

`frontend/package.json` is `"type": "module"`, so **every** `.js` under `frontend/` is
treated as ESM:

```js
require('./frontend/public/showcase/showcase.js');
// ERR_REQUIRE_ESM — and even where Node injects a `module` shim, `module.exports`
// is silently dropped, so the test reports "exports not populated" with no real cause
```

Evaluate the file as a classic script instead:

```js
const sandbox = { module: { exports: {} }, console };
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: FILE });
const m = sandbox.module.exports;
```

Guard the file for both environments so the same source is importable and directly
loadable:

```js
if (typeof document !== 'undefined') { init(); return; }
module.exports = api;
globalThis.__showcase = api;
```

## `position: fixed` has a containing-block trap

Any ancestor with `transform`, `filter`, `perspective`, `contain`, or `will-change` becomes
the containing block for `position: fixed` descendants. A full-bleed fixed layer nested
under one collapses to that ancestor's box instead of the viewport.

For a page built from stacked full-screen fixed layers, this means: **put transforms only on
an inner wrapper, never on the layer itself.**

```css
/* Wrong: .stage becomes the containing block for its own fixed children */
.stage { position: fixed; inset: 0; transform: scale(1.04); }

/* Correct */
.stage       { position: fixed; inset: 0; }
.stage__inner { transform: translate3d(0, var(--py), 0); }
```

Because this fails silently and only at certain scroll/motion states, assert it:

```js
const stage = cssCode.match(/\n\.stage\s*\{[^}]*\}/);
check(!/transform|filter|will-change/.test(stage[0]), '.stage has no transform');
```

### The same trap in reverse: a child that must stay *inside* a fixed parent

The rule above is about what `fixed` descendants do under a transformed ancestor. Its
mirror image bites when you add a layer to an existing fixed stack: `position: absolute`
inside a `position: fixed` parent uses **that parent** as the containing block, so the
child inherits its box and its stacking context. Write `fixed` instead and the child
escapes to the viewport — and silently leaves the parent's `z-index`, landing somewhere
else in the layer order.

```css
/* Wrong: escapes .backdrop, so the layer is no longer at z-index 0 */
.backdrop__scene { position: fixed; inset: 0; }

/* Correct: stays in .backdrop's box and stacking context */
.backdrop__scene { position: absolute; inset: 0; }
```

`absolute` and `fixed` look interchangeable here — both with `inset: 0` cover the same
pixels when nothing scrolls. Assert the property name, not the rendered geometry.

**`z-index` does not accept fractions.** To put a new layer *under* an existing one but
*above* the background, you cannot write `z-index: 0.5` — the value is parsed as an
integer, so `0.5` and `0` are the same and one of the two layers wins arbitrarily. Nest
the new layer inside the lower one instead, which needs no z-index change at all and
keeps a "strictly increasing z-chain" assertion passing untouched.

## `pointer-events` is inherited — a top layer can swallow clicks for a lower one

`pointer-events` is an inherited property, and an element with `inset: 0` at a higher
`z-index` than a sibling does not have to be *opaque* to block it — it only has to be
hit-testable. The failure is nasty because the blocked element is still **visible**:

```css
.copy--panel  { position: absolute; inset: 0; z-index: 6; pointer-events: auto; }
.topbar       { position: fixed;  inset: 0 0 auto; z-index: 5; }
/* The topbar renders, but its nav is unclickable: the panel takes every hit. */
```

Set the container to `none` and open `auto` only where a real interaction exists:

```css
.copy--panel  { pointer-events: none; }
.folder__deck { pointer-events: auto; }   /* the only hit region */
.folder__close{ pointer-events: auto; }
```

Two follow-on rules:

- **A visually-hidden text block must live *outside* any `pointer-events: auto`
  container.** `.sr-only` (1px + `clip-path: inset(50%)`) is invisible but still
  hit-testable, so inside an `auto` parent it becomes an invisible click target that
  swallows real clicks.
- **Derive the click-outside handler from the same container.** A handler on the panel
  that closes on "anything but `.foo`" also fires for clicks on the panel's own content,
  which then contradicts the on-screen hint (e.g. "click the blank area to close"). Put
  the listener on the narrow surface and early-return via
  `closest('[data-toggle]')`.

## Scroll-driven one-shot effects: drive by progress, land on an exact value

An effect that should run once as a section comes into view — an image dropping in, a
reveal, a fill — should be a **pure function of scroll progress**, not a CSS
`animation` fired from an observer. Progress-driven is reversible for free (scrolling
back plays it in reverse), writes nothing while the value is unchanged, and is testable
without a browser.

```js
function sceneDropY(p, span) {
  if (!span) return 0;
  const w = (span[1] - span[0]) * CONFIG.sceneDrop.dropSpan;
  if (!(w > 0)) return 0;                        // degenerate span: start === end
  const u = clamp((p - span[0]) / w, 0, 1);      // must clamp: p is < 0 before the span
  const k = u * u * u;                           // easeInCubic
  return CONFIG.sceneDrop.from * (1 - k);        // exactly 0 at u === 1
}
```

Three things that are easy to get wrong, in order of how much time they cost:

1. **The resting value must be exactly `0`, not "approaching `0`".** `1 - k` reaches
   exactly `0` at `u = 1`. Softening it — `+ (k >= 1 ? 1e-9 : 0)` — leaves the layer on
   a permanent sub-pixel offset. This is the same discipline as a
   fade-out that must snap rather than merely converge: a damped value that only
   approaches its target never satisfies a `=== 0` stop condition.
2. **An increasing function can produce a decreasing displacement.** The layer moves
   *down* while `y` climbs from `-1` to `0`. Writing "monotone non-increasing" for it is
   the natural mistake, and it passes a casual eyeball. Assert the direction explicitly,
   and phrase the label so the direction is auditable:
   `sceneDropY is monotone increasing over the whole range (scrolling back climbs it)`
   with the seed at `-Infinity` and `if (y < prev - 1e-12) ok = false`.
3. **Clamp the progress.** `p` is negative before the span and greater than 1 after it;
   without the clamp the layer leaves the viewport.

Assert the degenerate inputs too — `span` null, start `===` end, start `>` end — all
`0`. A branch that only exists to survive bad input is the one branch no happy-path test
reaches.

## Assertion style: set equality, not `size >= N`

An assertion like `check(refs.size >= 8)` passes when the regex silently stops matching
and the set collapses to whatever still matched. It tests "at least something happened",
which is the one thing you already knew. Assert the exact set, in both directions:

```js
// Wrong: a regex that stops matching still passes
check(refs.size >= 8, 'media refs found');

// Correct: both a missing ref and an unexpected new one go red
const EXPECTED = ['intro-loop.mp4', 'intro.jpeg', 'main.mp4', /* ... */];
EXPECTED.forEach(f => check(refs.has(f), 'referenced: ' + f));
[...refs].forEach(f => check(EXPECTED.includes(f), 'no stray ref: ' + f));
```

The same reasoning applies to counts: `exactly 3 scene layers` beats `at least 3`, and
when the *keys* matter, assert the key set rather than the count. A layer whose key
never matches the value it is switched by is **permanently invisible while every
"the layer exists" assertion stays green** — a silent no-op is exactly what a count
cannot see.

### Record a deliberate relaxation in the assertion itself

Sometimes a previously locked requirement has to be broken on purpose (here: card text
had to be real selectable markup, and a raster replacement broke that). Write the
relaxation into the test as a comment naming what was traded and why:

```js
/* Explicit relaxation, not a post-hoc concession: the three cards are now part of a
   flat image, so their text is no longer selectable. It is preserved in .sr-only, and
   the assertion below enforces exactly that. */
```

Without that comment the next reader cannot distinguish a decision from a drift, and the
default assumption — that the older, stricter-looking assertion was correct — is wrong.

### Give every new assertion teeth

A new assertion that cannot go red is not a test. For each one, copy the sources to a
temp dir, break exactly one thing, run **the real checker** with its source directory
patched to the temp dir, and assert the FAIL count is non-zero. Patch the directory
constant — never copy the regexes, or the two copies drift and the teeth stop
corresponding to the assertion.

```
run(mutated, label, expectFail):  assert  (fails.length > 0) === expectFail
baseline (no mutation, expectFail = false)   // if this is red, nothing else means anything
```

Keep the media directory pointed at the **real** one while mutating the sources. A
mutation that breaks a referenced file path reddens "every reference resolves" for every
mutation, and that noise buries the signal you are actually testing.

## Scroll-driven video scrubbing

Assigning `video.currentTime` starts a seek. Reading it back mid-seek returns the **old**
value, so a loop of `t = f(video.currentTime)` oscillates instead of converging.

> **Warning**: Never read `video.currentTime` as a control value. Keep your own
> `applied` variable, damp that, and write it. Write only when the value actually
> changed — that keeps a settled page at zero seeks per frame.

```js
// Wrong: reads back a stale value while a seek is in flight
target = progress * video.duration;
video.currentTime += (target - video.currentTime) * EASE;

// Correct
applied += (target - applied) * EASE;
if (Math.abs(target - applied) < SNAP) applied = target;
if (applied !== written) { video.currentTime = applied; written = applied; }
```

Required attributes for a scrubbed video: `muted playsinline webkit-playsinline
preload="auto"`.

**Once scrub mode is live, the video must have no `autoplay`** — scrub and autoplay
fight over the playhead. Keeping `autoplay loop` in the *markup* is fine and is the
better default: it is the no-JS and touch fallback, where there is no cursor to scrub
with and the section would otherwise sit frozen on one frame. The rule binds the
runtime state, not the attribute — strip `autoplay`/`loop` in the same branch that
takes over the timeline:

```js
if (scrubMode) {
  video.pause();
  video.loop = false;
  video.removeAttribute('loop');
  video.removeAttribute('autoplay');
} else {
  video.loop = true;
  video.play().catch(noop);
}
```

iOS additionally needs a user-gesture "unlock" (`play().then(() => pause())`) before
`currentTime` writes take effect.

## Decouple timing constants from media duration

Derived positions must be ratios of a normalized progress, never absolute seconds.

```js
// Wrong: welded to "the video is exactly 30s" — a 10s clip makes beat 3 unreachable,
// silently dropping a section with no error
const beats = [{ start: 0, end: 9 }, { start: 9, end: 21 }, { start: 21, end: 30 }];

// Correct: p is already normalized
const beatCuts = [0.30, 0.70];
```

Prefer cut points over spans: `0.30 + 0.40 === 0.7000000000000001`, so a span-based lookup
can put `p = 0.7` in the wrong beat.

## Wrong vs Correct

#### Wrong — animation state stops instead of returning to rest

Deactivating a mouse-following animation by freezing it leaves the figure stuck mid-pose
while it fades out. Drive it to a defined rest value instead, and overlap that return with
the cross-fade rather than sequencing them (sequencing adds the full return + fade time to
every scroll response).

#### Correct — an explicit rest target with its own damping

```js
const rest = CONFIG.restAt * duration;
const target = (seg === 'intro' && mouseMoved) ? mouseTarget() : rest;
const ease   = (seg === 'intro') ? CONFIG.ease : CONFIG.restEase;  // rest must be faster
```

The rest damping has to converge inside the fade duration (at 60fps, `fadeSeconds × 60`
frames is the hard ceiling) — assert the convergence numerically, since it is pure arithmetic:

```js
function settleFrames(from, target, ease, snap) {
  let v = from, n = 0;
  while (Math.abs(v - target) > snap && n < 2000) { v += (target - v) * ease; n++; }
  return n;
}
```
