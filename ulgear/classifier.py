#!/usr/bin/env python3
"""
List-aware classifier for the four core roles of a backpacking kit:

    pack | shelter | quilt (quilt or sleeping bag, incl. underquilts) | pad (sleeping pad)

Item-only keyword rules (build_db.item_classify) fail on terse names like "Bag",
"Pad - NeoAir", "DD40".  This classifier uses, in order:

  1. text/model rules   - words and a brand/model vocabulary over name + description
  2. category context   - the user's own category name ("Shelter", "Sleep", "Pack", "Big 4")
  3. elimination        - if a "big items" category has exactly the unidentified heavy items
                          needed to fill the missing roles, assign them by weight order

Every role decision records WHY (`role_via`: text | category | eliminated) so uncertain
assignments can be audited.

Usage:  python -m ulgear.classifier [--cohort thread|archive|all] [--misses] [--show LIST_ID]
"""
import html
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "data" / "ul_flair_lists.db"
ROLES = ("pack", "shelter", "quilt", "pad")

# ── vocabulary ────────────────────────────────────────────────────────────────
# Name words that mean "this item is something else" (checked on the item NAME only).
NAME_VETO = re.compile(
    r"jacket|\bcoat\b|pants|shorts|\bshirt|\btops?\b|bottoms?|hood(ie|y)|sweater|fleece|\bvest\b|puffy|"
    r"parka|\bsocks?\b|gloves?|mitts?|\bhat\b|\bcap\b|bea?e?nie|beany|\bbuff\b|gaiters?|shoes?|boots?|sandals?|"
    r"underwear|\bbra\b|base ?layer|mid-?layer|\blayers?\b|clothing|tights|leggings|headlamp|"
    r"flashlight|\blight\b|\blamp\b|phone|camera|tripod|charger|battery|power ?bank|cable|\bwatch\b|\bgps\b|"
    r"inreach|stove|\bpot\b|\bmug\b|\bcup\b|spork|spoon|\bfork\b|lighter|\bfuel\b|\bfood\b|\bbear\b|"
    r"canister|filtration|purif|filter|\bwater\b|bottle|bladder|sawyer|\bsoap|toothbrush|toothpaste|sunscreen|"
    r"bug ?spray|first aid|knife|multi-?tool|sunglasses|glasses|trekking|umbrella|\bmap\b|compass|"
    r"journal|\bbook\b|whistle|mirror|trowel|toilet|\btp\b|wipes|\btape\b|towel|bandana|pillow|"
    r"\bchair\b|\bbelt\b|cann?ister|\bpoles?\b|\bst(?:ak|ka)es?\b|\bpegs?\b|guy ?lines?|\bcord\b|\bsit\b|seat|\bliner\b|\bcover\b|\bpatch\b|"
    r"repair|\bpump\b|\bvalve|stuff ?sack|\bsack\b|\bclip\b|buckle|\bstrap|\bpouch|\bwallet|\bdry ?bag|"
    r"ziploc|trash|\bcable|\bcharg|\bwind ?shirt|rain ?(shell|gear|skirt)|\bshell\b|"
    r"ground ?sheets?|piquets?|footprint|polycro|tyvek|whoopie|suspension|poncho|clothes|\bcloth|pajamas?|\bpjs?\b|"
    r"^(sub)?total\b|\bdaisy|\bspider\b|ridge ?line|carabiner|\bbiner|\bstraps\b|tree ?huggers?|"
    r"\bbivy ?(sack )?cover|\blaundry")

# type words found in the NAME: strong evidence
N_PACK = re.compile(r"sac ?[àa�] ?dos|\bmochila|ryggs[äa]ck|rygs[æa]k|\breppu|\brugzak|\bbackpack|\brucksack|\bpack\b|\bfast ?pack|\bday ?pack|\bpack ?\d")
N_QUILT = re.compile(r"schlafsack|sac de couchage|saco de dormir|sovs[äa]ck|sovepose|makuupussi|slaapzak|"
                     r"sacco a pelo|\bquilts?\b|sleep(ing)? ?bags?|\bunderquilt|\bover ?quilt|top ?quilt|\btq\b|\buq\b|"
                     r"\b(down|synthetic|false bottom|over|summer|winter|mummy)\b.*\bbag\b")
