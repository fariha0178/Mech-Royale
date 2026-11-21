

## 1. Match shape and what actually scores

- 16 mechs, free-for-all, Ohio State campus. Lockstep: 10 decisions per match-second, each applied for 2 ticks (0.1 s). You get **50 ms** and 1 CPU per decision.
- Score per match = `16 - place` (15 for a win, 0 for dying first). Your score is the mean across matches.
- **Surviving matters more than kills.** Kills only matter because they give cubes and remove threats.
- The match ends when one mech is left or at 8:00 (survivors ranked by HP). The last zone circle closes at about 6:55, so camping the final zone is not a safe plan.

The example bot's plan (walk to the zone, shoot the nearest mech) is a reasonable baseline but ignores the scoring rule: it picks every fight it can see.

---

## 2. The decision loop

1. Server sends `obs` for tick N. Wrapper keeps only the **newest** if several queued.
2. `act(obs)` returns an action dict. Wrapper sets `tick` and attaches any `draw` output as `debug`.
3. If `act()` raises, the wrapper re-sends the last `move`, `aim`, `boost`. **`fire`, `jump`, `reload`, `pick`, `take`, `drop` are dropped**, so a crashing bot stops shooting but keeps walking.
4. No answer in time: continuous parts (`move`, `boost`, `aim`) coast for `coast_s` 1.0 s, then the mech **idles**. A crashed process idles for the rest of the match.

Because of the 50 ms budget, expensive planning (pathfinding over the map, ray casts against prisms) must be cheap or cached.

---

## 3. Target selection

Both examples:

1. Keep only `kind == "mech"` (NPC drones are excluded).
2. Sort by distance (Python 3D, TS horizontal) and take the first.
3. No weighting by HP, weapon carried, `charging`, facing, or whether the target is a threat to *you*.

What `obs.mechs` really contains:
- Everything you can **see now**, plus anything seen in the last `memory_s` (5 s), tracked at its **real current position** even out of sight.
- `hp` only while `vision.show_enemy_hp` is true. `weapons` lists what they hold (this tells you their counter relationship to you). `charging` shows a laser telegraph. `aim` is their torso aim, so you can tell whether they are facing you.

---

## 4. Aiming

```
yaw   = atan2(ty - y, tx - x)
pitch = atan2(tz - z - 2.5, horizontal_distance)     # muzzle z+7 -> target center t.z+4.5
```

Facts:
- `aim` is the **desired** `[yaw, pitch]`. The torso slews at `turn_rate` (4 rad/s in the sample obs) and `pitch_rate`. **Shots leave along `self.aim`** (actual aim), not the commanded one.
- The examples fire the same tick they command the aim, so early shots go wherever the torso currently points.
- **No lead.** Gun bullets fly at 252 m/s with no drop, so you must lead movers. Worked example: target 100 m away strafing at 11.7 m/s (walk speed): flight time 0.40 s, so it moves about 4.6 m. A mech has radius 2.5 m, so the shot **misses**. Rough rule: an un-led gun shot at a strafing mech is only reliable inside about 50 m.
- **Muzzle height moves with cubes.** Each cube makes you 5% bigger, with no cap, so the real muzzle height is in `self.stats.muzzle_height`. The examples hard-code `z + 7` / `+ 2.5` and drift off as cubes accumulate.
- Mortar and lightning use different aim rules (below), but the examples aim them exactly like the gun.

---

## 5. Weapons: real numbers and what the example does with each

The examples set `fire = [True, True]` whenever any mech is visible, at any range, with any weapon, every tick.

### Gun (slot 0 at spawn, the only starting weapon)
- 45 damage, 0.24 s cooldown, 252 m/s, range 230 m, spread 0.6 deg, mag 12, reload 2.4 s.
- Raw DPS 187.5. A full magazine is 2.88 s of fire (540 damage), then 2.4 s reloading. **Against 1400 HP that is about 2.6 magazines of perfect hits**, so sustained fighting is magazine-limited.
- Held fire on the gun is fine, but firing at 230 m with no lead wastes the magazine and leaves you in a reload.

