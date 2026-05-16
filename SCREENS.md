# SCREENS.md — Row Tab Design Contract

Six swipeable screens in the Row tab. Each screen has a single purpose.
Max **8 cells** per screen (2-column × 4-row grid). Cells combine via `wide` (span 2 cols) or `tall` (span 2 rows).

---

## Grid Rules

- Class `.g-grid` — 2-column CSS grid, 7px gap
- Class `.g-card` — one cell
- `.g-card.wide` — spans both columns (2 cells)
- `.g-card.tall` — spans 2 rows (combined with `wide` = 4 cells)
- `.g-card.hero` — large font for the primary number
- **Hard limit: 8 cells per screen**

---

## Screen 0 — Power

**Purpose**: Is the rower on target for this piece? Output and pace at a glance.

| Cell | Metric |
|------|--------|
| Wide hero | Watts (tap → Avg Force) |
| | Pace (/500m) |
| | SPM |
| | Distance |
| | Time |
| | Strokes |
| | Drag Factor |

**Not for**: HR, technique mechanics, interval management.

---

## Screen 1 — Endurance

**Purpose**: Aerobic zone management. Keeping HR in the target zone across a long piece.

| Cell | Metric |
|------|--------|
| Wide hero | HR bpm (tap → Calories) |
| Wide | Zone strip (5-zone visual bar) |
| | Pace |
| | Distance |
| | Time |
| | Watts |

**Not for**: Stroke mechanics, force details, interval countdown.

---

## Screen 2 — Technique

**Purpose**: Stroke mechanics coaching. Used when focusing on quality, not pace.

| Cell | Metric |
|------|--------|
| | Drive Time |
| | Recovery Time |
| | Dr:Rec Ratio (good/warn/bad colour) |
| | SPM |
| | Drive Length |
| | Peak Force |
| | Avg Force |
| | Peak/Avg ratio (good/warn/bad colour) |

**Not for**: Overall pace, HR, interval management. Drag Factor lives on Power (Screen 0).

---

## Screen 3 — Force Curve

**Purpose**: Visual stroke shape. Broad smooth arch = good sequencing; jagged/spiky = poor.

| Cell | Metric |
|------|--------|
| Wide + tall (4 cells) | Drive curve canvas + streak label |
| | Peak Force |
| | Avg Force |
| | Work/Stroke (J) |
| | Drive Length |

The dashed outline is the "ideal" beta-distribution reference shape. The coloured curve is the actual last stroke, coloured green/yellow/red by Peak/Avg ratio.

**Not for**: HR, interval management, pace targets.

---

## Screen 4 — Intervals

**Purpose**: Interval countdown and phase tracking during structured workouts.

| Element | Content |
|---------|---------|
| Counter | Interval # of total |
| Progress bar | Work/rest completion % |
| Remaining | Time or distance left |
| Cards | Pace · Distance |

Only useful when a workout is selected. Shows a prompt otherwise.

**Not for**: Stroke mechanics, HR zone management.

---

## Screen 5 — Video

**Purpose**: Real-time posture feedback using device camera and pose estimation.

| Element | Content |
|---------|---------|
| Camera feed | Live video with skeleton overlay |
| Angle pills | Catch angle · Layback angle · Dr:Rec ratio |

**Not for**: Pace, power, HR, interval management.

---

## PM5 Metric Coverage

Every metric the PM5 exposes has a home screen:

| Metric | Screen |
|--------|--------|
| Pace (/500m) | Power, Endurance |
| Watts | Power, Endurance |
| SPM | Power, Technique |
| Time elapsed | Power, Endurance |
| Distance | Power, Endurance |
| Calories | Endurance (tap HR hero) |
| Heart rate | Endurance |
| Drag factor | Power |
| Drive time | Technique |
| Recovery time | Technique |
| Drive:Rec ratio | Technique |
| Drive length | Technique, Force Curve |
| Peak force (N) | Technique, Force Curve |
| Avg force (N) | Technique, Force Curve |
| Peak/Avg ratio | Technique |
| Work per stroke (J) | Force Curve |
| Interval # / phase | Intervals |
| Interval remaining | Intervals |
| Catch angle | Video |
| Layback angle | Video |
| Drive:Rec ratio (visual) | Video |