N_BARE_BAG = re.compile(r"^bag\b|^sb\b")      # a bare "Bag": ambiguous (pack or sleeping bag)
N_PAD = re.compile(r"isomatte|matelas|\bmatras\b|colchoneta|liggunderlag|makuualusta|slaapmat|karrimat|"
                   r"sleep(ing)? ?(pad|mat)|\bpads?\b|\bmats?\b|mattress|inflatable|air ?pad|\bccf\b|"
                   r"foam|^sleep ?system")
N_SHELTER = re.compile(r"\bzelt\b|au[ßs�]+enzelt|\btente\b|\btienda\b|\btelt\b|\bt[äa]lt\b|\bteltta\b|\btents?\b|\btarps?\b|\bbivy\b|\bbivvy\b|hammock(?! gear)|\bshelter|pyramid|\bmid\b(?! ?layer)|"
                       r"\bfly\b")
# short descriptions that are just a type word ("Sleeping Pad", "Internal Frame Pack", "3-Season Tent")
DESC_TYPE = {
    "pad": re.compile(r"^(inflatable |foam |torso |insulated |ccf )?(sleeping|sleep)? ?(pad|mat|mattress)\W*$"),
    "quilt": re.compile(r"^((summer|winter|sleeping|down|top|3-season|synthetic)\s+)*(quilt|bag)\W*$"),
    "pack": re.compile(r"^(internal |external )?(frame |frameless )?(back)?pack\W*$|^backpack\W*$|^rucksack\W*$"),
    "shelter": re.compile(r"^(\d ?(p|person|season|-season)\W*)*(tent|tarp|shelter|bivy)\W*$|^3-season tent\W*$"),
}

# model vocabulary found in NAME or DESCRIPTION: strong evidence
M_QUILT = re.compile(
    r"enigma|revelation|accomplice|\bconvert\b|\bugq\b|underground quilts?|katabatic|palisade|\balsek|"
    r"chisos|burrow|phoenix|\becon\b|incubator|premiere|serratus|zenbivy|sastrugi|bandit|\bflex ?\d|"
    r"nunatak(?! ?bears? ?ears)|\bsulo\b|subakigear|\borka\b|\bskaha|\barc ?(ul|\d)|\bsl ?sul|hummingbird|\bvireo\b|megalite|ultralite|summerlite|"
    r"alpinlite|versalite|flylite|\bnewt\b|timmermade|\bmoondance|featherstone|cumulus|"
    r"nemo (disco|riff|forte|tempo|salsa|kayu|coda)|sea to summit (spark|ember|trek|altitude|quest)|"
    r"zpacks.*(classic|solitude|ghost|sleeping|bag)|montbell.*(spiral|seamless|down hugger)|"
    r"marmot (hydrogen|helium|trestles)|big agnes.*(anvil|lost ranger|torchlight|fairview|sidewinder|zirkel)|"
    r"\bloco libre|\boperator\b|\bwilderness logics|\blsoh|little shop of hammocks|"
    r"\btoaster|\btorrid\b.*(quilt|10d)|\bjrb\b|jacks ?'?r'? better|\bpeak ?\d+ quilt|\bbonfire\b|"
    r"hammock gear|\bundercling ?mike|\bunderclinger|\boutdoor vitals|\bluxe quilt|\bgolite.*quilt|"
    r"\baegismax|\bnaturehike.*(bag|quilt)|\bwestern mountaineering|\bfeathered friends|"
    r"\bsnugpak|\bkelty.*(bag|cosmic)|\bmhw\b.*bag|\bnorth face.*(bag|aleutian)|\brei.*(magma|sub-?kilo|co-?op bag)|"
    r"\bspark ?(sp|spi|spii)|\bdisco\b|\b[0-5]0 ?(°|º|\*|deg\w*)(?!\s*(shirt|jacket))|\b[0-5]0f\b|\b\d{2} ?f ?(quilt|bag)")