### Mortar
- Shell 72 m/s along your aim, gravity 22 m/s², so **pitch sets range** (max about 235 m at 45 deg). 200 direct damage plus 160 splash (falls to 30% at 7 m, blocked by walls).
- **Concussion:** everyone the blast reaches is thrown (16 m/s, plus 9 m/s up) and loses 45 energy, with falloff. **Your own splash hurts you at 50% and throws you too.**
- The example aims it as a flat line. At 50 m the shell flight time is about 0.7 s and it drops about 5 m, so **it lands short**. At close range it also hits you.

### Laser
- **Hold to charge, release to fire.** Charge builds for up to 0.75 s. Damage scales from 35% (no charge) to 315 (full). Range 280 m, hitscan, then 1.65 s cooldown.
- Releasing before `min_charge` 0.15 s fires as soon as that much is in. **A full charge held 2 s more fires on its own.**
- **While charging you move at half speed**, and everyone who sees you gets `charging: true` plus your `aim`, and it makes a sound (carry 140 m). It can be dodged.
- What the example does: because it holds `fire` true continuously, the laser charges 0.75 s, then sits at full charge for up to 2 s before auto-firing. It telegraphs for about 2.75 s per shot at half speed. Effective output is low and it is slow while doing it.
- **Better:** release the trigger (send `fire` false for that slot) the moment the target is lined up, instead of holding.

### Lightning
- Instant, 60 damage, range **45 m**, within a **30 deg cone** of your aim yaw, needs line of sight, 0.25 s cooldown. It chains to 2 more targets within 14 m (x0.7 each jump). Raw DPS 240 on one target.
- **Costs 3 energy per shot, even with no target.** The example holds it down whenever *any* mech is visible, even at 150 m. That drains the energy it also needs for boost and jet (100 max), leaving the bot unable to boost.
- Hits crates and NPCs too (it picks the nearest target in the cone, which may not be the mech you wanted).

### Weapon triangle (confirmed)
- **Laser beats mortar:** cook-off, +60% damage to a mech holding a mortar.
- **Mortar beats lightning:** concussion throws them out of arc range and drains the energy lightning fires with.
- **Lightning beats laser:** "short" cancels any charge in progress and blocks a new one for 2 s.
- Gun is neutral. The examples never read `ActorObs.weapons`, so they never use this.

### Rear armor
Hits from outside the victim's 180 deg front arc (centered on **aim yaw**) deal x1.5. The example always faces whatever it is shooting, but when it has no target it faces the zone, and `damaged.rear` events are never read.

---

## 6. Weapon acquisition

- `take: <pickup id>` needs you within **4 m horizontal and 4 m vertical**. The examples only check horizontal (and the Python one only looks at `near[0]`).
- It goes into your empty slot, or `drop: <slot>` swaps it in and leaves the old weapon at your feet. **You cannot hold two of the same kind.** A swap cannot drop a laser mid-charge (`busy`).
- A newly taken weapon cannot fire for `max(equip_s, its cooldown)` s (1 s for gun, 1.65 s for laser).
- Sources: 40 floor spawns at match start (a quarter on roofs), 50% of destroyed crates, and dead mechs (all weapons except the gun).
- Floor weights are mortar:laser:lightning 1:1:1 (the gun is 0), so **which weapon you get is random**. The decision is whether to swap given what opponents carry.
- Pickups never despawn, though the zone can close over them.
- Example policy: fill an empty slot 1 with the first non-gun weapon, never swap, never read `took` / `take_failed` events.

---

## 7. Cubes, upgrades and supply drops

**Cubes**
- Each cube: +4% max HP (heals the difference), +4% damage, +5% size. Damage and HP bonuses cap at 10 cubes; **size has no cap**, and bigger means easier to hit.
- Mechs that die drop all their cubes plus 2. NPCs drop 2 cubes each, crates 1. Pickup radius is 3.5 m horizontal, 4 m vertical, and goes to the closest mech.

