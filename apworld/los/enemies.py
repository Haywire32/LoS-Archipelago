"""Versioned minor-enemy pool; identifiers are retail character controllers."""
import hashlib
import json
LAYOUT_VERSION = 7
GROUP_WAVES = 260  # Thirteen complete 20-spawn difficulty bags.
IMPORTED_TYPES_PER_LEVEL = 4
# Frozen order is part of the seed layout. Change LAYOUT_VERSION if changed.
ENEMY_POOL = tuple(sorted((
    'AnimArmour', 'FloatingHeads', 'Ghoul', 'GhoulDLC', 'Goblin',
    'Gremlin', 'LycanthropeGreater', 'LycanthropeLesser', 'Mandrake',
    'Reaper', 'Scarecrow', 'SkeletonFlame', 'SkeletonWarrior',
    'SwordMaster', 'TrollSmall', 'VampireWarrior', 'WitchChild',
    'Zombie',
)))
EXCLUDED = {
    'Naiad': 'user exclusion', 'Chupacabra': 'user exclusion',
    'SwampThing': 'invulnerable swamp/Naiad actor',
    'CreepingCorpse': 'headless burrower / user exclusion',
    'CreepingCoffin': 'spawns excluded headless burrowers',
    'RagDoll': 'Deadly Toy requires a level-specific grab finisher and can revive',
    'SpiderGiant': 'mount', 'WargGreat': 'mount', 'Warthog': 'mount',
    'TrollBig': 'mount', 'TrollBigSwamp': 'boss/mount',
    'BlackKnight': 'boss', 'Butcher': 'boss', 'Darklord1': 'boss',
    'Darklord1L': 'boss', 'Darklord2': 'boss', 'Darklord2V': 'boss',
    'Dracolich': 'boss', 'EliteVampA': 'boss', 'EliteVampB': 'boss',
    'GraveDigger': 'boss', 'IceElemental': 'boss', 'Laura': 'boss',
    'Legion': 'boss', 'MechanicalM': 'boss', 'Necromancer': 'boss',
    'Ogre': 'boss', 'Satan': 'boss', 'SilverWarrior': 'boss',
    'StoneIdol': 'boss', 'Witch': 'boss',
}
# Floating Heads are ordinary enemies, but their controller is only authored in
# the Bones Forest and caused a hard engine exit when imported into Agharta.
# Keep them randomized as sources/targets in their native map while preventing
# this specialized controller from being loaded cross-level.
NATIVE_ONLY_TARGETS = frozenset({'FloatingHeads'})
# Preserve crash-prone maps and Fire Cemetery's authored weak-enemy horde.
RETAIL_ONLY_LEVELS = frozenset({'11_8_dracolich', '5_2_isolated_village',
                              '10_3_cementery', '3_0_the_gauntlet'})
HARD_ENEMIES = frozenset({'Scarecrow', 'SkeletonWarrior', 'LycanthropeGreater', 'AnimArmour'})
# Refectory's meat/cauldron puzzle searches for the literal Ghoul controller.
PRESERVED_TYPES = {'6_5_refectory': frozenset({'Ghoul'})}
# The cauldron searches the entire map for living ghouls. Adding one behind a
# later locked door would prevent taking meat now, so only authored ghouls remain.
TARGET_EXCLUSIONS = {'6_5_refectory': frozenset({'Ghoul', 'GhoulDLC'})}
PRESERVED_GROUPS = {'3_0_the_gauntlet': frozenset({'Enemy_Group_Fairy'}),
                    '6_5_refectory': frozenset({'Enemy_Group'})}
# Captured retail MapEnemiesGroup.List membership. Groups are assigned AFTER
# static actor creation, so guarding only the generator is insufficient.
PRESERVED_ACTORS = {'3_0_the_gauntlet': frozenset({'Enemy313','Enemy311','Enemy315'}),
                    '6_5_refectory': frozenset({'Enemy821','Enemy819','Enemy817'})}
# Only the whitelist is eligible: scenery animals, friendly NPCs, detached body
# parts and unknown controllers are preserved by default.
assert not set(ENEMY_POOL) & EXCLUDED.keys()

# Names displayed by the English Travel Book/bestiary. GhoulDLC is the DLC
# variant of the same bestiary enemy; Floating Heads are Spawns of Leviathan.
ENEMY_DISPLAY_NAMES = {
    'AnimArmour': 'Animated Armor',
    'FloatingHeads': 'Spawns of Leviathan',
    'Ghoul': 'Ghoul',
    'GhoulDLC': 'Ghoul (DLC variant)',
    'Goblin': 'Goblin',
    'Gremlin': 'Gremlin',
    'LycanthropeGreater': 'Greater Lycanthrope',
    'LycanthropeLesser': 'Lesser Lycanthrope',
    'Mandrake': 'Mandragora',
    'Reaper': 'Reaper',
    'Scarecrow': 'Scarecrow',
    'SkeletonFlame': 'Flaming Skeleton Warrior',
    'SkeletonWarrior': 'Skeleton Warrior',
    'SwordMaster': 'Swordmaster',
    'TrollSmall': 'Small Troll',
    'VampireWarrior': 'Vampire Warrior',
    'WitchChild': 'Witch Child',
    'Zombie': 'Zombie',
}
assert set(ENEMY_DISPLAY_NAMES) == set(ENEMY_POOL)

