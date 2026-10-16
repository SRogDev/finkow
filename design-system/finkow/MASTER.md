# Design System Master File — Finkow

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Finkow
**Revised:** 2026-10-16 (Phase 1 — supersedes the 2026-09-26 generated file)
**Category:** AI-native investment platform — minimalist financial observatory
**Visual brief:** `docs/VISUAL_DIRECTION.md` (the *why* behind these tokens)

**Historical note:** the 2026-09-26 version of this file specified a green
(`#22C55E`) primary CTA, IBM Plex Sans as primary type, and an "Enterprise
Gateway" dashboard pattern. Those were superseded by the gold visual system
(v2.1) and are removed here. Green is now reserved exclusively for positive
financial movement; it is never a brand or action color.

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Background | `#0A0A0B` | `--color-background` |
| Surface | `#141416` | `--color-surface` |
| Surface raised | `#1C1C1F` | `--color-surface-raised` |
| Foreground | `#F5F3EC` | `--color-foreground` |
| Muted foreground | `#A1A19A` | `--color-muted-foreground` |
| Border | `#26262B` | `--color-border` |
| **Gold (signal)** | `#F59E0B` | `--color-gold` |
| Gold deep | `#B45309` | `--color-gold-deep` |
| Gold soft | `#FFE9A8` | `--color-gold-soft` |
| On gold | `#0A0A0B` | `--color-on-gold` |
| **Positive (financial)** | `#16A34A` | `--color-positive` |
| **Negative (financial)** | `#DC2626` | `--color-negative` |
| Focus ring | `#F59E0B` | `--color-ring` |

**Color notes:**
- Gold is a **signal**, used selectively: primary actions, AI activity, key
  values, discoveries, headings, justified outcomes. ~60/30/10 balance
  (dark surface / secondary content / gold accents).
- Green/red carry financial semantics **only** (gains/losses, up/down
  movement). They are never CTAs, brand elements, or decorative color.
- Hero moments may use a gold gradient `#FFE9A8 → #F59E0B → #B45309`.
  Never as a general background wash.

### Typography

- **Functional font:** Inter — UI text, numbers, labels, dense information.
- **Editorial font:** Fraunces — headings, hero moments, Finkow's voice.
  Used sparingly so it stays distinctive.
- **Mood:** calm, confident, editorial, quietly premium — an observatory, not
  a cockpit.
