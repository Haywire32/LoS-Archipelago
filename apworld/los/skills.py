"""Retail positive-price whitelist. No free, mount, story or automatic moves.

Stable release IDs are assigned in explicit catalog order. Do not reorder SKILLS.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    action: str
    combo: str
    price: int
    conditions: tuple[str, ...] = ()


SKILLS = (
    Skill('LightFlash', 'BlockSyncBlind', 1500, ('_light', '_syncBlock')),
    Skill('DaggerWave', 'MultipleDaggers', 400),
    Skill('FlapWindWave', 'WhipBlockComboUppercutJ', 3500, ('_gauntlet', '_wings')),
    Skill('SomersaultStrike', 'WhipBlockSommerJumpDDD', 3000, ('_boots', '_gauntlet')),
    Skill('ShadowFlames', 'WhipComboADDrh', 3000, ('_dark',)),
    Skill('HolyCross', 'WhipComboADLMh', 6000, ('_light',)),
    Skill('FlapWhirlwind', 'WhipComboAJJ', 3500, ('_wings',)),
    Skill('ComboChainBarrier', 'WhipComboAh', 800),
    Skill('ComboChainBarrier_Upgrade', 'WhipComboAhA', 1500, ('WhipComboAh',)),
    Skill('CircularChain', 'WhipComboDAA', 1000),
    Skill('ChainSaw', 'WhipComboDAD', 2000, ('WhipComboDAA',)),
    Skill('ExplodingQuake', 'WhipComboDADrh', 6000, ('WhipComboDAA', '_dark')),
    Skill('ErosiveChains', 'WhipComboDALMh', 3000, ('WhipComboDAA', '_light')),
    Skill('UpwardGuillotine', 'WhipComboDJJ', 3500, ('_wings',)),
    Skill('ComboDHeavy', 'WhipComboDrD', 800),
    Skill('ComboDHeavy_Upgrade', 'WhipComboDrDrDrD', 1500, ('WhipComboDrD',)),
    Skill('ComboDHeavy_Upgrade_Upgrade', 'WhipComboDrDrDrDrD', 2000, ('WhipComboDrDrDrD',)),
    Skill('DarkFocusMode', 'WhipComboDrMh', 25000, ('WhipComboADDrh', 'WhipComboDADrh', '_dark')),
    Skill('LightFocusMode', 'WhipComboLMh', 25000, ('WhipComboADLMh', 'WhipComboDALMh', '_light')),
    Skill('AvalanchePunch', 'WhipFallBlockComboAh', 2500, ('_gauntlet',)),
    Skill('LandslidePunch', 'WhipFallBlockComboDh', 2500, ('_gauntlet',)),
    Skill('SpinningChain', 'WhipFallComboAh', 150),
    Skill('GroundCutter', 'WhipFallComboDDhD', 2000),
    Skill('Guillotine', 'WhipFallComboDh', 25),
    Skill('Guillotine_Upgrade', 'WhipFallComboDhD', 1500, ('WhipFallComboDh',)),
    Skill('DownwardKick', 'WhipFallComboGripBig', 200, ('_grip',)),
    Skill('AirGrab', 'WhipFallComboGripSmall', 200, ('_grip',)),
    Skill('DownwardPunch', 'WhipFallComboGripSmallDown', 300, ('WhipFallComboGripSmall', '_grip')),
    Skill('SprintThrust', 'WhipSprintComboAD', 1000, ('_boots',)),
    Skill('FlameClaws', 'WhipSprintComboDDark', 3500, ('_boots', '_dark', '_gauntlet')),
    Skill('CounterstrikeA', 'WhipSyncComboAAA', 600, ('_syncBlock',)),
)

LABELS = {
    'LightFlash': 'Light Flash', 'DaggerWave': 'Dagger Wave',
    'FlapWindWave': 'Flapping Wind', 'SomersaultStrike': 'Somersault Strike',
    'ShadowFlames': 'Shadow Flames', 'HolyCross': 'Holy Cross',
    'FlapWhirlwind': 'Flapping Whirlwind', 'ComboChainBarrier': 'Chain Barrier',
    'ComboChainBarrier_Upgrade': 'Chain Barrier Upgrade', 'CircularChain': 'Circular Chain',
    'ChainSaw': 'Chain Saw', 'ExplodingQuake': 'Exploding Quake', 'ErosiveChains': 'Erosive Chains',
    'UpwardGuillotine': 'Upward Guillotine', 'ComboDHeavy': 'Direct Heavy Combo',
    'ComboDHeavy_Upgrade': 'Direct Heavy Combo Upgrade',
    'ComboDHeavy_Upgrade_Upgrade': 'Direct Heavy Combo Upgrade 2',
    'DarkFocusMode': 'Ultimate Shadow', 'LightFocusMode': 'Ultimate Light',
    'AvalanchePunch': 'Avalanche Punch', 'LandslidePunch': 'Landslide Punch',
    'SpinningChain': 'Spinning Chain', 'GroundCutter': 'Ground Cutter',
    'Guillotine': 'Guillotine', 'Guillotine_Upgrade': 'Guillotine Upgrade',
    'DownwardKick': 'Downward Kick', 'AirGrab': 'Air Grab', 'DownwardPunch': 'Downward Punch',
    'SprintThrust': 'Sprint Thrust', 'FlameClaws': 'Flame Claws', 'CounterstrikeA': 'Counterstrike'
}
BY_ACTION = {s.action:s for s in SKILLS}
BY_COMBO = {s.combo:s for s in SKILLS}
SKILL_ITEM_NAMES = {s.action:'Skill: '+LABELS[s.action] for s in SKILLS}
SKILL_LOCATION_NAMES = {s.action:'Skill Purchase - '+LABELS[s.action] for s in SKILLS}
SKILL_ITEM_IDS = {s.action:20130200+i for i,s in enumerate(SKILLS)}
SKILL_LOCATION_IDS = {s.action:20134000+i for i,s in enumerate(SKILLS)}
RELICS = {'_light':'Light Magic','_dark':'Shadow Magic','_gauntlet':'Dark Gauntlet',
          '_wings':'Seraph Shoulders','_boots':'Cyclone Boots','_grip':'Hook Tip'}
def purchase_relics(action):
    """A completed predecessor purchase requires its relic gates, never its item.

    With renewable XP, an accessible purchase chain can be bought in order.
    Recursing the chain avoids AP event items and handles excluded locations.
    """
    required=set()
    for condition in BY_ACTION[action].conditions:
        if condition in RELICS:
            required.add(RELICS[condition])
        elif condition in BY_COMBO:
            required.update(purchase_relics(BY_COMBO[condition].action))
        elif condition != '_syncBlock':
            raise ValueError('Unaudited skill condition: '+condition)
    return frozenset(required)