M_PAD = re.compile(
    r"x ?-?lite|x ?-?therm|xlite|xtherm|neo ?air|\bnxt\b|z ?-?lite|x ?-?air ?-?li(te|ght)|ridge ?rest|\btensor\b|uberlite|"
    r"\bklymit(?! motion)|megamat|thinlight|prolite|trail ?(pro|lite)|\bswitchback|\bnemo.*(pad|tensor|astro|roam)|"
    r"insulated.*(air|pad)|\bether\b|\bcomfort (plus|light)|\bsynmat|\bdownmat|\bairmat|\binertia|"
    r"\bstatic ?v|\bsol\b.*(pad|mattress)|\brest\b.*\bpad|\bexped.*(ultra|mat|synmat|downmat)|"
    r"\bultra ?3r|\brapide|\bevazote|\bz ?rest|\bflextherm|\bnightlight|\bnight ?light")
M_PACK = re.compile(
    r"arc ?(haul|blast|zip)|\bnero\b|zpacks.*(arc|nero|zero)|hyperlite.*(pack|windrider|southwest|junction|porter)|"
    r"windrider|southwest ?\d|junction ?\d|\bporter\b|mariposa|gorilla|\bkumo\b|silverback|\bg4\b|\btalon\b|"
    r"\blevity|\bexos\b|\batmos|kestrel|\bkyte\b|\baura\b|\bula ?(circuit|catalyst|ohm|cdt|equipment)|"
    r"\bcircuit\b|\bcatalyst\b|\bohm\b|palante|atom ?packs?|granite gear|\bcrown ?2?\b|\bvirga\b|\bnimbus\b|"
    r"\bkakwa\b|\bbears? ?ears\b|hybride|hyberg|(running|hydration|trail|race) vest|\bflash( air)? ?\d{2}\b|\b\d{2}\+\d{1,2}\b|\bklymit motion|\bks[- ]?\d{1,2}\b|zimmerbuilt|zimmbag|seek outside|\bprophet\b|\bmld.*(burn|exodus|prophet)|"
    r"\bburn\b|\bexodus\b|\bflo\b|pa'?lante|\bmurmur|\baircontact|\bsirrus|\bstratos\b|\btrailblazer|\bdd ?(pro ?)?(pack ?)?\d{2}\b|\bg{1,2} ?4-?\d{2}\b|\bdandee|\bhmg\b.*\d{4}|\b\d{4} ?(southwest|windrider|junction)|"
    r"\bsalomon.*(bag|discovery)|\bskin pro|solamon|\bnashville|farpoint|\bkifaru|\bmystery ?ranch|"
    r"\bgregory|\bdeuter|\bosprey|\bjaylife|\bsensu|\bhelium ?v|bergans|\bmini ?2\b|zimm?[eb]*r?built|\bswd\b|"
    r"\bsuperior ?\d|\bnorthern ?ul|\bsundown|\bmontmolar|\bmuv\b|\bfastpack|\bvenom|\bmyog.*pack|"
    r"\blapg|\bmeng|\bgolite.*(jam|pack)|\b\d{2,3} ?(l|liter|litre)\b|\bbirch|\bkhaki")
M_SHELTER = re.compile(
    r"duplex|x ?-?mid|xmid|\bsolo ?mid|\bsolomid|\bduomid|lunar (solo|duo)|\bnotch\b|skyscape|trailstar|"
    r"rainbow|nighthawk|fly creek|copper spur|tiger wall|protrail|stratospire|\bmoment\b|"
    r"deschutes|ultamid|\bplex\b|solplex|altaplex|\blanshan|tarptent|big sky|\bthe one\b|gatewood|tensegrity|"
    r"dutchware|warbonnet|\beno\b|hexon|simply light|\bsld\b|trailbird|bug ?bivy|\bsixmoon|six moon|hexamid|plexamid|triplex|\blightheart|\bsl ?\d|"
    r"cirriform|\bhornet\b|\bsuper ?mid|echo ?(ii|pyramid)|\bdirigo|\bsuperlight (solo|tarp)|"
    r"\bborah|\byama\b|yama (cirriform|mountain)|\bcricket\b|\bvision ?\d+ ?(bivy|tarp)|\bylmg|\bymg|\bcricket ?tarp|\bflytrex|\bcatenary|\bknot tarp|\bsolo tarp|"
    r"\bpocket tarp|\bsil ?nylon|\bdcf (tarp|shelter)|\bcuben (tarp|shelter)|\b\d ?x ?\d+ ?(tarp|dcf|cuben)|"
    r"\btorrid\b.*(hammock|tarp)|\bwesterly|\bslingfin|\bnemo.*(hornet|dagger|galaxi)|\bmsr.*(hubba|elixir|freelite)|"
    r"\bbig agnes.*(tent|copper|fly)|\bsea to summit.*(alto|telos|specter|escapist)|\btitanium goat|\bttt?m\b|"
    r"\btrailstar|\bfarpoint.*tarp|\bsuperlight|\bbug ?(net|shelter)|poncho ?tarp|sil ?poncho|silponcho|(pro|dcf|cuben|silnylon|sil) poncho|\bmld.*poncho|\d+ ?x ?\d+ ?(cm|m|mm|ft)? ?(tarp|tent|bivy)")