**Upgrade offers**
- Offers trigger at cube counts 1, 3, 6, 10, 15, 21... with 3 choices. If you don't answer within 5 s, choice 0 is applied (the examples pick 0 anyway).
- Weapon upgrades only appear for weapons you hold at offer time, and they persist on your mech if you drop the weapon. Full effects are in `hello.config.upgrades`, so a real bot should score each choice against the weapons it carries.

**Supply drops** (3 per match, called at 70, 140, 210 s, landing 25 s after the call)
- Stand **alone** in the 8 m ring for 4 s: +3 cubes, **full HP and full energy**. Contested rings freeze the clock.
- Everyone sees them from the moment they are called, so they pull mechs into the same spot. Good for a strong mech, a trap for a weak one. The examples ignore them.

---

## 8. NPC drones and crates

**NPC drones** (12 per match, 350 HP, radius 1.8, height 3.5, ids 100+)
- Wander within 30 m of home. They shoot (25 damage, 90 m/s, 1 s cooldown) at whoever hit them, **or at any mech within 45 m with line of sight** while within 30 m of home.
- Chase until the target is 90 m away or the drone is 60 m from home. Not affected by the zone.
- Each drops **2 cubes**, so a drone is an easy early upgrade (about 350 HP is under 2 s of gun fire).
- The examples filter them out of targets, but they can still hurt the bot, which walks in a straight line and never avoids them. Walking through a drone's 45 m zone means taking 25 damage per second from each one. Visible `projectiles` with `kind: "npc"` and `damaged` events with `weapon: "npc"` are the signal.
- Lightning's auto-targeting can pick an NPC if it is nearer than the mech.

**Crates** (36 per match, 300 HP, about a quarter on rooftops, ids 1000+)
- Destroying one: 1 cube plus 50% chance of a weapon. `hit` events report crate damage.
- The examples never target them. A bot with no second weapon has a reason to: about 300 HP is 1.6 s of gun fire.

---

## 9. Movement, energy and survival

- Walk speed 11.7, boost 19.5 m/s. Boost drains energy on the ground, and **boost in the air is a jet** (up to about 60 m of climb on a full 100 energy). Energy regenerates after a delay without spending.
- Acceleration is limited (58.5 m/s² ground, 12 air), so direction changes take time: strafing is slower than the raw speed suggests.
- Health regenerates 45 HP/s after 5 s without dealing or taking damage, **except outside the zone**. Zone damage restarts the timer.
- The example moves straight at the **next** zone center in a straight line and does not path around buildings. Walls make you slide, ledges over 1.2 m and slopes over 50 deg are blockers, so a straight line often just sticks on a building. The map is in `/arena/v2/world.json` and `terrain.i16` and is the same every match, but the examples never read it.
- Zone damage ramps 20, 35, 60, 100, 160, 260 HP/s. By the late phases it kills a 1400 HP mech in seconds.
- `jump` on `tick % 40` is only decorative: not a dodge, and costs nothing but is not useful.

---

## 10. Vision and sound (what the bot sees, and what it gives away)

**Vision**
- Within **45 m** you see in all directions (buildings block). Out to **200 m** you only see inside a **120 deg yaw wedge** around your torso aim, with line of sight.
- The example bot faces the zone when no enemy is in view, so it effectively scans one 120 deg wedge of the map while walking and is blind behind it beyond 45 m.
- Tracked mechs stay in `mechs` for `memory_s` (5 s) after losing sight.

