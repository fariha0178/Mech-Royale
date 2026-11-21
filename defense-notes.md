# Defensive Notes for the Mech Bot

**Source for everything below:** `protocol.md`. Each point gives the section (§) and line number to look up. Line numbers match in both copies.

Items marked **[my idea]** are my own suggestions, not from the protocol.

---

## 1. How you win or lose
- You score points by dying late. The last mech alive gets 15 points, the first to die gets 0. Surviving matters more than kills. **§4, lines 90–94**
- If time runs out, the mechs with the most HP rank highest. **§4, line 92**
- If you don't answer in 50 ms, your mech keeps doing your last move. After 1 second it stands still. If your bot crashes, it stands still for the rest of the match. **§2, lines 69–72**
- Every answer must carry the same `tick` as the observation. Late answers are dropped. **§2, line 71**

## 2. Your health
- You start with 1400 HP. **§7 Health, line 291**
- You heal 45 HP per second if you go 5 seconds without hitting or being hit. You don't heal outside the zone. Zone damage restarts the 5-second timer. **§7 Health, line 291**
- **Back hits hurt more.** A hit from behind does 1.5 times the damage. Your "front" is the half-circle (180°) your gun points at. Always face your enemy. **§7 Rear armor, line 295**
- The server tells you when a hit came from behind (`rear: true`). **§6 Events table, line 201**
- Your gun turns slowly (`turn_rate`), so turning to face an enemy takes time. **§6 obs table, line 182**
- Each power cube gives +4% max HP and +4% damage (up to 10 cubes). Each cube also makes you 5% bigger, so you are easier to hit. **§10, lines 425–427**
- Killed mechs drop all their cubes plus 2, and every weapon except the gun. **§10, line 426; §7 Weapon loot, line 339**
- Upgrades arrive at 1, 3, 6, 10, 15, 21... cubes. **§10, lines 429–442**
  - "Armor": 8% less damage taken (does not help against the zone).
  - "Sensors": +15 m close-range sensors, +25 m vision, half the sound-direction error.
  - Full list: `hello.config.upgrades`.

## 3. What can hurt you
All weapons: **§7 Weapons, lines 299–319**.

| Weapon | What it does | Line |
| --- | --- | --- |
| Gun | 45 damage per bullet, fast, no drop. No lock-on, so enemies must aim ahead of you. After 12 shots they reload for 2.4 s. | 303 |
| Mortar | Shell in an arc. 200 damage on a direct hit plus blast damage nearby (less with distance). Walls block the blast. Throws you back and drains 45 energy. You can see the shell flying in `projectiles`. | 304 |
| Laser | Instant beam, up to 315 damage, 280 m range. The shooter must hold the trigger (0.75 s for full charge). You can see them charging (`charging: true`) and where they aim, and you hear it. **Move out of their aim line before they let go.** Does +60% damage to a mech carrying a mortar. | 305 |
| Lightning | 45 m range, inside a 30° cone in front of the shooter, needs line of sight. 60 damage, then jumps to up to 2 more targets within 14 m. If it hits a laser holder, their laser stops working for 2 s. | 306 |
| NPC drones | 25 damage per shot, 90 m/s bullets, 1 s cooldown. They shoot whoever attacks them, or mechs within 45 m with line of sight while the drone is within 30 m of its home. | 321–328 |

**Who beats who** (lines 308–313):
- Laser beats mortar.
- Mortar beats lightning.
- Lightning beats laser.
- Gun is neutral.

**[my idea]** Staying out of lightning range, or not standing next to drones and crates, follows from how the chaining works (line 306). The protocol doesn't say it directly.

## 4. How to move
- You speed up and turn slowly (`ground_accel` 58.5, `air_accel` 12), so you can't change direction instantly. **§7 Movement, line 279**
- Your legs and your gun are separate. You can run one way and aim another. **§6 action table, line 226**
- Walls stop you but you slide along them. **§7 Movement, line 281**
- Steps up to 1.2 m are fine. Slopes steeper than 50° can't be climbed. **§7 Movement, lines 282–283**
- Overhangs (bridges) higher than your 9 m body can be walked under. **§7 Movement, line 284**
- 100 energy lets you fly up about 60 m. Energy comes back after a short delay. Gravity is 22 m/s². The map edge is a wall. **§7, line 287**
- Example speeds: walk 11.7, boost 19.5 (from the example observation, **§6, line 154**).
- Your body: 2.5 m radius, 9 m tall, centre at 4.5 m. **§5, lines 101–102**

