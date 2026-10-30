#!/usr/bin/env python3
"""
Brand/model word clouds per gear category from the flair lists, in the TrailPeaches look
(Playfair Display / Inter / Caveat, bundled in fonts/, SIL OFL; forest + peach on cream).

Terms are counted by LISTS (a brand named in three items of one list counts once), after
  - merging brand phrases and spellings ("sts", "s2s", "Sea to Summit" -> Sea to Summit),
  - decoding HTML entities,
  - dropping generic words (gear nouns, sizes, colors, materials, filler).

Needs Pillow and numpy (pip install pillow numpy).
Usage:  python analysis/wordclouds.py --terms          # print the top terms per category (tune the filters)
        python analysis/wordclouds.py                  # render PNGs to out/wordclouds/
"""
import collections
import html
import math
import random
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report as fr

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "out" / "wordclouds"
FONTS = ROOT / "fonts"

# ── brand look (theme :root) ──────────────────────────────────────────────────────────────────
FOREST, FOREST_MID, FOREST_DARK = "#2d4a3e", "#3d6454", "#1a2e26"
PEACH, PEACH_DARK = "#e87d5a", "#c8603e"
CREAM, CREAM_MID, BORDER = "#faf8f4", "#f3ede3", "#e3d9cc"
TEXT_MID = "#4a4540"

