# 1024 editorial cards (01-04)

Source of the four-card set. Re-render from the repository root:

```powershell
python .runtime/easel/skills/shared/scripts/render_card.py ^
  --html projects/x-superplay-1024/motion/cards/cards-1024.html ^
  --all ".card" --out-dir outputs/editorial-1024 --prefix card ^
  --width 1080 --height 1920 --scale 2
```

Then copy `card_1..4` to `outputs/editorial-1024/by-placement/shot_03,04,00,05.png`.
The card numbers follow the playback order: 01 TURN, 02 HOOK, 03 PROBLEM, 04 ENDING.