## 5. Where to hide
- Buildings, bridges and ground stop bullets, shells and lasers. You can shoot (and be shot) under a bridge. **§7 Cover and shots, line 317**
- **Trees do NOT stop shots.** They only block being seen. **§7, line 317; §8, line 372**
- Fences, hedges, cars, parking and water block nothing. **§11, line 454**
- The map is the same every match. Buildings are in `v2/world.json`, ground height in `v2/terrain.i16` (1 m grid). **§11, lines 446–455**
- Mortar blast is blocked by walls. **§7, line 304**

## 6. The shrinking circle (zone)
- Outside the circle you lose HP every second. Armor doesn't help, and you don't heal. **§9, line 409**
- The circle keeps shrinking. You can always see the current circle and the next one. The next circle is always fully inside the current one. **§9, lines 411–415**
- Default circle sizes: 560, 380, 240, 140, 70, 25, 0 m. **§9, line 419**
- Damage per second grows: 20, 35, 60, 100, 160, 260. **§9, line 420**
- Supply drops (boxes that fall from the sky) are called at 70, 140 and 210 s and land 25 s later inside the next circle. Everyone can see them. Stand alone in the 8 m ring for 4 s to get full HP, full energy and 3 cubes. If two or more mechs are in the ring, the timer freezes. **§7 Supply drops, lines 354–361**
- **[my idea]** A drop is probably a place where fights happen, because everyone sees it and only one mech can capture it.

## 7. What you can see and hear
**Seeing (§8, lines 367–374):**
- Everything within 45 m in every direction (buildings block the view).
- Up to 200 m in front of you, inside a 120° cone centred on where you aim (up and down don't matter).
- You remember an enemy's real position for 5 seconds after it leaves view.
- Crates, cubes, pickups and projectiles are listed only while you see them.

**Hearing (§8, lines 378–405):**

| Sound | Heard from |
| --- | --- |
| gun | 320 m |
| mortar launch | 420 m |
| explosion | 420 m |
| laser | 380 m |
| laser charging | 140 m |
| lightning | 160 m |
| jet | 90 m |
| boost | 90 m |
| death | 600 m |
| step | 40 m |
| reload | 60 m |
| drop landing | 600 m |

- Each sound gives a direction (about 7° error), a rough distance (`near` under 60 m, `mid` under 160 m, `far`), and its age. **§8, lines 399–403**
- Sounds don't say who made them, but the sound type tells you the weapon. **§8, lines 397, 405**
- Walking slowly or standing still is silent. Moving faster than 5 m/s makes a step sound every 0.6 s. **§8, line 397**
- Your own sounds are not reported to you. **§8, line 405**

## 8. Information the server gives you every tick
All in **§6, lines 178–195**:
- `events`: who hit you, from which direction, with what weapon, and whether it was from behind (line 201).
- `projectiles`: enemy bullets and shells with position and speed.
- `mechs`: enemies you can see, with their aim, weapons, and whether they are charging a laser.
- `beams`: lasers and lightning others fired that you could see.
- `sounds`: things you heard.
- `zone` and `drops`: always known.
- `self`: your HP, energy, whether you are on the ground, whether you are in the zone, and your stats.
- `alive`: how many mechs are left (your place if you died now).

## 9. My suggested priorities **[my ideas, not from the protocol]**
1. Never miss a tick. Wrap your decision code so one error doesn't crash the bot.
2. Stay inside the zone, and start moving toward the next circle early.
3. Face the attacker (use the `damaged` event direction, sounds, and enemy `aim`).
4. Hide behind buildings, not trees.
5. Dodge laser lines when you see `charging: true`.
6. Stay out of mortar blast areas, and keep some energy for escaping.
7. Don't carry a mortar near laser users.
8. Don't enter a supply-drop ring if other mechs are in it.

## 10. What the kit does not give you
- The example bots (`python/example_bot.py`, `ts/example.ts`, line 1 of each) only walk toward the zone centre, boost when outside the zone, jump every 2 seconds, and shoot the nearest mech. They have no defence code.
- `check/check.py` replays recorded observations and does not react to your actions, so it can't test whether your defence works. **§1, line 38**
