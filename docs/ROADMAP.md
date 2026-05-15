# Erg-onomics — Roadmap

Product goal: a premium rowing coach on a $60 board — WHOOP/Garmin quality feel, runs offline, no subscriptions.

---

## Shipped

### Core infrastructure
- [x] BLE connect to PM5 (auto-connect to single erg; picker for multiples)
- [x] Parse all live data: speed, pace, watts, SPM (EMA-smoothed), HR, drive/recovery timing, force, drag factor
- [x] SQLite session log with per-stroke `stroke_log` table
- [x] FTMS broadcast so ErgZone / Zwift on iPad sees the erg over BLE
- [x] TCX export at session end
- [x] espeak audio cues every 500 m / 60 s
- [x] Systemd service (`erg.service`) with auto-restart; passwordless `sudo systemctl restart erg`
- [x] mDNS hostname `erg.local` via avahi; ErgRower fallback hotspot via NetworkManager

### Web UI (FastAPI + `static/index.html`)
- [x] 6-screen swipeable interface: Power, Endurance, Technique, Force Curve, Intervals, Video
- [x] Tap-to-flip cards (cycle between related metrics)
- [x] Session menu (slide-up panel): Start / Pause / Resume / End / Target Pace / Workout
- [x] Header hides during active session to maximise metric space
- [x] BLE status pill with connect-on-tap erg picker
- [x] Pulse animation on BLE dot during drive phase
- [x] Card depth shadows + tap feedback (`scale(0.97)` active state)
- [x] Screen 0 — Power: Watts hero, Pace/SPM/Strokes/Dist/Time cards
- [x] Screen 1 — Endurance: HR hero with zone colour, zone strip, Pace/Dist/Time
- [x] Screen 2 — Technique: Drive/Recovery/Ratio, Drive Length vs Expected (delta in metres), Peak/Avg Force, Peak:Avg ratio, Drag, SPM — all with good/warn/bad colouring
- [x] Screen 3 — Force Curve: live Bezier drive curve (gradient fill, peak dot, dashed reference), Perfect Stroke Streak counter
- [x] Screen 4 — Intervals: interval counter, work/rest progress bar, remaining time/distance
- [x] Screen 5 — Video Analysis: live camera, TF.js MoveNet skeleton overlay, catch/layback angle pills, ghost rower toggle (best-watts stroke at 35% opacity)
- [x] Target pace: modal sets server-side target; pace card colours green/red vs target; `#target-bar` shows active target
- [x] Resumable session prompt on startup
- [x] Version badge in Profile (live git hash from `/api/version`)

### History & analytics
- [x] Session history list (last 30 sessions)
- [x] Post-session summary: stats grid, pace chart, force chart, Strive Score, zone bar, 500 m splits table, PRs, streak, drag factor, workout name
- [x] Personal records: longest distance, longest time, best avg watts, best peak watts, best avg SPM, best pace at every 500 m split distance
- [x] Strive Score (HR zone × time, Peloton-style)
- [x] Training streak (consecutive days)

### Workouts & planning
- [x] 10 preset Concept2 workouts (2000 m, 5000 m, 30 min, etc.)
- [x] Custom workout builder: distance / time / calorie intervals with configurable rest and reps
- [x] 7-day training plan with per-day workout assignment
- [x] Active workout shown in session (interval index, phase, remaining)

### Profile & WiFi
- [x] User profile: name, weight (kg), height (ft/in → cm), DOB
- [x] Expected drive length and peak force derived from height/weight (used in Technique screen)
- [x] WiFi management: status, scan, connect (with password), saved networks, forget
- [x] WiFi falls back to ErgRower hotspot when no known network in range

---

## In Progress

### Visual polish (Phase 1)
- [ ] State glow on cards when metric is in target range (green glow on watts/HR card)
- [ ] Active dot indicator size refinement (9 px active vs 7 px inactive — done for dots, glow on active dot done)

---

## Planned

### Per-stroke video frame sync
Store `video_ts` (wall-clock time) alongside each stroke in `stroke_log`. After session, sync stroke log timestamps with recorded video to allow frame-accurate force-curve overlay.

### Post-session video review
- Scrub through session by stroke number
- Show force curve, drive length, and angle for each stroke
- Overlay ghost (personal best stroke) at selected stroke

### Coaching mode
- Real-time text cues when metrics drift out of target ranges
- E.g. "Shorten the drive" when drive length drops > 15 cm below expected
- Delivered via espeak (already wired) + optional on-screen toast

### Comparison screen
- Side-by-side two-session summary (pace graph overlay, stats diff)
- Already stubbed as `db/comparison.py` (Kivy version existed; web version not yet built)

### Workout summary sharing
- Export as PNG card (pace graph + key stats) for sharing
- Could use server-side Pillow or client-side canvas

### Multi-user support
- Profile picker at session start (stored as separate `user_profile` rows)
- Per-user records and streak tracking (schema already supports `user_id`)

---

## Won't Do

- **Mobile app**: the web app works natively on iPhone/iPad Safari. No native app needed.
- **Cloud sync**: the board runs offline by design. All data stays on the device.
- **Real-time video recording**: video analysis is pose-only (MediaPipe/TF.js in browser). No server-side video storage.