# ── brand phrases: regex -> display (applied before tokenizing) ───────────────────────────────
PHRASES = [
    (r"therm ?-?a ?-?rest|thermarest|therma ?rest|\btar\b", "Therm-a-Rest"),
    (r"sea ?-?to ?-?summit|\bsts\b|\bs2s\b", "Sea to Summit"),
    (r"enlightened equipment|\bee\b", "Enlightened Equipment"),
    (r"hyperlite mountain gear|hyperlite|\bhmg\b", "Hyperlite"),
    (r"mountain laurel designs|\bmld\b", "MLD"),
    (r"hammock gear|\bhg\b", "Hammock Gear"),
    (r"underground quilts?|\bugq\b", "UGQ"),
    (r"western mountaineering|\bwm\b", "Western Mountaineering"),
    (r"feathered friends", "Feathered Friends"),
    (r"darn ?-?tough", "Darn Tough"),
    (r"frogg? ?-?toggs?", "Frogg Toggs"),
    (r"black diamond|\bbd\b", "Black Diamond"),
    (r"big agnes", "Big Agnes"),
    (r"outdoor research", "Outdoor Research"),
    (r"snow ?-?peak", "Snow Peak"),
    (r"dirty ?-?girl", "Dirty Girl"),
    (r"deuce of spades|the deuce|\bdeuce\b", "Deuce of Spades"),
    (r"holey hiker", "Holey Hiker"),
    (r"six moon designs|\bsmd\b|six moons", "Six Moon Designs"),
    (r"granite gear", "Granite Gear"),
    (r"superior wilderness( designs)?|\bswd\b", "SWD"),
    (r"pa'?-?lante|palante", "Pa'lante"),
    (r"atom ?-?packs?|\batom\b", "Atom Packs"),
    (r"mountain hardwear|\bmhw\b", "Mountain Hardwear"),
    (r"z ?-?packs?|zpacks", "Zpacks"),
    (r"dr\.? ?bronner'?s?", "Dr. Bronner's"),
    (r"nitecore", "Nitecore"),
    (r"x ?-?mid", "X-Mid"),
    (r"x ?-?dome", "X-Dome"),
    (r"neo ?-?air", "NeoAir"),
    (r"x ?-?lite|xlite", "XLite"),
    (r"x ?-?therm|xtherm", "XTherm"),
    (r"z ?-?lite", "Z Lite"),
    (r"in ?-?reach", "inReach"),
    (r"quick ?-?draw", "QuickDraw"),
    (r"be ?-?free", "BeFree"),
    (r"smart ?-?water", "Smartwater"),
    (r"pocket ?-?rocket", "PocketRocket"),
    (r"wind ?-?master", "Windmaster"),
    (r"ghost whisperer", "Ghost Whisperer"),
    (r"lone ?-?peak", "Lone Peak"),
    (r"speed ?-?goat", "Speedgoat"),
    (r"leuko ?-?tape", "Leukotape"),
    (r"tenacious tape", "Tenacious Tape"),
    (r"victorinox|swiss army", "Victorinox"),
    (r"toaks", "Toaks"),
    (r"sawyer( ?squeeze| ?mini)?|squeeze( ?mini)?", "Sawyer Squeeze"), (r"gossamer( gear)?|\bgg\b", "Gossamer Gear"),
    (r"nunatak ?arc|arc ?ul\b", "Nunatak Arc"), (r"sierra designs", "Sierra Designs"), (r"versalite", "Versalite"),
    (r"arc ?-?haul", "Arc Haul"), (r"arc ?-?blast", "Arc Blast"), (r"nashville|cut ?-?away", "Nashville Cutaway"),
    (r"nylo ?-?flume|nylofume", "Nylofume"), (r"cascade mountain tech|\bcmt\b|cascade", "Cascade Mountain Tech"),
    (r"op ?-?sak|lok ?-?sak", "OPSAK"), (r"zip ?-?lock|ziploc", "Ziploc"), (r"bogler ?-?co|bogler", "Bogler"),
    (r"tropic comfort", "Tropic Comfort"), (r"silver ridge", "Silver Ridge"), (r"alpha direct", "Alpha Direct"),
    (r"alpha ?-?light", "Alpha Light"), (r"fancy feast", "Fancy Feast"), (r"light my fire", "Light My Fire"),
    (r"z ?-?seat", "Z Seat"), (r"cnoc|vecto", "CNOC Vecto"),
    (r"north face|\btnf\b", "The North Face"),
    (r"nashville", "Nashville"),
    (r"nunatak", "Nunatak"),
    (r"katabatic", "Katabatic"),
    (r"durston", "Durston"),
    (r"tarptent|tarp tent", "Tarptent"),
]
CAPS = {"nu25": "NU25", "nu20": "NU20", "nb10000": "NB10000", "brs": "BRS", "msr": "MSR", "bic": "BIC", "ula": "ULA", "ccf": "CCF",
        "iphone": "iPhone", "ios": "iOS", "usb-c": "USB-C", "dcf": "DCF", "ul": "UL", "xlite": "XLite", "ks": "KS", "iniu": "INIU",
        "ae": "AE", "ravpower": "RAVPower", "gopro": "GoPro", "oneplus": "OnePlus", "airpods": "AirPods", "powerport": "PowerPort", "powercore": "PowerCore", "liteaf": "LiteAF", "nxt": "NXT", "kojin": "Kojin", "ks": "KS", "ald": "ALD", "rei": "REI", "gsi": "GSI", "lsoh": "LSOH", "hyberg": "Hyberg", "eos": "Eos", "diy": "DIY", "gps": "GPS", "ptfe": "PTFE", "sl": "SL", "cdt": "CDT", "ef": "EF"}
NOCAP = {"ee"}