# brands that make several kinds of core gear: weak evidence, may only fill a missing role
WEAK_BRAND = [
    (r"\bmld\b|mountain laurel", ("pack", "shelter", "quilt")),
    (r"gossamer|\bgg\b", ("pack", "pad", "shelter")),
    (r"durston", ("shelter", "pack", "quilt")),
    (r"zpacks", ("pack", "shelter", "quilt")),
    (r"hyperlite|\bhmg\b", ("pack", "shelter")),
    (r"enlightened equipment|\bee\b", ("quilt",)),
    (r"therm-?a-?rest|thermarest|\btar\b", ("pad",)),
    (r"\bnemo\b", ("pad", "shelter", "quilt")),
    (r"sea to summit|\bsts\b|\bs2s\b", ("pad", "quilt", "shelter")),
    (r"big agnes", ("pad", "shelter", "quilt")),
    (r"\bula\b", ("pack",)),
    (r"tarptent", ("shelter",)),
    (r"\bexped\b", ("pad",)),
    (r"\bmsr\b", ("shelter",)),
]
CAT_BIG = re.compile(r"big ?(3|4|5|three|four|five)|\bbig\b|core|essentials?|\bbase\b|heavy|main gear|"
                     r"the big|carry|major|necessities|shelter.*sleep|sleep.*shelter|sleep.*pack|"
                     r"gear\b|basic")
CAT_BIG_STRICT = re.compile(r"big ?(3|4|5|three|four|five)\b|\bbig ?\d")
CAT_OTHER = re.compile(r"cloth|wear|apparel|wardrobe|layers|food|cook|kitchen|electronic|hygiene|"
                       r"toiletr|first aid|water|consum|medical|worn|tech|camera")
CAT_ROLE = {
    "pack": re.compile(r"\bpacks?\b|backpack|\bcarry\b|^bags?\b"),
    "shelter": re.compile(r"shelter|\btent|\btarp|bivy|hammock"),
    "quilt": re.compile(r"\bsleep|\bbed\b|\bquilt|\bbag\b|insulation"),
    "pad": re.compile(r"\bsleep|\bbed\b|\bpad\b|\bmat\b"),
}
# plausible total-grams windows for the main item of a role
WIN = {"pack": (90, 2800), "shelter": (60, 3000), "quilt": (180, 2200), "pad": (50, 1200)}

W_RE = re.compile(r"[:\-]?\s*\d+(\.\d+)?\s*(oz|lb|lbs|kg|g)\b(\s*x\s*\d+)?", re.I)
ACCESSORY = NAME_VETO  # kept for callers; name-level veto is the accessory/other filter


def clean(name, desc=""):
    t = html.unescape(f"{name} {desc}").replace("�", "°").lower()
    t = W_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


NEG = re.compile(
    r"sketch ?pad|note ?pad|writing pad|inflation|inflator|pump ?sack|bivy stick|\bevac\b|tenkara|sit(ting)? ?pad|\bseat\b|z-?seat|bum ?(bag|pack)|\bsteaks?\b|pad (pump|patch)|(pack|pad|bag|quilt|sleeping bag|tent) (liner|cover)|"
    r"bear (bag|canister|vault|protection)|food bag|dry ?bag|ditty|chest pack|hip ?pack|fanny|"
    r"bladder|pack ?towel|pack ?cover|(first aid|repair|cook|cooking|toiletr(y|ies)|med|hygiene|survival|"
    r"emergency|sewing) kit|first[- ]aid|pillow|\bgaiter|\bgloves|\bwater (bag|bottle)|"
    r"trash ?(bag|compactor)|compactor|nylofume|\bbag ?liner|(battery|power|ice|jet|fuel|hydration) ?pack|\d ?mah\b")