def _seed_value(seed: str, level: str, spawn: str) -> int:
    """Matches float-safe retail Lua arithmetic; never truncate a long seed."""
    level = level.removeprefix('level.')
    identity = f'enemy-layout-{LAYOUT_VERSION}|{len(seed.encode("utf-8"))}:{seed}|{len(level.encode("utf-8"))}:{level}|{spawn}'
    value = 0
    for byte in identity.encode('utf-8'):
        value = (value * 31 + byte) % 65521
    return value


def selection(seed: str, level: str, spawn: str, pool=ENEMY_POOL) -> str:
    return pool[_seed_value(seed, level, spawn) % len(pool)]


def _balanced_pick(seed, level, key, pool, hard):
    choices=tuple(enemy for enemy in pool if (enemy in HARD_ENEMIES)==hard)
    choices=choices or pool
    return choices[_balance_hash(seed,level,key) % len(choices)]


def _balance_hash(seed, level, key):
    # Plans are precomputed in Python. A strong hash avoids clustering adjacent
    # spawn names/waves into long runs of the same difficulty class.
    encoded=json.dumps([seed,level,key],ensure_ascii=False).encode('utf-8')
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], 'big')


def _group_stream(seed: str, level: str, group: str, pool=ENEMY_POOL) -> str:
    """Each member column has 17 easy / 3 hard spawns per 20 activations.

    Offset members through the same sequence: both one-at-a-time generators and
    multi-member waves get the intended weights without depending on timing.
    """
    sequence=[]
    for block in range(GROUP_WAVES//20):
        ranks=sorted(range(20),key=lambda i:(_balance_hash(seed,level,f'balance:{group}:{block}:{i}'),i))
        hard=set(ranks[:3])
        for i in range(20):
            sequence.append(_balanced_pick(seed,level,f'group:{group}:{block}:{i}',pool,i in hard))
    return ''.join(chr(65+ENEMY_POOL.index(sequence[(wave+member)%GROUP_WAVES]))
                   for wave in range(GROUP_WAVES) for member in range(len(pool)))


def build_plan(seed: str, catalog: dict) -> dict:
    """Materialize choices before level entry; generators cycle balanced bags."""
    if not isinstance(seed, str) or not seed:
        raise ValueError('Missing enemy seed identity')
    levels = {}
    for level, entries in sorted(catalog.items()):
        sources=entries['static']
        protected=set(entries.get('protected',()))
        if level in RETAIL_ONLY_LEVELS:
            levels[level] = {'passthrough': True, 'roster': [], 'static': {},
                             'groups': {}, 'preserved': dict(sources)}
            continue
        eligible=lambda name: name not in PRESERVED_ACTORS.get(level,()) and (not isinstance(sources,dict) or (sources[name] in ENEMY_POOL
                       and sources[name] not in PRESERVED_TYPES.get(level,())
                       and sources[name]!='Goblin' and 'static:'+name not in protected))
        # Loading every foreign controller in every map exhausts the game's
        # pause-book resource path after combat. Keep all authored/native minor
        # types and add four seed-selected imports. Across levels and seeds the
        # full pool remains possible, without one map carrying every type.
        target_exclusions=TARGET_EXCLUSIONS.get(level,())
        native=sorted({controller for controller in sources.values()
                       if controller in ENEMY_POOL and controller not in target_exclusions}) if isinstance(sources,dict) else []
        imports=sorted((enemy for enemy in ENEMY_POOL
                        if enemy not in native and enemy not in NATIVE_ONLY_TARGETS and enemy not in target_exclusions),
                       key=lambda enemy: (_seed_value(seed,level,'roster:'+enemy),enemy))
        # Keep the existing four-import budget but ensure both difficulty classes
        # are represented, even when the native roster contains only hard actors.
        chosen=[]
        for hard in (False,True):
            candidates=[e for e in imports if (e in HARD_ENEMIES)==hard]
            chosen.extend(candidates[:2])
        chosen.extend(e for e in imports if e not in chosen)
        roster=tuple(native+chosen[:IMPORTED_TYPES_PER_LEVEL])
        names=sorted(name for name in sources if eligible(name))
        ranked=sorted(names,key=lambda n:(_balance_hash(seed,level,'balance:static:'+n),n))
        hard_names=set(ranked[:(len(names)*15+50)//100])
        levels[level] = {
            'balance_version': 2,
            'preserved_types': sorted(PRESERVED_TYPES.get(level,())),
            'preserved_groups': sorted(PRESERVED_GROUPS.get(level,())),
            'roster': list(roster),
            'static': {name: _balanced_pick(seed,level,'static:'+name,roster,name in hard_names) for name in names},
            'preserved': {name:sources[name] for name in sorted(sources) if not eligible(name)},
            'groups': {name: _group_stream(seed, level, name,roster)
                       for name in sorted(entries['groups']) if name not in PRESERVED_GROUPS.get(level,())},
        }
    return {'version': LAYOUT_VERSION, 'seed': seed, 'pool': list(ENEMY_POOL), 'levels': levels}