# ── generic words to drop ─────────────────────────────────────────────────────────────────────
ENGLISH = set("""a an and are as at be but by for from has have in into is it its of on or per than that the their this to up
with without w o x via not no yes if so too very all any both each more most other some such only own same just also can will one two
three four five six seven eight nine ten first second my your our i me we you he she they them his her was were been being do does did
done get got use used using new old plus extra spare backup back optional carry carried carrying mine amp quot nbsp x2f x3d x27 gt lt
about like when where which who whom what how out off over under again then once here there why""".split())
GENERIC = set("""pack backpack backpacks packs bag bags sack sacks pouch pouches pocket pockets strap straps belt hip hipbelt shoulder frame frameless
gear equipment designs design mountain company co inc usa ultralight ultra light lightweight lite weight custom myog diy homemade
quilt quilts sleeping sleep bag down fill fp degree degrees deg reg regular wide long short slim length large small medium xl xxl sm md lg
comfort overfill footbox season seasons summer winter three apex goose power top bottom topquilt underquilt mm cm ml oz lb lbs kg g liter
liters litre litres inch inches ft feet size sizes color colour black white blue green red grey gray orange yellow tan brown purple pink
tent tarp shelter stakes stake pegs peg poles pole groundsheet ground sheet footprint floor inner outer fly body net mesh
pad mat mattress inflatable foam air
water bottle bottles filter filters bladder bag treatment purification tablets drops dropper cap lid flask container storage bag dirty clean
sport sports soft plastic empty reservoir hydration cup mug pot stove stoves fuel canister spoon spork lighter lighters windscreen cook cooking
pot cozy lid handle titanium ti aluminum steel carbon fiber fibre nylon polyester silnylon silpoly sil poly cuben dyneema x-pac xpac dcf merino
wool synthetic cotton fleece insulated insulation puffy jacket coat pants shorts shirt tee top hoodie hoody sweater vest layer base baselayer
rain wind shell sun hat cap beanie buff gloves glove mitts socks sock shoes shoe sandals boots trail runner runners running underwear boxers
gaiters headband
phone cell battery batteries charger charging cable cables cord cords usb usb-c adapter adapters wall plug plugs bank powerbank mah wh amp
headlamp lamp light flashlight torch headphones earbuds earplugs ear plugs case watch camera gps messenger satellite
first aid kit tape toilet paper tp bidet wipes soap sanitizer toothbrush toothpaste tooth brush sunscreen lip balm bug spray repellent
repair patch knife multitool scissors trowel
liner covers cover stuff compression dry food bear canister spray towel bandana map compass
pro mini micro max plus lite ultra v1 v2 v3 v4 v5 gen model version edition set pair piece pieces item items bit
v2 v3 comes came made make by from thanks thank brought bought gift sale cheap amazon ebay aliexpress
trekking hiking backpacking camp camping outdoor outdoors sleeper side flat tapered pull pulls
nano ul sl lt hd xl xs""".split())
# words that are real signal even though they look generic
KEEP = {"nano", "mini", "pro", "plus", "micro"}  # kept only inside phrases, not alone (handled by being in GENERIC)

# Known brands and models (lowercase single tokens).  A term is drawn only if it is a brand/model on this list, a merged
# phrase above, or a word from the community brand list in gear_brands.csv (minus generic words).
MODELS = set("""
pa'lante palante swd arc haul blast ula hyperlite osprey durston kakwa exos dandee atom kumo circuit mld liteaf burn murmur ohm windrider
gorilla joey bonfus sundown threadworks rei wapta ks granite mariposa southwest junction levity yamatomichi hyberg ald hybride seek outside
mystery ranch gregory deuter exped salomon simple nashville cutaway osprey kestrel kyte aura talon prophet
zpacks borah mid x-mid dome mld tarptent duplex six moon hexamid plex yama rainbow altaplex cirriform aeon gatewood protrail msr lunar dimma
solomid lanshan dutchware etowah xenon stratospire cricket notch skyscape trailstar duomid hornet copper spur fly creek tiger wall hubba
slingfin warbonnet eno hennessy kammok grace twinn
enlightened revelation enigma katabatic nunatak cumulus palisade hammock burrow flex ugq bandit western mountaineering timmermade alsek
magma econ aegismax marmot kelty sierra serpentes sulo gryphon libre loco vesper sastrugi astralite feathered hummingbird naturehike zenbivy
nemo montbell wilderness logics lsoh cedar neve jacks better disco
neoair xlite nxt xtherm uberlite tensor thinlight switchback klymit prolite synmat nightlight ridgerest ether inertia kiwicamp paria flextail
vitals sol ccf
smartwater sawyer squeeze befree platypus katadyn quickdraw evernew vecto hydrapak nalgene dasani aquamira platy vesica aquatabs micropur
litesmith lifestraw steripen grayl seeker
bic toaks soto brs windmaster pocketrocket amicus talenti gsi esbit vargo jetboil optimus kojin imusa titan trangia primus snow peak
nitecore iphone anker nu25 nu20 nb10000 garmin inreach pixel apple powercore samsung fenix petzl galaxy casio ravpower google airpods sony
suunto coros aukey powerport otterbox iniu zendure mophie spot zoleo instinct forerunner vapcell fuji gopro ricoh oneplus motorola kindle
fitbit wahoo polar
darn tough patagonia altra lone peak injinji frogg toggs dirty girl columbia smartwool capilene outdoor research decathlon icebreaker topo
nike exofficio torrid versalite copperfield uniqlo hoka tropic comfort helium brooks merrell saucony houdini puff ghost whisperer melanzana
arc'teryx rab hardwear senchi buff fjallraven prana kuhl kuiu wigwam skylight bridgedale xero lowa sportiva scarpa tachyon visp
deuce spades leukotape tenacious tape chapstick bronner bogler kula holey hiker purell gear aid gold bond glide compeed neutrogena coppertone
sun bum blue lizard benadryl
nylofume victorinox ziploc opsak ursack opinel lightload fizan leki cascade leatherman bearikade westcott helinox gerber black diamond
""".split())