- **Google Fonts:**
  [Inter](https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap)
  +
  [Fraunces](https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&display=swap');
```

- Numbers that align (portfolio values, ledgers) use tabular numerals:
  `font-variant-numeric: tabular-nums;`

### Spacing Variables

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.35)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.4)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.45)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.5)` | Hero images, featured cards |

Dark surfaces need darker shadows than light ones — the values above are
tuned for `#0A0A0B` backgrounds.

---

## Component Specs

### Buttons

```css
/* Primary button — gold, used only for the one important action per surface */
.btn-primary {
  background: #F59E0B;
  color: #0A0A0B;
  padding: 12px 24px;
  border-radius: 8px;
  font-family: Inter, sans-serif;
  font-weight: 600;
  transition: background-color 200ms ease, transform 150ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  background: #FBBF24;
  transform: translateY(-1px);
}

/* Secondary button — quiet outline, warm neutral */
.btn-secondary {
  background: transparent;
  color: #F5F3EC;
  border: 1px solid #3F3F46;
  padding: 12px 24px;
  border-radius: 8px;
  font-family: Inter, sans-serif;
  font-weight: 600;
  transition: border-color 200ms ease, background-color 200ms ease;
  cursor: pointer;
}

.btn-secondary:hover {
  border-color: #F59E0B;
  background: rgba(245, 158, 11, 0.08);
}

/* Destructive button — reserved for destructive actions only */
.btn-destructive {
  background: transparent;
  color: #DC2626;
  border: 1px solid #DC2626;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: #141416;
  border: 1px solid #26262B;
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-md);
  transition: border-color 200ms ease, box-shadow 200ms ease;
}

/* Gold edge marks something Finkow's AI produced or vouches for */
.card--ai {
  border-color: rgba(245, 158, 11, 0.45);
}
```

### Inputs

```css
.input {
  background: #0A0A0B;
  color: #F5F3EC;
  padding: 12px 16px;
  border: 1px solid #3F3F46;
  border-radius: 8px;
  font-size: 16px; /* 16px minimum — prevents iOS zoom */
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: #F59E0B;
  outline: none;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.25);
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.modal {
  background: #141416;
  border: 1px solid #26262B;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Dark charcoal, editorial calm

**Keywords:** observatory, calm, quiet, premium, editorial, warm dark, gold
signal, plain language

**Best For:** long-term money relationships, reading about your money,
conversational finance

**Key Effects:** restraint — motion and emphasis are earned, never ambient

### Page Pattern

**Pattern Name:** Conversational Observatory

- **Conversion strategy:** one clear question at a time; natural-language
  input is the primary control, forms are progressive disclosure.
- **Home:** persistent portfolio indicator (value, movement + direction, link
  to portfolio view) → natural-language input → recent activity →
  discoveries → few entry points. No chart grid, no candlestick walls, no
  ticker-tape headers.
- **Portfolio view hierarchy:** total value → period performance →
  gains/losses → allocation → positions → recent transactions → full history.
- **Trust signals:** source + freshness of key values; virtual capital
  labeled; deposits never styled as gains; every agent action explains
  itself in plain language.

### Motion

- Purposeful motion only: functional (state changes), informative (draw
  attention to something that changed), expressive (rare, celebratory).
- Calm when idle: no ambient pulsing, no looping decorative motion.
- Respect `prefers-reduced-motion`: decorative motion off, transitions
  minimal, media static.
- State transitions 150–300ms; no layout-shifting hovers.

---

## Anti-Patterns (Do NOT Use)

- ❌ Green (or any color) as primary/brand action color
- ❌ IBM Plex Sans or other corporate-banking type as primary typography
- ❌ Conventional trading-dashboard patterns (candlestick walls, ticker
  tapes, crowded chart grids, "Enterprise Gateway" layouts)
- ❌ Generic unadapted component-library look
- ❌ Excessive gradients, glassmorphism, glows, shadows as the aesthetic
- ❌ Purple/blue "AI glow" or "AI sparkle" clichés
- ❌ Emojis as icons — use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ Missing cursor:pointer on clickable elements
- ❌ Layout-shifting hovers
- ❌ Low contrast text — maintain 4.5:1 minimum contrast ratio
- ❌ Instant state changes — always use transitions (150–300ms)
- ❌ Invisible focus states — focus states must be visible for keyboard nav
- ❌ Guaranteed-return language in UI copy — the backend verifier rejects it

---

## Accessibility (kept)

- 4.5:1 minimum text contrast on all surfaces.
- Visible focus states for keyboard navigation; all interactive elements
  keyboard-operable.
- Moving media must be pausable; pause offscreen/hidden media automatically;
  render a static final state under reduced motion.
- Motion controls (logo carousels, rotating elements) must be keyboard
  operable.

## Responsive (kept)

- Verify at 375px, 768px, 1024px, 1440px. 375px is a first-class citizen.
- 16px minimum input font size (prevents iOS zoom).
- No content hidden behind fixed navbars; no horizontal scroll on mobile.

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] Gold used selectively (signal, not decoration); green/red only for
  financial movement
- [ ] Inter for functional text, Fraunces for editorial headings
- [ ] No emojis used as icons (SVG instead); consistent icon set
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150–300ms); no layout shift
- [ ] Text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars; no horizontal scroll on mobile
- [ ] Data honesty: virtual capital labeled, sources/freshness shown,
  deposits never styled as gains
- [ ] No guaranteed-return language in copy
