# Castlevania: Lords of Shadow Archipelago
An Archipelago randomizer for Castlevania: Lords of Shadow - Ultimate Edition on Steam.
The mod randomizes available levels, gear, relics and gem upgrades.
The goal is to beat a set number of levels to unlock the Final Fight and beat the boss.

### Current location checks
- Beating a level
- Fallen brotherhood knights who have gems
- Brotherhood Arks

### Current items
- Level access
- Relics and magic
- Life, light and shadow gems are given two at a time
- Combat cross upgrades
- Subweapons and their capacity upgrades
- Consumable refill
- Experience points

### Download
[Download can be found here.](https://github.com/Haywire32/Castlevania-Lords-of-Shadow-Archipelago-randomizer/releases/tag/v0.5.0)

### How to install
Install Archipelago version 0.6.7

Download the files. Install los.apworld by double-clicking it

Fill out the yaml and make a seed like usual in Archipelago.

Drop "dinput8.dll" into \Steam\steamapps\common\CastlevaniaLoS\bin

On Steam, enter properties for the game and disable "Steam Cloud" under General.

Remove your save file "Castlevania.profile" from \Steam\userdata\User-ID\234080\remote. 
Back it up first if you want to keep it.

Open Archipelago Launcher - run "Lords of Shadow Client"

Connect to the Archipelago server and enter slot name, then launch the game normally on Steam.

### Current logic
My current logic can be found in this [sheet.](https://docs.google.com/spreadsheets/d/1RQx8A5rJAoTpEiopHlmUMY5vjVQFeupraoh7jmgP3mI/edit?usp=sharing)

It is a work in progress and probably has mistakes. It can be useful for completing seeds, though.

I'll happily accept feedback on it.

### Feedback or other questions
I'd love feedback on design choices and bugs in the [Castlevania lords of shadow channel](https://discord.com/channels/731205301247803413/1420192076259393567) in the [Archipelago discord](https://discord.gg/8Z65BR2)

The current version is still unstable and most likely has bugs.

### Future plans and ideas
Trials are not yet implemented as checks.

DLC maps are currently disabled because logic hasn't been mapped.

Traps - poison, magic drain

DeathLink

More yaml options

Ingame tracker that counts completed levels

Ingame messages of sent/recieved items

Possible map indicators to show in-logic progression

Brotherhood knight scrolls giving hints

### Disclaimer
AI assistance was used for reverse engineering and hook implementation. Item and logic mapping, in-game testing, verification, and design decisions were done manually by me.