TOK = re.compile(r"[a-z][a-z0-9'.\-]*[a-z0-9]|[a-z]")


BRAND_WORDS_RAW = set("""

aegismax aerobie agnes altra anker appalacian armor armour athletics barefoot bauer bearvault borah camelbak cascade
coca-cola cocoon columbia cotopaxi dakine darn deuter diamond dutchware eddie enlightened esbit etowah evernew exofficio
exped fenix fizan frogg garcia golite gregory handi-foil hardwear hartford hefty hilleberg hummingbird hydrapak
hyperlight hyperlite icebreaker imusa katabatic katadyn kelty komperdell kungix laurel leki lightload lightloads
liteoutdoors litesmith luke's marmot mcdonald's melanzana mizuno montbell moond mountaineering naturehike nemo nike
nitecore nunatak oakley opinel optimus ospray osprey pa'lante packtowl paria patagonia petzl products rainwear ravpower
ray-way research robens sawyer showa snow soto stoveworks summit superior suunto tarptent them-a-rest therm-a-rest
thermarest thrunite toaks toggs towels underground uniqlo uniqloe ursack vargo victorinox vivo warbonnet western
wrappers yama zebralight zelph's ziploc zpacks

""".split())   # brand-name words from a community gear survey, words only


FRAGMENTS = set("""hammock peak better simple hardware wilderness logics locus rock silva hiker mid tech fire gold bond essentials outfitters ultimate
direction built bushcraft maple ruta locura qiwiz source goat creek tiger copper spur dome ranch outside jacks cedar neve tough spades bum
haul blast arc ccf sol hammocks gossamer ghost instinct tape tenacious wall fly six moon seek mystery vitals sierra versalite hybride puff
whisperer lone comfort cumulus peak dasani""".split()) - {"dasani"}
MODELS -= FRAGMENTS
BRAND_WORDS = BRAND_WORDS_RAW - FRAGMENTS


def clean_text(t):
    t = html.unescape(html.unescape(t)).lower()
    t = re.sub(r"[:\-]?\s*\d+(\.\d+)?\s*(oz|lb|lbs|kg|g)\b(\s*x\s*\d+)?", " ", t)       # weights
    t = t.replace("�", " ")
    return re.sub(r"\s+", " ", t).strip()


def terms_of(text):
    """Set of display terms in one item's text."""
    t = clean_text(text)
    found = set()
    for rx, disp in PHRASES:
        if re.search(rx, t):
            found.add(disp)
            t = re.sub(rx, " ", t)
    for w in TOK.findall(t):
        w = w.strip(".-'")
        if len(w) < 3 or w in ENGLISH or w in GENERIC or w.isdigit():
            continue
        if w in MODELS or w in BRAND_WORDS:
            found.add(CAPS.get(w, w.title() if w not in NOCAP else w))
    return found


