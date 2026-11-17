# Screenshots

Each lesson shows `<shot>.png` from this folder when the file exists. If a file is missing, the lesson simply shows no screenshot.
The `shot` name of every lesson is in `lessons.json`.

Included (frames from the Atlas, BCS and eAtlas walkthrough recordings, shown as recorded):
`atlas-overview`, `startup-navigation`, `license-activation`, `product-details`, `service-case`, `bulletins`,
`operations`, `bcs`, `eatlas-dashboard`, `eatlas-assign`, `eatlas-content`, `licenses`, `constants`.

Still without a screenshot (not clearly shown in the recordings): `ai-chat`, `offline`, `dwcr`, `recovery`, `architecture`, `jobs`, `global`.
To replace or add one, save a PNG here with that name and run setup.bat again.

To show a screenshot for a lesson, save `<name>.png` here and set that lesson's `"shot": "<name>"` in `lessons.json`
(the tests fail if a lesson names a file that does not exist).