# words that rule an item out wherever they appear in the leading clause of the name
GENERIC_HEAD = re.compile(r"^(light|lamp|tops?|bottoms?|layers?|water|food|fuel|cup|hat|cap|map|tp|kit|bear|vest)$")
VETO_ANY = re.compile(
    r"jacket|\bcoat\b|pants|shorts|\bshirt|hood(ie|y)|sweater|fleece|\bvest\b|puffy|parka|\bsocks?\b|"
    r"gloves?|mitts?|bea?e?nie|beany|gaiters?|shoes?|boots?|sandals?|underwear|base ?layer|mid-?layer|headlamp|"
    r"flashlight|phone|camera|tripod|charger|battery|power ?bank|\bwatch\b|inreach|stove|\bpot\b|\bmug\b|"
    r"spork|spoon|lighter|\bfuel\b|canister|filtration|purif|filter|bottle|bladder|sawyer|toothbrush|sunscreen|"
    r"trekking|umbrella|trowel|toilet|pillow|\bchair\b|\bbelt\b|cann?ister|\bpoles?\b|\bst(?:ak|ka)es?\b|\bpegs?\b|guy ?lines?|"
    r"ground ?sheets?|footprint|polycro|tyvek|whoopie|suspension|poncho|clothes|pajamas?|laundry|"
    r"^(sub)?total\b|\bdaisy|\bspider\b|ridge ?line|carabiner|\bbiner|\bstraps\b|tree ?huggers?")


def vetoed(nm):
    """True if the item NAME shows it is not the core item (accessory or other gear)."""
    nm = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", nm)
    seg = re.split(r"[:|]", nm)[0]
    clause = re.split(r"\s*(?:&|\+|\band\b|\bwith\b|\bw/|,|/| - )\s*", seg)[0].strip()
    if NEG.search(clause):
        return True
    words = clause.split()
    head = words[-1] if words else ""
    has_role = any(rx.search(nm) for rx in (N_PACK, N_QUILT, N_PAD, N_SHELTER))
    has_model = any(rx.search(nm) for rx in (M_PACK, M_QUILT, M_PAD, M_SHELTER))
    if NAME_VETO.search(head) and not ((has_role or has_model) and GENERIC_HEAD.match(head)):
        return True
    if has_role:
        return False
    # no role word anywhere: veto if the clause names other gear ("Tripod", "Rain jacket"),
    # unless the name carries a core-gear model ("MLD Pro Poncho", "KS running vest")
    return bool(VETO_ANY.search(clause)) and not has_model


def strong_role(name, desc):
    """
    Return (role, via) from text alone, or (None, None).
    Priority: type word in the name  >  model/brand in the name or description  >  bare "Bag".
    Within a priority tier the earliest token wins. A description contributes only
    models (plus a description that is itself just a type word, e.g. "Sleeping Pad").
    """
    nm = clean(name)
    dm = clean("", desc)
    if vetoed(nm):
        rescued = [r for r, rx in DESC_TYPE.items() if dm and rx.match(dm)]
        if len(rescued) == 1 and not NEG.search(nm):
            return rescued[0], "desc"
        return None, None
    named = bool(re.search(r"[a-z]{2}", nm))
    full = nm + " " + dm
    pairs = (("quilt", N_QUILT, M_QUILT), ("pad", N_PAD, M_PAD), ("pack", N_PACK, M_PACK),
             ("shelter", N_SHELTER, M_SHELTER))
    hits = []                                   # (tier, position, role)
    for role, types, models in pairs:
        t = types.search(nm if named else full)
        if t:
            hits.append((0, t.start(), role))
        m = models.search(full)
        if m:
            hits.append((1, m.start(), role))
        if named and dm and DESC_TYPE[role].match(dm) and not t:
            hits.append((1, 10_000, role))      # description that is only a type word
    roles = {h[2] for h in hits}
    if "quilt" in roles and "shelter" in roles and re.search(
            r"burrow|phoenix|\becon\b|incubator|premiere|underquilt|top ?quilt|\buq\b|\btq\b", full):
        return "quilt", "text"
    if not hits and N_BARE_BAG.search(nm):
        return "quilt", "bare"                  # bare "Bag": caller may reassign by category
    if hits:
        return min(hits)[2], "text"
    return None, None


