"""Survival-first Mech Royale bot. Uses only the standard-library wrapper."""
import math
import random
import mechfight as mf


TAU = 2.0 * math.pi


def clamp(value, low, high):
    return max(low, min(high, value))


def distance2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_delta(a, b):
    return (a - b + math.pi) % TAU - math.pi


def unit(x, y):
    length = math.hypot(x, y)
    return (x / length, y / length) if length > 1e-8 else (0.0, 0.0)


def has_weapon(actor, kind):
    return kind in actor.get("weapons", [])


class Bot:
    name = "zonewise"

    def __init__(self, hello: mf.Hello):
        self.config = hello["config"]
        self.pickup_radius = self.config["loot"]["pickup_radius"]
        self.weapon_cfg = self.config["weapons"]
        # The protocol seed is fixed per slot, so using it alone would repeat
        # the same route every match. Use local OS entropy for tactical variety.
        self.rng = random.SystemRandom()
        self.route_key = None
        self.route_goal = None
        self.strafe_sign = 1.0 if self.rng.random() < 0.5 else -1.0
        self.next_strafe_tick = 0

    def _zone_goal(self, obs):
        """Use a changing off-center waypoint that remains safely inside the next circle."""
        zone = obs["zone"]
        center = zone["next_center"]
        radius = max(0.0, zone.get("next_radius", 0.0))
        key = (round(center[0], 1), round(center[1], 1), round(radius, 1),
               round(zone.get("shrink_start", 0), 1), round(zone.get("shrink_end", 0), 1))
        if key != self.route_key:
            self.route_key = key
            offset = min(radius * 0.42, 115.0)
            angle = self.rng.uniform(-math.pi, math.pi)
            self.route_goal = [center[0] + math.cos(angle) * offset,
                               center[1] + math.sin(angle) * offset]
        return self.route_goal or center

    def _upgrade_choice(self, offer, held):
        """Prefer durable/general upgrades, then upgrades for weapons actually held."""
        best_i, best_score = 0, float("-inf")
        for i, choice in enumerate(offer.get("choices", [])):
            uid = choice.get("id", "").lower()
            desc = choice.get("desc", "").lower()
            requires = next((w for w in held if w in uid or w in desc), None)
            score = 0.0
            if "armor" in uid or "damage taken" in desc:
                score += 12
            if "health" in uid or "regen" in uid or "repair" in desc:
                score += 10
            if "sensor" in uid or "vision" in desc:
                score += 5
            if "speed" in uid or "energy" in uid or "boost" in uid:
                score += 6
            if requires and requires in held:
                score += 5
            if any(word in uid for word in ("damage", "rate", "cooldown", "reload")):
                score += 4
            if "gun" in uid and "gun" in held:
                score += 6
            if not score:
                score = 1
            if score > best_score:
                best_i, best_score = i, score
        return best_i

    def _best_target(self, obs, me, enemies):
        """Score threats and useful nearby drones; avoid fixating on harmless distant bots."""
        mx, my, mz = me["pos"]
        held = {w["kind"] for w in me["weapons"] if w}
        mechs = [e for e in enemies if e["kind"] == "mech"]
        candidates = []
        for enemy in enemies:
            pos = enemy["pos"]
            d = math.dist(pos, me["pos"])
            if enemy["kind"] == "npc":
                # Drones are a reasonable early cube source only when no nearby mech can punish us.
                if d > 65 or any(math.dist(m["pos"], me["pos"]) < 110 for m in mechs):
                    continue
                score = d + 35
            else:
                toward_us = math.atan2(my - pos[1], mx - pos[0])
                facing_us = abs(angle_delta(enemy.get("aim", [0, 0])[0], toward_us)) < 0.8
                weapons = set(enemy.get("weapons", []))
                dangerous = bool(("laser" in weapons and "mortar" in held) or
                                 ("mortar" in weapons and "lightning" in held) or
                                 ("lightning" in weapons and "laser" in held))
                countered = bool(("laser" in held and "mortar" in weapons) or
                                 ("mortar" in held and "lightning" in weapons) or
                                 ("lightning" in held and "laser" in weapons))
                score = d - (28 if facing_us else 0) + (24 if dangerous else 0) - (15 if countered else 0)
                if enemy.get("charging"):
                    score -= 12  # prioritize interrupting a telegraphed laser if safely in range
            candidates.append((score, d, enemy))
        best = min(candidates, default=(None, None, None), key=lambda row: row[0])
        return (best[2], best[1]) if best[2] is not None else (None, None)

    def _drop_goal(self, obs, me, enemies):
        """Only detour to an uncontested drop that can be reached inside the next circle."""
        x, y, _ = me["pos"]
        zone = obs["zone"]
        best = None
        for drop in obs.get("drops", []):
            if drop.get("holder") not in (None, me["id"]):
                continue
            pos = drop["pos"]
            d = distance2((x, y), pos)
            if drop.get("lands_in", 0) > max(3.0, d / 8.0):
                continue
            if distance2(pos, zone["next_center"]) > zone.get("next_radius", 0) - 12:
                continue
            if any(e["kind"] == "mech" and distance2(e["pos"], pos) < 70 for e in enemies):
                continue
            # A drop is most valuable when damaged, but 3 cubes are still a useful late-game boost.
            value = d - (90 if me["hp"] < me["max_hp"] * 0.8 else 25)
            if best is None or value < best[0]:
                best = (value, pos)
        return best[1] if best else None

    def _aim_for(self, target, me, weapon_kind, charge=0.0):
        """Compute world yaw/pitch; lead gun shots and use a ballistic mortar arc."""
        mx, my, mz = me["pos"]
        tx, ty, tz = target["pos"]
        dx, dy = tx - mx, ty - my
        horizontal = max(0.01, math.hypot(dx, dy))
        lead = 0.0
        if weapon_kind == "gun":
            speed = self.weapon_cfg["gun"].get("speed", 252)
            lead = horizontal / max(1.0, speed)
        elif weapon_kind == "laser":
            lead = max(0.0, charge)
        if lead:
            vx, vy, vz = target.get("vel", [0, 0, 0])
            tx += vx * lead
            ty += vy * lead
            tz += vz * lead
            dx, dy = tx - mx, ty - my
            horizontal = max(0.01, math.hypot(dx, dy))
        yaw = math.atan2(dy, dx)
        target_scale = 1.0 + 0.05 * target.get("cubes", 0)
        target_center = tz + 4.5 * target_scale
        muzzle = mz + me.get("stats", {}).get("muzzle_height", 7.0)
        dz = target_center - muzzle
        if weapon_kind == "mortar":
            cfg = self.weapon_cfg["mortar"]
            speed, gravity = cfg.get("speed", 72), cfg.get("gravity", 22)
            disc = speed ** 4 - gravity * (gravity * horizontal ** 2 + 2 * dz * speed ** 2)
            if disc >= 0:
                tan_pitch = (speed ** 2 - math.sqrt(disc)) / (gravity * horizontal)
                return yaw, math.atan(tan_pitch)
        return yaw, math.atan2(dz, horizontal)

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        enemies = obs.get("mechs", [])
        act: mf.Action = {"tick": obs["tick"], "fire": [False, False]}
        weapons = me.get("weapons", [])
        held = {w["kind"] for w in weapons if w}
        if obs.get("offer"):
            act["pick"] = self._upgrade_choice(obs["offer"], held)

        # Route toward the future safe area, with opportunistic but cautious drop capture.
        goal = self._drop_goal(obs, me, enemies) or self._zone_goal(obs)
        gx, gy = unit(goal[0] - x, goal[1] - y)
        move_x, move_y = gx, gy

        target, target_dist = self._best_target(obs, me, enemies)
        # In a close encounter, orbit laterally and change sides at irregular
        # intervals instead of offering a predictable straight approach.
        close_threat = min((e for e in enemies if e["kind"] == "mech"),
                           key=lambda e: distance2(e["pos"], (x, y)), default=None)
        if close_threat is not None:
            dx = x - close_threat["pos"][0]
            dy = y - close_threat["pos"][1]
            d = max(1.0, math.hypot(dx, dy))
            if d < 78:
                if obs["tick"] >= self.next_strafe_tick:
                    self.strafe_sign *= -1.0
                    self.next_strafe_tick = obs["tick"] + self.rng.randint(7, 16)
                facing_us = abs(angle_delta(
                    close_threat.get("aim", [0, 0])[0], math.atan2(dy, dx)
                )) < 0.8
                lateral = 0.85 if d > 30 else 0.45
                if facing_us:
                    lateral += 0.35
                move_x += self.strafe_sign * (-dy / d) * lateral
                move_y += self.strafe_sign * (dx / d) * lateral

        for enemy in enemies:
            if enemy["kind"] != "mech":
                continue
            d = max(1.0, distance2(enemy["pos"], (x, y)))
            toward_us = math.atan2(y - enemy["pos"][1], x - enemy["pos"][0])
            facing = abs(angle_delta(enemy.get("aim", [0, 0])[0], toward_us)) < 0.8
            carrying_counter = (("laser" in enemy.get("weapons", []) and "mortar" in held) or
                                ("mortar" in enemy.get("weapons", []) and "lightning" in held) or
                                ("lightning" in enemy.get("weapons", []) and "laser" in held))
            urgency = (1.0 + (0.8 if facing else 0.0) + (0.8 if carrying_counter else 0.0))
            if d < 85:
                strength = urgency * (85 - d) / 85.0
                move_x += (x - enemy["pos"][0]) / d * strength * 1.6
                move_y += (y - enemy["pos"][1]) / d * strength * 1.6

        # Face the most immediate attacker when there is no worthwhile target.
        attacker_bearings = [e.get("bearing") for e in obs.get("events", [])
                             if e.get("type") == "damaged" and e.get("bearing") is not None
                             and e.get("weapon") != "zone"]
        if target is not None:
            aim_target = target
        elif attacker_bearings:
            aim_target = None
        else:
            aim_target = None

        # Dodge visible projectiles on a near-collision trajectory.
        danger = False
        for projectile in obs.get("projectiles", []):
            px, py, pz = projectile["pos"]
            vx, vy, vz = projectile["vel"]
            rx, ry = x - px, y - py
            vv = vx * vx + vy * vy
            if vv < 1:
                continue
            t = clamp(-(rx * vx + ry * vy) / vv, 0.0, 0.65)
            closest = math.hypot(rx + vx * t, ry + vy * t)
            z_closest = pz + vz * t - (11.0 * t * t if projectile["kind"] == "mortar" else 0.0)
            if closest < 7.0 and abs(z_closest - (z + 4.5)) < 9.0:
                # Move perpendicular to the shot path; bias away from the projectile origin.
                side = 1.0 if (vx * (y - py) - vy * (x - px)) >= 0 else -1.0
                px_d, py_d = unit(-vy * side, vx * side)
                move_x += 1.7 * px_d
                move_y += 1.7 * py_d
                danger = True

        # A laser telegraph is a strong dodge cue even when its shooter is not our target.
        for enemy in enemies:
            if enemy["kind"] != "mech" or not enemy.get("charging"):
                continue
            yaw = enemy.get("aim", [0, 0])[0]
            bearing_to_us = math.atan2(y - enemy["pos"][1], x - enemy["pos"][0])
            if abs(angle_delta(bearing_to_us, yaw)) < 0.30 and distance2(enemy["pos"], (x, y)) < 280:
                side = 1.0 if angle_delta(bearing_to_us, yaw) >= 0 else -1.0
                move_x += -math.sin(yaw) * side * 1.8
                move_y += math.cos(yaw) * side * 1.8
                danger = True

        move_x, move_y = unit(move_x, move_y)
        act["move"] = [move_x, move_y]
        energy = me.get("energy", 0)
        urgent_zone = not me.get("in_zone", False)
        boost = energy > 18 and (urgent_zone or (danger and energy > 30))
        act["boost"] = boost
        act["jump"] = bool(me.get("grounded") and danger and obs["tick"] % 4 == 0)

        if aim_target is not None:
            # Select a primary weapon aim, prioritizing an available counter weapon.
            slot = next((i for i, w in enumerate(weapons) if w and w["kind"] == "lightning"
                         and target_dist < 45), None)
            if slot is None:
                slot = next((i for i, w in enumerate(weapons) if w and w["kind"] == "laser"
                             and target_dist < 260), None)
            if slot is None:
                slot = 0 if weapons and weapons[0] else next((i for i, w in enumerate(weapons) if w), None)
            primary_kind = weapons[slot]["kind"] if slot is not None else "gun"
            charge = weapons[slot].get("charge", 0) if slot is not None else 0
            desired = self._aim_for(aim_target, me, primary_kind, charge)
            act["aim"] = [desired[0], desired[1]]
        elif attacker_bearings:
            act["aim"] = [attacker_bearings[-1], 0.0]
        else:
            # Look toward the zone route to scan the useful forward vision cone.
            act["aim"] = [math.atan2(gy, gx) if gx or gy else me["aim"][0], 0.0]

        desired_aim = act["aim"]
        yaw_error = abs(angle_delta(desired_aim[0], me["aim"][0]))
        pitch_error = abs(desired_aim[1] - me["aim"][1])
        aim_ready = yaw_error < 0.14 and pitch_error < 0.12
        for i, weapon in enumerate(weapons[:2]):
            if not weapon or target is None or i != slot:
                continue
            kind = weapon["kind"]
            d = math.dist(target["pos"], me["pos"])
            stats = weapon.get("stats", self.weapon_cfg.get(kind, {}))
            cooldown = weapon.get("cooldown", 0)
            in_range = d <= stats.get("range", 0)
            if kind == "gun":
                # Preserve ammunition at long range; lead is still applied for any shot.
                in_range = d <= min(stats.get("range", 230), 155 if target["kind"] == "mech" else 65)
                should_reload = (weapon.get("ammo", 12) <= 2 or
                                 (weapon.get("ammo", 12) <= 4 and not in_range))
                if should_reload and weapon.get("reload", 0) <= 0:
                    act["reload"] = True
                else:
                    act["fire"][i] = bool(in_range and aim_ready and cooldown <= 0.12
                                           and weapon.get("reload", 0) <= 0)
            elif kind == "lightning":
                # Lightning auto-targets the nearest object, so don't waste it through a nearer drone/crate.
                nearest_npc = min((math.dist(e["pos"], me["pos"]) for e in enemies
                                   if e["kind"] == "npc"), default=float("inf"))
                act["fire"][i] = bool(d <= min(45, stats.get("range", 45)) and aim_ready
                                       and cooldown <= 0.12 and energy > 8
                                       and (target["kind"] == "npc" or d <= nearest_npc + 2))
            elif kind == "laser":
                charge_s = stats.get("charge", 0.75)
                current_charge = weapon.get("charge", 0)
                if current_charge > 0:
                    # Release after a moderate charge to reduce the dodge/slow-movement window.
                    act["fire"][i] = current_charge < min(0.45, charge_s) and in_range
                else:
                    act["fire"][i] = bool(in_range and aim_ready and cooldown <= 0.12)
            elif kind == "mortar":
                act["fire"][i] = bool(18 < d < min(190, stats.get("range", 235)) and aim_ready
                                       and cooldown <= 0.12)

        # Take nearby weapons only when the empty slot or matchup makes the swap worthwhile.
        candidates = []
        for pickup in obs.get("pickups", []):
            dxy = distance2(pickup["pos"], (x, y))
            dz = abs(pickup["pos"][2] - z)
            if dxy > self.pickup_radius or dz > 4:
                continue
            kind = pickup["kind"]
            if kind in held:
                continue
            if any(w is None for w in weapons):
                priority = {"laser": 3, "lightning": 2, "mortar": 1}.get(kind, 0)
                nearby_laser = any(e["kind"] == "mech" and has_weapon(e, "laser")
                                   and distance2(e["pos"], (x, y)) < 180 for e in enemies)
                if kind == "lightning" and nearby_laser:
                    priority += 4
                if kind == "mortar" and nearby_laser:
                    priority -= 3
                candidates.append((priority, pickup["id"]))
        if candidates:
            act["take"] = max(candidates)[1]

        # Status-only debug output stays small and within the protocol caps.
        mf.draw.label(f"HP {me['hp']:.0f} | alive {obs['alive']} | target {target['id'] if target else '-'}")
        mf.draw.point([goal[0], goal[1], z], "#40c0ff", 5)
        return act


mf.run(Bot)
