# Future Intelligence editorial cards (01-06)

Source of the six-card set. Re-render from the repository root:

```powershell
python .runtime/easel/skills/shared/scripts/render_card.py ^
  --html projects/x-superplay-future-intelligence/motion/cards/cards.html ^
  --all ".card" --out-dir outputs/editorial --prefix card ^
  --width 1080 --height 1920 --scale 2
```

Then copy `card_1..6` to `outputs/editorial/by-placement/shot_00..05.png`.
Playback order: 01 HOOK, 02 SETUP, 03 EVIDENCE, 04 TURN, 05 PROBLEM, 06 ENDING.