CATEGORIES = [
    ("Packs", "pack"), ("Shelters", "shelter"), ("Quilts & Sleeping Bags", "quilt"), ("Sleeping Pads", "pad"),
    ("Water", "Water"), ("Cooking", "Cook"), ("Electronics", "Electronics"), ("Clothing & Footwear", "Clothing"),
    ("Health & Hygiene", "Health & hygiene"), ("Everything Else", "Misc"),
]
SUB = {"pack": "Most-named packs", "shelter": "Most-named shelters", "quilt": "Most-named quilts and bags", "pad": "Most-named sleeping pads",
       "Water": "Water treatment and carry", "Cook": "Stoves, pots and kitchen", "Electronics": "Phones, lights, power and navigation",
       "Clothing": "What goes on the body", "Health & hygiene": "First aid, repair and hygiene", "Misc": "Poles, knives, liners and the rest"}


def count_terms(lists, key):
    """term -> number of lists naming it, for the items belonging to a category."""
    df = collections.Counter()
    for l in lists.values():
        seen = set()
        for i in l["items"]:
            if i["cons"]:
                continue
            if key in ("pack", "shelter", "quilt", "pad"):
                ok = i["role"] == key
            else:
                ok = i["role"] is None and any(g == key and rx.search(fr.tgt(i)) and not (ex and ex.search(fr.tgt(i)))
                                               for g, rx, ex, ms in fr.S.values())
            if ok:
                seen |= terms_of(f"{i['name']} {i['desc']}")
        df.update(seen)
    return df


# ── rendering ─────────────────────────────────────────────────────────────────────────────────
def font(name, size, var=None):
    f = ImageFont.truetype(str(FONTS / name), size)
    if var:
        try:
            f.set_variation_by_name(var)
        except Exception:
            pass
    return f


