# Screenshots

Each lesson shows `<shot>.png` from this folder when the lesson has a `"shot"` value in `lessons.json`. A lesson
with no `shot` simply shows no screenshot. The tests fail if a lesson names a file that does not exist.

## Included

Frames from the Atlas, BCS and eAtlas walkthrough recordings, shown as recorded:

| File | Lesson |
|---|---|
| `startup-navigation.png` | Install, startup & navigation |
| `license-activation.png` | Sign-in vs. license vs. authorization |
| `atlas-login.png` | Sign-in vs. license vs. authorization |
| `product-details.png` | The technician workflow, step by step |
| `bulletins.png` | Manuals, bulletins & downloads |
| `operations.png` | Detectors & service operations (plugins) |
| `eatlas-assign.png` | Assigning cases |
| `licenses.png` | Two kinds of license |
| `constants.png` | Instrument constants pipeline |

## Lessons without a screenshot

Warranty and support, Repair Assistant, offline and sync, recovery and environments, architecture, the daily
schedule, Global Service, the documentation capstone and the five source-code lessons. They are not clearly
shown in the recordings.

## Add or replace a screenshot

1. Save a PNG here, for example `my-shot.png`.
2. Set that lesson's `"shot": "my-shot"` in `lessons.json` (omit the extension).
3. Run `python -m unittest discover -s tests`, then `setup.bat` again to copy it into the installed guide.