def weak_roles(name, desc):
    t = clean(name, desc)
    nm = clean(name)
    if vetoed(nm):
        return ()
    for rx, roles in WEAK_BRAND:
        if re.search(rx, t):
            return roles
    return ()


def classify_list(items):
    """
    items: dicts with name, desc, cat, w (total grams), worn, cons.
    Sets item['role'] in ROLES or None, and item['role_via'].
    """
    for it in items:
        it["role"], it["role_via"] = None, None

    def free(i):
        return i["role"] is None and not i["cons"] and not i["worn"]

    def ok_w(r, i):
        return WIN[r][0] <= i["w"] <= WIN[r][1]

    def cat_ok(i):
        return not CAT_OTHER.search(i["cat"].lower())

    def other_role(r, i):
        """True if the item's own text says it is a different core role."""
        sr = strong_role(i["name"], i["desc"])[0]
        return sr is not None and sr != r

    # 1. strong text
    cands = {r: [] for r in ROLES}
    for it in items:
        if it["cons"] or it["worn"]:
            continue
        r, via = strong_role(it["name"], it["desc"])
        if via == "bare" and CAT_ROLE["pack"].search(it["cat"].lower()) and not CAT_ROLE["quilt"].search(
                it["cat"].lower().replace("bag", "")):
            r = "pack"                    # a bare "Bag" in a Backpack category
        if r and CAT_OTHER.search(it["cat"].lower()) and not any(
                rx.search(clean(it["name"])) for rx in (N_PACK, N_QUILT, N_PAD, N_SHELTER)):
            r = None       # model-only match inside a clothing/food/electronics category
        if r and WIN[r][0] <= it["w"]:       # strong text: no upper weight bound (data may be mis-typed)
            cands[r].append(it)
    for r in ROLES:
        c = sorted(cands[r], key=lambda x: -x["w"])
        if r == "pack":
            c = c[:1]
        for it in c:
            it["role"], it["role_via"] = r, "text"

    def missing():
        return [r for r in ROLES if not any(i["role"] == r for i in items)]

    # 2. category named for the role
    for r in missing():
        pool = [i for i in items if free(i) and CAT_ROLE[r].search(i["cat"].lower()) and ok_w(r, i)
                and not vetoed(clean(i["name"])) and not other_role(r, i) and cat_ok(i)]
        pool.sort(key=lambda x: -x["w"])
        if not pool:
            continue
        if r == "pad" and len(pool) >= 1 and not any(i["role"] == "quilt" for i in items):
            continue                         # ambiguous generic 'Sleep' category; wait for quilt first
        pool[0]["role"], pool[0]["role_via"] = r, "category"
    # a generic 'Sleep' category: after quilt is known, next-heaviest free item is the pad
    for r in missing():
        if r != "pad":
            continue
        for q in [i for i in items if i["role"] == "quilt" and CAT_ROLE["pad"].search(i["cat"].lower())]:
            pool = [i for i in items if free(i) and i["cat"] == q["cat"] and ok_w("pad", i)
                    and not vetoed(clean(i["name"])) and not other_role("pad", i) and cat_ok(i)]
            pool.sort(key=lambda x: -x["w"])
            if pool:
                pool[0]["role"], pool[0]["role_via"] = "pad", "category"
                break

    # 3. weak brand evidence fills a still-missing role
    for r in missing():
        pool = [i for i in items if free(i) and r in weak_roles(i["name"], i["desc"]) and ok_w(r, i)
                and not other_role(r, i) and cat_ok(i)
                and (r == "quilt" or not re.search(r"\b(bag|sack|pouch|case)$", clean(i["name"])))]
        pool.sort(key=lambda x: -x["w"])
        if pool:
            pool[0]["role"], pool[0]["role_via"] = r, "brand"

    # 5. hammock sleepers: the underquilt / bottom quilt is the pad
    if "pad" in missing():
        quilts = [i for i in items if i["role"] == "quilt"]
        uq = [i for i in items if free(i) and i["w"] >= 100 and strong_role(i["name"], i["desc"])[0] == "quilt"
              and re.search(r"under|bottom|\buq\b|phoenix|\bnest\b", clean(i["name"], i["desc"]))]
        uq += [i for i in quilts if re.search(r"under|bottom|\buq\b|phoenix|\bnest\b", clean(i["name"], i["desc"]))]
        hammock = any(i["role"] == "shelter" and re.search("hammock", clean(i["name"], i["desc"])) for i in items)
        if uq:
            pick = max(uq, key=lambda x: x["w"])
            # convert only when it is one of two quilts, or a separate free underquilt item; a lone
            # "Quilt (UQ or TQ)" stays the quilt
            if pick["role"] != "quilt" or len(quilts) >= 2:
                pick["role"], pick["role_via"] = "pad", "underquilt"

    # 4. elimination in 'big items' categories
    for cat in {i["cat"] for i in items if CAT_BIG_STRICT.search(i["cat"].lower())}:
        miss = missing()
        if len(miss) != 1:
            continue
        r = miss[0]
        pool = [i for i in items if free(i) and i["cat"] == cat and ok_w(r, i)
                and not vetoed(clean(i["name"]))
                and not (M_PAD.search(clean(i["name"], i["desc"])) or M_QUILT.search(clean(i["name"], i["desc"]))
                         or M_SHELTER.search(clean(i["name"], i["desc"])) or M_PACK.search(clean(i["name"], i["desc"])))]
        if len(pool) == 1:
            pool[0]["role"], pool[0]["role_via"] = r, "eliminated"

    return items