def hex2rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def render(title, sub, df, n_lists, path, min_df=3, max_terms=48, seed=7, W=1800, H=1050):
    terms = [(w, c) for w, c in df.most_common() if c >= min_df][:max_terms]
    img = Image.new("RGB", (W, H), hex2rgb(CREAM))
    d = ImageDraw.Draw(img)
    # header
    d.text((90, 62), title, font=font("PlayfairDisplay.ttf", 64, "Bold"), fill=hex2rgb(FOREST))
    d.text((92, 148), sub, font=font("Caveat.ttf", 44, "Bold"), fill=hex2rgb(PEACH_DARK))
    d.rounded_rectangle((90, 208, 210, 214), radius=3, fill=hex2rgb(PEACH))
    # footer
    foot = font("Inter.ttf", 24, "Medium")
    d.text((90, H - 66), f"{n_lists} r/Ultralight gear lists  ·  term size = number of lists that name it", font=foot, fill=hex2rgb(TEXT_MID))
    tp = "trailpeaches.com"
    tw = d.textlength(tp, font=font("PlayfairDisplay.ttf", 28, "Bold"))
    d.text((W - 90 - tw, H - 70), tp, font=font("PlayfairDisplay.ttf", 28, "Bold"), fill=hex2rgb(FOREST))
    # cloud area
    x0, y0, x1, y1 = 90, 250, W - 90, H - 110
    aw, ah = x1 - x0, y1 - y0
    occ = np.zeros((ah, aw), dtype=bool)
    rng = random.Random(seed)
    if not terms:
        img.save(path)
        return []
    top = terms[0][1]
    pal_top = [PEACH, PEACH_DARK, FOREST]
    pal = [FOREST, FOREST_MID, FOREST_DARK, TEXT_MID, FOREST_MID, PEACH_DARK]
    placed = []
    for rank, (w, c) in enumerate(terms):
        size = int(34 + (190 - 34) * math.sqrt(c / top)) if rank > 0 else 200
        size = max(30, size)
        color = pal_top[rank] if rank < 3 else pal[(rank - 3) % len(pal)]
        # a few words go vertical for texture, never the biggest ones
        vertical = rank > 8 and rng.random() < 0.18
        while True:
            f = font("PlayfairDisplay.ttf", size, "Bold")
            bb = f.getbbox(w)
            tw_, th_ = bb[2] - bb[0], bb[3] - bb[1]
            m = Image.new("L", (tw_ + 4, th_ + 4), 0)
            ImageDraw.Draw(m).text((2 - bb[0], 2 - bb[1]), w, font=f, fill=255)
            if vertical:
                m = m.rotate(90, expand=True)
            ma = np.array(m) > 40
            pad = 7                                              # breathing room around words
            ma_p = np.array(Image.fromarray((ma * 255).astype("uint8")).filter(ImageFilter.MaxFilter(pad * 2 + 1))) > 0
            h_, w_ = ma_p.shape
            ok = None
            cx, cy = aw / 2, ah / 2
            for t in range(0, 6000):
                ang = 0.35 * t
                r = 2.4 * ang
                px = int(cx + r * math.cos(ang) * 1.9 - w_ / 2)       # stretched spiral fills the wide card
                py = int(cy + r * math.sin(ang) - h_ / 2)
                if px < 0 or py < 0 or px + w_ > aw or py + h_ > ah:
                    if r > max(aw, ah):
                        break
                    continue
                if not (occ[py:py + h_, px:px + w_] & ma_p).any():
                    ok = (px, py)
                    break
            if ok or size <= 30:
                break
            size = int(size * 0.88)
        if not ok:
            continue
        px, py = ok
        occ[py:py + h_, px:px + w_] |= ma_p
        layer = Image.new("RGB", m.size, hex2rgb(color))
        img.paste(layer, (x0 + px + pad, y0 + py + pad), m) if False else img.paste(layer, (x0 + px + (w_ - m.size[0]) // 2, y0 + py + (h_ - m.size[1]) // 2), m)
        placed.append((w, c, size))
    img.save(path, optimize=True)
    return placed


# Terms that are real brands but, in a given category, only appear because of a neighbouring item (a camera lens cloth in
# "health", a freezer bag in "electronics").
DROP = {"Health & hygiene": {"Fuji", "Kindle", "Ziploc", "Oakley"}, "Electronics": {"Ziploc", "Litesmith", "OPSAK"},
        "Water": {"Ziploc", "Esbit"}, "Cook": {"Ziploc", "Leukotape", "Tenacious Tape"}}
SPECIFICITY = 0.30      # a term must reach this share of its count in its "home" category


def main():
    conn = sqlite3.connect(fr.DB)
    lists = fr.load(conn)
    n = len(lists)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    alts = {}
    all_df = {key: count_terms(lists, key) for _, key in CATEGORIES}
    home = collections.Counter()
    for df_ in all_df.values():
        for t, c in df_.items():
            home[t] = max(home[t], c)
    for title, key in CATEGORIES:
        df = collections.Counter({t: c for t, c in all_df[key].items()
                                  if c / home[t] >= SPECIFICITY and t not in DROP.get(key, ())})
        if "--terms" in sys.argv:
            print(f"\n## {title}  ({sum(1 for c in df.values() if c >= 3)} terms with >= 3 lists)")
            print("  " + ", ".join(f"{w} {c}" for w, c in df.most_common(60)))
            continue
        slug = re.sub(r"[^a-z]+", "-", title.lower()).strip("-")
        placed = render(title, SUB[key], df, n, OUTDIR / f"ul-wordcloud-{slug}.png")
        alts[slug] = dict(key=key, title=title, file=f"ul-wordcloud-{slug}.png",
                          alt=f"Word cloud of the brands and models named most often under {title} across {n} r/Ultralight gear lists. Largest terms: "
                              + ", ".join(w for w, c, sz in placed[:6]) + ".")
        print(f"{title:<24} {len(placed)} terms placed; top: " + ", ".join(f"{w} ({c})" for w, c, s in placed[:6]))
    if alts:
        _dump(alts)


def _dump(alts):
    import json
    (OUTDIR / "wordcloud_alts.json").write_text(json.dumps(alts, indent=1))


if __name__ == "__main__":
    main()
