# Data

`data/ul_flair_lists.db` (SQLite). One row per LighterPack list, category and item.

## Tables

**`lists`**: `id`, `cohort`, `total_g`, `base_weight_g`, `ul_tier`
- `cohort`: `thread` (found by crawling r/Ultralight comment threads) or `archive` (found through a public Reddit archive, flairs from 2023 on).
- `base_weight_g`: total weight minus items flagged worn or consumable.
- `ul_tier`: SUL up to 2,270 g (5 lb), UL up to 4,536 g (10 lb), LW up to 9,072 g (20 lb), otherwise Traditional.

**`categories`**: `id`, `list_id`, `name`, `total_g`. `name` is the list owner's own category name.

**`items`**: `id`, `list_id`, `category_id`, `name`, `description`, `weight_g` (one unit), `quantity`, `total_g` (as LighterPack reports it, already including quantity), `worn`, `consumable`, `core_role`, `core_role_via`.
- `core_role`: `pack`, `shelter`, `quilt` or `pad` where the classifier identified the item, otherwise NULL. More than one item per role is possible (a tent and its inner, a top quilt and an underquilt); the analysis uses the heaviest.
- `core_role_via`: how the role was decided: `text` (the item name or description), `category` (the owner's category name), `brand` (a brand that makes several kinds of gear, used only to fill a missing role), `eliminated` (the only unidentified heavy item in a Big 3/4/5 category), `underquilt` (a hammock list's underquilt standing in as the pad).

## Anonymization

Removed: Reddit usernames, LighterPack URLs and list names, post ids/titles/authors, per-item product URLs. List and item ids are assigned fresh (lists by a seeded shuffle), so ids carry no crawl order.

Scrubbed from the free-text fields (item names, descriptions, category names): email addresses, URLs, @handles, phone numbers, any `u/name` mention, and any known username of a list owner (distinctive names only, matched as whole tokens). Removed fragments appear as `[removed]`. HTML entities in the scraped text were decoded.

Free text can still carry things the scrubbers cannot recognize. If you find a row that identifies someone, open an issue and it will be removed.

## What the weights mean

LighterPack's per-item value already includes the quantity; `total_g` is that value and `weight_g` is `total_g / quantity`. For every list the item `total_g` values sum to the list total LighterPack reports (checked on export).