# ── review harness ────────────────────────────────────────────────────────────
def load(conn, cohort=None):
    """Load lists from the public database into the dict shape classify_list() expects."""
    where = "" if cohort in (None, "all") else "WHERE cohort = ?"
    args = () if not where else (cohort,)
    lists = {lid: dict(id=lid, user=f"list-{lid}", url=f"list-{lid}", items=[])
             for (lid,) in conn.execute(f"SELECT id FROM lists {where} ORDER BY id", args)}
    for r in conn.execute("""SELECT i.list_id, i.id, i.name, COALESCE(i.description, ''), i.total_g, i.worn, i.consumable, c.name
                             FROM items i JOIN categories c ON c.id = i.category_id"""):
        if r[0] in lists:
            lists[r[0]]["items"].append(dict(db_id=r[1], name=r[2], desc=r[3], w=r[4] or 0,
                                             worn=bool(r[5]), cons=bool(r[6]), cat=r[7] or ""))
    return lists


def main():
    argv = sys.argv
    cohort = argv[argv.index("--cohort") + 1] if "--cohort" in argv else "all"
    misses_only = "--misses" in argv
    show = int(argv[argv.index("--show") + 1]) if "--show" in argv else None
    conn = sqlite3.connect(DB)
    lists = load(conn, cohort)
    n_ok = {r: 0 for r in ROLES}
    via = {}
    for l in lists.values():
        classify_list(l["items"])
        if show == l["id"]:
            for i in sorted(l["items"], key=lambda i: -i["w"])[:40]:
                print(f"  {i['w']:7.0f} g {str(i['role'] or '-'):<8}{'W' if i['worn'] else ' '}{'C' if i['cons'] else ' '} "
                      f"({i['cat'][:22]}) {i['name'][:40]} | {i['desc'][:50]}")
        got = {r: [i for i in l["items"] if i["role"] == r] for r in ROLES}
        for r in ROLES:
            n_ok[r] += bool(got[r])
            for i in got[r]:
                via[i["role_via"]] = via.get(i["role_via"], 0) + 1
        miss = [r for r in ROLES if not got[r]]
        if misses_only and not miss:
            continue

        def fmt(r):
            g = sorted(got[r], key=lambda i: -i["w"])
            if not g:
                return f"{r}=??"
            top = g[0]
            tag = "" if top["role_via"] == "text" else f"[{top['role_via'][0]}]"
            return f"{r}={top['name'][:26]}({top['w']:.0f}){tag}" + (f"+{len(g) - 1}" if len(g) > 1 else "")
        print(f"list-{l['id']:<5} " + " | ".join(fmt(r) for r in ROLES))
    N = len(lists)
    print(f"\n{cohort}: {N} lists   found: " + "  ".join(f"{r} {n_ok[r]}/{N}" for r in ROLES) + f"   via: {via}")


if __name__ == "__main__":
    main()
