# Methods

## Users and lists

Users were found two ways: a crawl of r/Ultralight comment threads (`thread` cohort), and a public Reddit archive filtered on author-flair text containing `lighterpack.com` (`archive` cohort, flairs from 2023 on). Lists are the LighterPack pages those flairs link to. Only flair strings and the list pages themselves were collected. The collection scripts are not part of this repository.

## Base weight

`base_weight_g = sum(total_g of items where worn = 0 and consumable = 0)`, using the owner's flags.

## Finding the Big 4: `ulgear/classifier.py`

Item-only keyword rules fail on terse names ("Bag", "Pad - NeoAir", "DD40"), so classification is list-aware. For each list, roles `pack`, `shelter`, `quilt` (quilt or sleeping bag, including underquilts) and `pad` are assigned in stages; each assignment records how it was made (`core_role_via`).

1. **Text.** Name first. A type word in the name (`quilt`, `tarp`, `sleeping pad`, `backpack`) beats a model name (`Enigma`, `X-Mid`, `NeoAir`), which beats a bare `Bag`. The description contributes model names only, unless the item has no name or the description is itself just a type word ("Sleeping Pad"). A veto list removes accessories and other gear by the *head noun* of the name ("pack liner", "tent stakes", "rain jacket"; but "Vest Pack" and "Top Quilt" survive), and a weight window rejects implausible matches.
2. **Category.** If a role is still missing, the heaviest unidentified item in a category the owner named for that role ("Shelter", "Pack").
3. **Brand.** A brand that makes several kinds of gear (MLD, Gossamer Gear, Zpacks) can fill a still-missing role, but never overrides text.
4. **Elimination.** Inside a category named "Big 3/4/5", if exactly one role is missing and exactly one unidentified heavy item is left, it takes the role.
5. **Hammocks.** An underquilt or bottom quilt stands in for the pad when a second quilt exists.

Lists that genuinely lack a role (a hut-to-hut list, a 2-item list, a quilted hammock with no separate pad) are left without one. `tests/verified_core_gear.csv` holds the hand-checked pick for every list; `tests/test_classifier.py` fails if a change moves any of them.

## Item slots: `analysis/report.py`

Everything else is matched as a *slot*, a function such as "water filter" or "headlamp", by regex over normalized item name + description (about 55 slots, each with an optional exclusion pattern and a list of models). A slot counts once per list; its weight is the heaviest matching non-consumable item in that list, one unit. Items with no weight entered count toward whether a slot is carried but not toward its weight.

For slot *s*, with *c<sub>s</sub>* the set of lists carrying it and *N* the number of lists:

- prevalence = |*c<sub>s</sub>*| / *N*
- slot weight = median over *c<sub>s</sub>* of the matched item's weight
- the **modal kit** includes *s* iff prevalence >= 0.5, using the most common named model's median weight when that model appears in at least 3 lists.

## Known limits

Brand shares are floors (generic names). Slot matching reads names and can miss or mislabel unusual items; the Big 4 were hand-checked, the other items were not. The cohorts agree on base weight (`analysis/cohort_check.py`), which checks the collection method and nothing about selection into the sample.