**Sound** (you hear within carry range; bearing has 7 deg Gaussian error; sounds don't say who)
- gun 320 m, mortar launch and explosion 420, laser 380, laser charge 140, lightning 160, step 40, boost 90, jet 90, reload 60, death 600, crate 220, supply drop landing 600.
- A mech moving faster than 5 m/s makes a `step` every 0.6 s, or `boost` noise. **Standing still or walking slowly is silent.**
- Each weapon has its own sound, so you can tell what a shooter holds. The examples never read `sounds`.
- The example, firing constantly while walking at full speed, broadcasts itself to a 320 m radius.

---

## 11. What the examples ignore 

| Source | What it gives | Used by example? |
|---|---|---|
| `events.damaged` | `bearing`, `by`, `weapon`, `rear` | No |
| `events.hit` / `kill` / `took` / `take_failed` | Confirm shots and pickups | No |
| `sounds` | Direction of unseen shooters, what they hold | No |
| `beams` | Where lasers and lightning came from | No |
| `projectiles` | Incoming gun, mortar and NPC shots with velocity | No |
| `ActorObs.weapons`, `charging`, `aim` | Matchup, telegraph, whether they face you | No |
| `zone.shrink_start/end`, `dps` | When to leave, cost of staying out | Partial (goal only) |
| `drops` | Free cubes, HP and energy | No |
| `alive` | Switch to survival at low counts | No |
| `self.stats`, `weapons[i].stats` | Real muzzle height, ranges, damage | No |
| Map files | Pathfinding, cover, roofs | No |

---

## 12. Summary of the example bot's behavior and gaps

| Area | What it does | Gap |
|---|---|---|
| Movement | Straight line to next zone center | No pathing, cover, strafing, retreat |
| Targeting | Nearest visible mech | No threat, HP, weapon matchup or charging logic |
| Aim | Direct at current position | No lead, no check against actual `self.aim` |
| Gun | Fires at any range | Wastes the 12-round mag, no lead, long reloads |
| Mortar | Flat aim | Falls short, self-splash and self-concussion at close range |
| Laser | Holds trigger | Telegraphs about 2.75 s at half speed, never releases early |
| Lightning | Held down at any range | Drains energy at 3 per shot even out of its 45 m range |
| Loot | First non-gun into empty slot 1 | No swaps, no counter-picking, no retries |
| Upgrades | Always choice 0 | Ignores which weapons are held |
| NPCs / crates | Not targeted | Takes NPC fire, forgoes free cubes and weapons |
| Drops | Ignored | Misses full heal and 3 cubes |
| Awareness | Ignores sounds, beams, events | Cannot find or dodge unseen attackers |
| Scoring | Always fights | Placement matters more than kills |

---

## 13. Suggested improvement order (highest value first)

1. **Gate firing.** Fire only when: target in range for that weapon (lightning 45 m, gun about 100 m), aim error vs `self.aim` is small, weapon off cooldown, and (mortar) the pitch is a computed lob.
2. **Lead the gun** using target `vel` and bullet speed 252 m/s (iterate once or twice for flight time).
3. **Release the laser deliberately** (fire true, then false when lined up), and stop firing lightning without a target in the cone.
4. **Use the triangle:** read `ActorObs.weapons` and prefer targets you counter, and avoid or flee ones that counter you.
5. **Read `events.damaged` and `sounds`** to turn toward unseen attackers. Keep your front arc toward threats (rear damage x1.5).
6. **Collect free cubes:** drones (2 cubes each), crates (1 cube plus 50% weapon), cube pickups, supply drops (3 cubes, full heal).
7. **Pick upgrades** by scoring choices against held weapons from `hello.config.upgrades`.
8. **Navigate the map** with `world.json` and `terrain.i16` instead of straight lines.
9. **Play for placement:** when `alive` is low or HP is low, avoid fights and manage zone timing.
10. **Mind the budget:** everything above must fit in 50 ms on 1 CPU. Precompute map data in `__init__` (the hello budget is 20 s).

---

## 14. Packaging notes (from the kit)

- Docker image, entrypoint speaks the protocol on stdin/stdout. Python needs `-u`. Logs go to **stderr**, never stdout.
- Runs as uid 65534, read-only disk, writable `/tmp` (64 MB), no network, 1 CPU, 512 MB RAM, at most 128 processes.
- `check/check.py` replays a recorded hello plus 300 observations. It checks `ready` timing, schema validity, tick echo, newest-observation rule, debug caps, clean exit, and that no more than 2% of answers are late. **It is not a simulation**, so passing says nothing about play quality.
- Submission: public GitHub repo with the `Dockerfile` at its top level (20 MB max, build under 10 minutes, linux/amd64). Each submission gets 48 practice matches against built-in bots.