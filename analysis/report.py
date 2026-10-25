#!/usr/bin/env python3
"""
Report for the r/Ultralight "LighterPack in user flair" lists in data/ul_flair_lists.db.

Produces the numbers behind the "what ultralight backpackers are actually bringing" post:
  1. sample + base-weight summary
  2. the Big 4 (pack / shelter / quilt / pad): median weight, top models
  3. frequency of ~70 item "slots" across categories (any brand), with the most common
     model in each slot and its median weight
  4. a median gear list: every slot carried by >= --min-share of lists, at the weight of the
     most common model (or the slot median when no model dominates)

Slots are matched on item name + description (find_common_items.normalize_text). A slot counts
once per list; its weight is the heaviest matching non-consumable item in that list (unit weight,
quantity excluded), so two pairs of socks are not 2x.  Worn items are reported as worn.

Outputs (in ./out): report.txt, item_frequency.csv, median_gearlist.csv, slot_models.json
Usage:   python flair_report.py [--min-share 0.4]
"""
import csv
import re
import sqlite3
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from ulgear.text import normalize_text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "ul_flair_lists.db"
OUTDIR = ROOT / "out"
OUTDIR.mkdir(exist_ok=True)
G_PER_OZ = 28.3495

# ── slots: name -> (group, regex, exclude-regex, [(model label, regex), ...]) ────────────────────
S = {}


def slot(name, group, rx, models=(), ex=None):
    S[name] = (group, re.compile(rx), re.compile(ex) if ex else None,
               [(l, re.compile(r)) for l, r in models])


# Sleep extras / shelter parts
slot("Pillow", "Sleep", r"pillow|aeros|fillow|flufflux|\bpillo\b",
     [("Sea to Summit Aeros", r"aeros"), ("Nemo Fillow", r"fillow"), ("Therm-a-Rest NeoAir pillow", r"neoair.*pillow|trekker")])
slot("Ground sheet", "Shelter", r"polycro|ground ?sheet|footprint|tyvek|floor",
     [("Polycryo (Gossamer Gear / Frost King)", r"polycro|frost king"), ("Tyvek", r"tyvek")], ex=r"floor ?plan")
slot("Tent stakes", "Shelter", r"\bstakes?\b|groundhog|\bpegs?\b|y-?stake|shepherd",
     [("MSR Groundhog", r"groundhog"), ("Shepherd hook", r"shepherd"), ("Y-stakes", r"\by[- ]stakes?")])
slot("Sit pad", "Sleep", r"sit ?pad|sitlight|z ?-?seat|sit ?mat|torso")
# Water
slot("Water filter", "Water", r"filter|sawyer|squeeze|befree|be free|quick ?draw|katadyn|lifestraw|aquamira|purif|steripen|chlorine|tablet",
     [("Sawyer Squeeze / Mini", r"sawyer|squeeze"), ("Katadyn BeFree", r"befree|be free"),
      ("Platypus QuickDraw", r"quick ?draw"), ("Aquamira drops", r"aquamira"), ("Lifestraw", r"lifestraw")])
slot("Water bottle", "Water", r"bottle|smart ?water|nalgene|platy|evernew|canteen|flask",
     [("Smartwater 1L", r"smart ?water"), ("Nalgene", r"nalgene"), ("Platypus bottle", r"platypus.*bottle|platy.*bottle")],
     ex=r"sawyer|filter")
slot("Dirty water bag / bladder", "Water", r"dirty (water )?bag|cnoc|vecto|bladder|reservoir|water bag|platy(pus)? (bag|2)|hydrapak|evernew.*bag",
     [("CNOC Vecto", r"cnoc|vecto"), ("Platypus bladder", r"platypus|platy")])
# Cooking
slot("Stove", "Cook", r"stove|\bbrs\b|pocket ?rocket|windmaster|amicus|alcohol|jetboil|esbit|mini ?stove|soto|optimus|crux",
     [("BRS-3000T", r"\bbrs\b"), ("MSR PocketRocket", r"pocket ?rocket"), ("Soto Windmaster/Amicus", r"windmaster|amicus|soto"),
      ("Alcohol stove", r"alcohol|fancy feast|cat food"), ("Jetboil", r"jetboil")], ex=r"canister|fuel")
slot("Pot / mug", "Cook", r"\bpot\b|\bmug\b|toaks|cook ?pot|\bcup\b|snow ?peak|evernew|\bti ?750|\bti ?550|\b750 ?ml|\b550 ?ml|\b900 ?ml",
     [("Toaks titanium", r"toaks"), ("Snow Peak titanium", r"snow ?peak"), ("Evernew", r"evernew")], ex=r"cup holder|lid ?only")
slot("Spoon / spork", "Cook", r"spoon|spork|long ?handle|\bfork\b",
     [("Toaks long spoon", r"toaks"), ("Sea to Summit Alpha Light", r"alpha ?light"), ("Sea to Summit long spoon", r"sea to summit.*spoon|\bsts\b.*spoon")])
slot("Lighter", "Cook", r"lighter|\bbic\b|mini ?bic|firestarter|ferro|matches|flint",
     [("Bic mini", r"\bbic\b|mini ?bic")])
slot("Cold-soak jar", "Cook", r"cold ?soak|talenti|\bjar\b|peanut butter jar|jif|ziploc.*(jar|container)")
# Electronics
slot("Headlamp", "Electronics", r"headlamp|head ?lamp|head ?torch|nu ?25|nu ?20|\bspot\b|petzl|actik|storm|\bnu\d+",
     [("Nitecore NU25", r"nu ?25"), ("Nitecore NU20", r"nu ?20"), ("Black Diamond Spot", r"black diamond|\bspot\b"), ("Petzl", r"petzl|actik")])
slot("Power bank", "Electronics", r"power ?bank|battery ?bank|external battery|nb ?10000|\b10 ?000 ?mah|\b10k\b|portable charger|powercore|anker|iniu|redux|\b5000 ?mah|\b20000 ?mah|mophie|zendure|ravpower|battery pack|\bbattery\b",
     [("Nitecore NB10000", r"nb ?10000"), ("Anker", r"anker|powercore"), ("INIU", r"iniu"), ("Zendure", r"zendure"), ("RAVPower", r"ravpower")],
     ex=r"wall|plug|adapter|\bcable|watch|headlamp|aaa")
slot("Phone", "Electronics", r"phone|iphone|pixel|galaxy|samsung|oneplus|moto ",
     [("iPhone", r"iphone"), ("Pixel", r"pixel"), ("Samsung Galaxy", r"samsung|galaxy")], ex=r"case only|charger|cable|holder|mount|wall|plug")
slot("Wall charger", "Electronics", r"wall (charger|plug|adapter)|\bgan\b|\b\d{2} ?w(att)?\b(?!/)|power ?port|\bbrick\b|usb-?c wall|\bplug\b|\bcharger\b|nano (iii|ii|3|iq)",
     [("Anker Nano", r"anker"), ("INIU", r"iniu"), ("Apple", r"apple")], ex=r"mah|10 ?000|10k|power ?bank|battery|solar|portable|nb air")
slot("Charging cable", "Electronics", r"\bcables?\b|\bcords?\b(?!age)|usb-?c (to|cable)|lightning|adapter|\bwire\b|\busb\b",
     [("USB-C cable", r"usb-?c"), ("Lightning cable", r"lightning|apple")], ex=r"mah|power ?bank|battery|wall|plug|bear|guyline|tarp|\bcord ?lock")
slot("Satellite messenger", "Electronics", r"in ?reach|zoleo|spot (gen|x|3)|messenger|satellite|\bsos\b|\bplb\b|beacon|garmin.*mini|starlink",
     [("Garmin inReach Mini", r"in ?reach.*mini|mini 2|inreach mini"), ("Garmin inReach (other)", r"in ?reach"), ("Zoleo", r"zoleo"), ("SPOT", r"\bspot\b")])
slot("Watch / GPS watch", "Electronics", r"watch|garmin (fenix|forerunner|instinct|enduro|venu)|coros|suunto (9|5|race|vertical|core|ambit|spartan)|fenix|forerunner|apple watch",
     [("Garmin watch", r"garmin|fenix|forerunner|instinct"), ("Coros", r"coros"), ("Apple Watch", r"apple watch")])
slot("Earbuds", "Electronics", r"earbud|headphone|airpod|earphone|buds|\bpods\b", [("AirPods", r"airpod"), ("Wired earbuds", r"wired|apple.*headphones|earpods")])
slot("Camera", "Electronics", r"camera|gopro|mirrorless|sony a|fuji|ricoh|canon|nikon|insta360|drone", [("GoPro", r"gopro"), ("Sony", r"sony")])
# Clothing
slot("Puffy / insulated jacket", "Clothing", r"puffy|down (jacket|hoodie|sweater|vest)|insulat|ghost whisperer|nano ?puff|torrid|apex (jacket|hood)|synthetic (jacket|hood)|belay|parka|vest.*(down|synthetic)|hooded (down|synth)|puffer|thermoball|uniqlo.*down|alpha.*(120|90)?\bpuff|uberlight|mountain hardwear|montbell.*(plasma|down|ex ?light|superior)|ex ?light down|goosefeet|\bphantom\b|\bplasma\b",
     [("Enlightened Equipment Torrid", r"torrid|apex"), ("Montbell down/Plasma", r"montbell"), ("Patagonia Nano Puff", r"nano ?puff"),
      ("Mountain Hardwear Ghost Whisperer", r"ghost whisperer"), ("Uniqlo down", r"uniqlo")], ex=r"pants|bottom|booties|sleeping")
slot("Rain jacket", "Clothing", r"rain ?(jacket|coat|shell|gear)|waterproof (jacket|shell)|frogg|helium|shakedry|hardshell|hard shell|\bhefty\b|storm cruiser|torrentshell|ul all[- ]?weather|poncho|rain shell|rainshell|\bgoretex|\bgore-?tex.*jacket|marmot.*precip|precip|zpacks.*vertice|vertice",
     [("Frogg Toggs", r"frogg|toggs"), ("Outdoor Research Helium", r"helium"), ("Montbell (Versalite/Storm Cruiser)", r"montbell|versalite|storm cruiser"),
      ("Marmot PreCip", r"precip"), ("Zpacks Vertice", r"vertice"), ("Patagonia Torrentshell", r"torrentshell")], ex=r"pants|skirt|kilt|cover")
slot("Wind shirt / jacket", "Clothing", r"wind ?(shirt|jacket|shell|breaker)|windshirt|houdini|tachyon|skylite|\bdewy\b|alpine start|squall",
     [("Patagonia Houdini", r"houdini"), ("Montbell Tachyon", r"tachyon"), ("Enlightened Equipment Copperfield", r"copperfield"), ("Black Diamond Alpine Start", r"alpine start")], ex=r"pants")
slot("Sun hoodie / sun shirt", "Clothing", r"sun (hood|shirt|sleeve)|tropic comfort|capilene cool|cool daily|\bhoody?\b.*(sun|upf)|\bupf\b|sun-?gloves|sun protection|columbia.*(silver ridge|freezer)|ls shirt|long ?sleeve",
     [("Patagonia Tropic Comfort", r"tropic comfort"), ("Patagonia Capilene Cool Daily", r"capilene|cool daily"), ("Columbia", r"columbia"), ("Outdoor Research Echo", r"\becho\b")])
slot("Base layer (top or bottom)", "Clothing", r"base ?layer|thermal|merino|long ?john|leggings|long underwear|baselayer|capilene (midweight|thermal)|smartwool 250|tights|sleep (shirt|top)|sleeping (shirt|clothes)",
     [("Merino (generic)", r"merino|smartwool|icebreaker"), ("Patagonia Capilene", r"capilene")], ex=r"socks|underwear")
slot("Rain pants / skirt / kilt", "Clothing", r"rain ?(pants|skirt|kilt|trousers)|kilt|wind ?pants|copperfield|ul all[- ]?weather pant|\bhelium.*pant",
     [("Rain kilt / skirt", r"kilt|skirt"), ("Wind pants", r"wind ?pants|copperfield")])
slot("Hat / buff / headband", "Clothing", r"\bhat\b|\bcap\b|beanie|\bbuff\b|balaclava|headband|neck gaiter|\bvisor\b|sun hat|trucker|mouth ?cover",
     [("Buff", r"buff"), ("Trucker/ball cap", r"trucker|\bcap\b|ball ?cap"), ("Beanie", r"beanie")], ex=r"filter|bottle|lens|water|fuel|head ?net")
slot("Gloves / mitts", "Clothing", r"glove|mitt|\bliner glove|sun glove|\bpogies|shell mitt",
     [("Montbell Climaplus gloves", r"montbell|climaplus"), ("Fleece/liner gloves", r"fleece|liner|glove liner")])
slot("Socks (spare)", "Clothing", r"\bsocks?\b|darn tough|injinji|smartwool|toe sock|crew sock|micro crew",
     [("Darn Tough", r"darn tough"), ("Injinji", r"injinji"), ("Smartwool", r"smartwool"), ("Wigwam", r"wigwam")])
slot("Underwear", "Clothing", r"underwear|boxer|brief|undies|jock|thong|\bundershorts|\bwood\b", [("ExOfficio / generic", r"exofficio|ex officio")])
slot("Shorts", "Clothing", r"shorts|baggies|running shorts|\bskort|hiking shorts|nylon shorts", [("Patagonia Baggies/Strider", r"patagonia|baggies|strider")])
slot("Shirt", "Clothing", r"\bshirt\b|\btee\b|t-?shirt|tank|\bjersey\b|sun hood|singlet|short ?sleeve",
     [("Merino tee", r"merino"), ("Synthetic tee", r"synthetic|polyester|poly")], ex=r"rain|wind|sleep|sun hoodie|base")
slot("Shoes (trail runners)", "Clothing", r"shoes?|trail runner|lone peak|speedgoat|hoka|altra|salomon|topo|brooks|cascadia|\bboots?\b|\bxa pro|nike|adidas|saucony|inov|la sportiva|\bnorvan|\bsandals?\b|ultra ?(ra|roam)|footwear|\btimp\b|\bolympus\b|\bsuperior\b|\bsense ride\b|\bchallenger\b|\bmafate",
     [("Altra Lone Peak", r"lone peak"), ("Hoka", r"hoka|speedgoat|challenger|mafate"), ("Altra (other)", r"altra|timp|olympus|superior"),
      ("Brooks Cascadia", r"cascadia"), ("Topo Athletic", r"topo"), ("Salomon", r"salomon|xa pro")], ex=r"insole|lace|laces|gaiter|stuff|sock")
slot("Gaiters", "Clothing", r"gaiter|\bdirty girl|dirtygirl|\bdg\b", [("Dirty Girl", r"dirty girl|dirtygirl")])
slot("Camp shoes / sandals", "Clothing", r"camp shoes|sandal|crocs|flip ?flops?|slides|\bcamp ?slip|\bcamp ?sock", [("Flip flops", r"flip"), ("Crocs", r"croc")])
# Hygiene, health, misc
slot("First-aid kit", "Health & hygiene", r"first[- ]?aid|\bfak\b|med ?kit|medical|medication|blister|leuko|\bpills?\b|ibuprofen|\bbandaid|moleskin|\bvitamin|medicine|\bmeds\b|advil|tylenol|benadryl|\bzyrtec|band aid|bandage",
     [("Leukotape", r"leuko"), ("Ibuprofen", r"ibuprofen|advil|motrin"), ("Benadryl", r"benadryl|diphen")])
slot("Repair kit", "Health & hygiene", r"repair|tenacious|\bneedle|duct tape|\bpatch(es)?\b|gear aid|aquaseal|\bsewing|\bsilnet|\bglue|zip ?ties?|\bsafety pin",
     [("Tenacious Tape", r"tenacious"), ("Gear Aid", r"gear aid|aquaseal")])
slot("Toothbrush / toothpaste", "Health & hygiene", r"tooth|dental|floss|\bdentist|\bmouthwash", [("Toothpaste tabs", r"tabs?\b|tablet|bite"), ("Short-handle toothbrush", r"cut|short|trimmed")])
slot("Sunscreen", "Health & hygiene", r"sun ?(screen|block)|\bspf\b|\bzinc\b|\bsun lotion|sun ?bum|neutrogena|coppertone|\bsun stick",
     [("Neutrogena", r"neutrogena"), ("Sun Bum", r"sun ?bum"), ("Zinc stick", r"zinc|stick")])
slot("Lip balm", "Health & hygiene", r"chap ?stick|lip ?balm|lipbalm|\blip\b|burt|\bblistex|carmex", [("Chapstick", r"chap ?stick")])
slot("Hand sanitizer", "Health & hygiene", r"sanitizer|purell|\bhand gel|\bhand wash|\bsoap|bronner", [("Purell", r"purell"), ("Dr. Bronner's", r"bronner")])
slot("Trowel", "Health & hygiene", r"trowel|deuce|boglerco|bogler|shovel|\bpoop|digging|\bstake.*dig", [("Deuce of Spades", r"deuce"), ("Bogler / Boglerco", r"bogler")], ex=r"paper")
slot("Toilet paper / bidet / wipes", "Health & hygiene", r"toilet|\btp\b|bidet|wipes|\bkula|pee ?cloth|\bpee rag|\bpaper|\bbandana.*pee|holey hiker|cloth.*pee",
     [("Kula Cloth", r"kula"), ("Holey Hiker bidet", r"holey|bidet"), ("Wet wipes", r"wipes")])
slot("Bug protection", "Health & hygiene", r"bug|insect|repellent|deet|picaridin|permethrin|head ?net|mosquito|\bnetting|\bsawyer.*permethrin|\bspray",
     [("Headnet", r"head ?net|face net"), ("DEET/picaridin", r"deet|picaridin|repellent")], ex=r"bug ?(bivy|shelter|net inner)")
slot("Sunglasses / glasses", "Health & hygiene", r"sunglass|glasses|shades|\bcontacts?\b|\blens\b|polarized|goggles", [("Sunglasses", r"sunglass|shades")])
slot("Knife / multitool / scissors", "Misc", r"knife|multi-?tool|\bsak\b|victorinox|opinel|scissors|razor|leatherman|\bcaseless|swiss army|\bnail clip|tweezers|\bleatherman",
     [("Victorinox Classic SD", r"victorinox|swiss army|\bsak\b"), ("Opinel", r"opinel")])
slot("Trekking poles", "Misc", r"trekking pole|\bpoles?\b|carbon z|distance carbon|fizan|\bflz\b|\bleki\b|\bhiking pole|cascade mountain|\bstick",
     [("Black Diamond poles", r"black diamond|\bbd\b|distance"), ("Cascade Mountain Tech", r"cascade"), ("Gossamer Gear LT5", r"lt5|gossamer")], ex=r"pole ?bag|pole ?strap|\btent pole|\bshelter pole")
slot("Map / compass / navigation", "Misc", r"\bmaps?\b|compass|\bgps\b|\bguthook|\bfarout|gaia|caltopo|\bnav\b|paper map|guidebook", [("Suunto clipper compass", r"clipper|suunto"), ("Paper map", r"paper map|\bmaps?\b")])
slot("Umbrella", "Misc", r"umbrella|chrome dome|sun umbrella", [("Gossamer Gear Lightrek umbrella", r"gossamer|lightrek"), ("Chrome Dome", r"chrome")])
slot("Journal / pen / book", "Misc", r"journal|notebook|\bpen\b|\bpencil|book|kindle|\bpaperwhite|reading|\bdeck of cards|\bcards\b|\bmusic|\bukulele|\bharmonica|\bflute",
     [("Kindle", r"kindle|paperwhite")])
slot("Pack liner", "Misc", r"pack ?liner|nylofume|nyloflume|compactor|turkey ?bag|trash ?(bag|compactor)|\bglad\b|pack ?cover|\bliner\b",
     [("Nylofume / compactor bag", r"nylofume|nyloflume|compactor|turkey|trash|glad"), ("Pack cover", r"cover")], ex=r"sleeping|quilt|bag ?liner|glove|silk|cocoon")
slot("Stuff sacks / dry bags", "Misc", r"stuff ?sack|dry ?(sack|bag)|ditty|\bzip ?lock|ziploc|\bdrybag|\bcompression|\bpouch|\bsack\b|\bopsak|\bloksak",
     [("Ziploc", r"ziploc|zip ?lock"), ("Sea to Summit dry sack", r"sea to summit|\bsts\b"), ("Opsak / Loksak", r"opsak|loksak")], ex=r"pack ?liner|liner|bear|food ?bag|ursack|nylofume|compactor|\bcover")
slot("Bandana / towel", "Misc", r"bandana|towel|\bshamwow|\bsham wow|\bwash ?cloth|\bwashcloth|\bpee ?cloth", [("Bandana", r"bandana"), ("Shamwow / pack towel", r"sham|towel")])
slot("Bear canister / Ursack", "Misc", r"bear (can|canister|vault|bag|sack|spray|box|protection)|bearikade|ursack|\bbv ?500|scout|\bbv450|food ?storage|odor ?proof|opsak|\bloksak|\bbear",
     [("Ursack", r"ursack"), ("Bearikade", r"bearikade"), ("BV500", r"bv ?500"), ("Bear spray", r"bear spray")])

GROUPS = ["Big 4", "Sleep", "Shelter", "Water", "Cook", "Electronics", "Clothing", "Health & hygiene", "Misc"]
CORE = {"pack": "Pack", "shelter": "Shelter", "quilt": "Quilt / sleeping bag", "pad": "Sleeping pad"}
CORE_MODELS = {
    "pack": [("Gossamer Gear (Mariposa/Kumo/Murmur/Gorilla)", r"gossamer|\bgg\b|mariposa|gorilla|kumo|murmur"), ("Nashville / Ultra100 vest pack", r"nashville|ultra ?100|cutaway"),
             ("ULA (Circuit/Ohm/Catalyst)", r"\bula\b|circuit|\bohm\b|catalyst"), ("Zpacks (Arc Haul/Blast, Nero)", r"zpacks|arc ?(haul|blast|zip)|\bnero\b"),
             ("Superior Wilderness Designs", r"\bswd\b|superior wilderness|long ?haul|superior ?\d"), ("Osprey (Exos / Levity / Kestrel)", r"osprey|exos|levity|kestrel|kyte"),
             ("Pa'lante", r"pa'?lante"), ("Hyperlite", r"hyperlite|\bhmg\b|windrider|southwest|junction"), ("Atom Packs", r"atom ?pack|\batom\b"),
             ("Durston Kakwa", r"kakwa|durston"), ("MLD (Burn/Prophet)", r"\bmld\b|burn|prophet|exodus")],
    "shelter": [("Zpacks (Duplex / Plex / Hexamid)", r"zpacks|duplex|plex|hexamid|altaplex|solplex"), ("Durston X-Mid / X-Dome", r"durston|x ?-?mid|x ?-?dome"),
                ("Tarptent", r"tarptent|protrail|stratospire|aeon|notch|moment|rainbow|sidecar"), ("Borah / bivy-based", r"borah|bivy"),
                ("Hammock (any)", r"hammock"), ("Gatewood Cape / SMD", r"gatewood|six moon|\bsmd\b|lunar"), ("MLD (Solomid/Duomid/Trailstar)", r"\bmld\b|solomid|duomid|trailstar"),
                ("Big Agnes", r"big agnes|copper spur|fly creek|tiger wall"), ("Generic tarp / flat tarp", r"\btarp\b|flat tarp"),
                ("3F UL Lanshan", r"lanshan|3f ul"), ("Yama / Hyperlite mids", r"yama|ultamid|hyperlite|\bhmg\b")],
    "quilt": [("Enlightened Equipment", r"enlightened|\bee\b|enigma|revelation|accomplice|convert"), ("Nunatak", r"nunatak|\barc\b|sulo|skaha"),
              ("Katabatic", r"katabatic|palisade|alsek|flex ?\d|\bknik"), ("Hammock Gear", r"hammock gear|burrow|econ|incubator|premiere|phoenix"),
              ("Underground Quilts", r"\bugq\b|underground|bandit"), ("Cumulus", r"cumulus"), ("Zpacks", r"zpacks"), ("Sea to Summit", r"sea to summit|\bsts\b|s2s"),
              ("Aegismax / Naturehike", r"aegismax|naturehike"), ("Western Mountaineering / FF", r"western mountaineering|feathered friends|\bwm\b"), ("Zenbivy", r"zenbivy")],
    "pad": [("Therm-a-Rest NeoAir XLite", r"x ?-?lite|xlite"), ("Therm-a-Rest NeoAir XTherm", r"x ?-?therm|xtherm"), ("Therm-a-Rest NeoAir Uberlite", r"uberlite"),
            ("Therm-a-Rest Z Lite", r"z ?-?lite|z ?-?rest"), ("Nemo Tensor", r"tensor"), ("Nemo (other)", r"\bnemo\b|switchback"), ("Exped", r"exped"),
            ("Sea to Summit", r"sea to summit|ether|comfort"), ("Klymit", r"klymit"), ("Gossamer Gear Thinlight / foam", r"thinlight|nightlight|foam|ccf"), ("Big Agnes", r"big agnes|rapide")],
}


def tgt(i):
    """Slot regexes run on the item NAME; the description only identifies the model (and stands in for a blank name)."""
    n = i.get("ntext") or i["text"]
    return n if re.search(r"[a-z]{3}", n) else i["text"]


def load(conn):
    lists = {lid: dict(id=lid, base=base or 0, items=[]) for lid, base in conn.execute("SELECT id, base_weight_g FROM lists")}
    for r in conn.execute("""SELECT i.list_id, i.name, COALESCE(i.description,''), i.weight_g, i.quantity, i.total_g,
                                    i.worn, i.consumable, i.core_role, c.name
                             FROM items i JOIN categories c ON c.id=i.category_id"""):
        lid, name, desc, w, q, tot, worn, cons, role, cat = r
        lists[lid]["items"].append(dict(name=name, desc=desc, w=w or 0, q=q or 1, tot=tot or 0, worn=bool(worn),
                                        cons=bool(cons), role=role, cat=cat, text=normalize_text(name, desc), ntext=normalize_text(name, "")))
    return lists


def med(v):
    return st.median(v) if v else 0


def main():
    min_share = float(sys.argv[sys.argv.index("--min-share") + 1]) if "--min-share" in sys.argv else 0.5
    conn = sqlite3.connect(DB)
    lists = load(conn)
    L = list(lists.values())
    n = len(L)
    out = []
    P = lambda s="": out.append(s)

    # 1. sample ------------------------------------------------------------------------
    base = sorted(l["base"] for l in L if l["base"] > 0)
    P(f"FLAIR COHORT REPORT   n={n} lists")
    P(f"base weight: median {med(base):.0f} g ({med(base) / 453.592:.1f} lb)  IQR {base[len(base) // 4]:.0f}-{base[3 * len(base) // 4]:.0f} g "
      f"({base[len(base) // 4] / 453.592:.1f}-{base[3 * len(base) // 4] / 453.592:.1f} lb)  mean {st.mean(base):.0f} g")
    tiers = Counter("SUL" if b <= 2270 else "UL" if b <= 4536 else "LW" if b <= 9072 else "Traditional" for b in base)
    P("tiers: " + ", ".join(f"{t} {tiers[t]} ({100 * tiers[t] / len(base):.0f}%)" for t in ("SUL", "UL", "LW", "Traditional")))
    P(f"under 3 kg: {100 * sum(b < 3000 for b in base) / len(base):.0f}%   under 4 kg: {100 * sum(b < 4000 for b in base) / len(base):.0f}%   "
      f"under 5 kg: {100 * sum(b < 5000 for b in base) / len(base):.0f}%")

    # 2. big four ----------------------------------------------------------------------
    P("\n== BIG 4 ==")
    big = {}
    per_list_big = defaultdict(float)
    rows_csv = []
    for role, label in CORE.items():
        prim = {}
        for l in L:
            c = [i for i in l["items"] if i["role"] == role and not i["cons"]]
            if c:
                top = max(c, key=lambda i: i["tot"])
                prim[l["id"]] = top
                per_list_big[l["id"]] += sum(i["tot"] for i in c) if role in ("shelter",) else top["tot"]
        big[role] = prim
        ws = [i["tot"] for i in prim.values()]
        P(f"\n{label}: {len(prim)} of {n} lists, median {med(ws):.0f} g ({med(ws) / G_PER_OZ:.1f} oz), IQR {sorted(ws)[len(ws) // 4]:.0f}-{sorted(ws)[3 * len(ws) // 4]:.0f} g")
        cnt = defaultdict(list)
        unk = []
        for i in prim.values():
            hit = next((m for m, rx in ((m, re.compile(r)) for m, r in CORE_MODELS[role]) if rx.search(tgt(i))), None)
            (cnt[hit] if hit else unk).append(i["tot"])
        for m, v in sorted(cnt.items(), key=lambda x: -len(x[1])):
            P(f"   {len(v):>3} ({100 * len(v) / len(prim):4.1f}%)  {m:<48} median {med(v):.0f} g")
        P(f"   {len(unk):>3} ({100 * len(unk) / len(prim):4.1f}%)  name too generic to attribute (e.g. 'Backpack', 'Quilt') median {med(unk):.0f} g")
    totals = [v for v in per_list_big.values()]
    P(f"\nBig 4 total per list (pack + shelter + quilt + pad): median {med(totals):.0f} g; share of base weight: "
      f"{100 * med([per_list_big[l['id']] / l['base'] for l in L if l['base'] > 0 and l['id'] in per_list_big]):.0f}% (median of per-list ratios)")

    # 3. slot frequency -----------------------------------------------------------------
    P("\n== ITEM SLOTS ACROSS CATEGORIES (share of lists; one count per list) ==")
    slot_rows = []
    for name, (group, rx, ex, models) in S.items():
        present, wts, worns, model_hits = 0, [], [], defaultdict(list)
        for l in L:
            cands = [i for i in l["items"] if not i["cons"] and i["role"] is None and rx.search(tgt(i))
                     and not (ex and ex.search(tgt(i))) and i["w"] < 4000]
            if not cands:
                continue
            present += 1                                    # carried, whether or not a weight was entered
            weighted = [i for i in cands if i["w"] > 0]
            top = max(weighted or cands, key=lambda i: i["w"])
            worns.append(top["worn"])
            if weighted:
                wts.append(top["w"])
            for m, mrx in models:
                if mrx.search(top["text"]):
                    model_hits[m].append(top["w"])          # 0 = no weight entered; dropped below
                    break
        model_hits = {m: v for m, v in model_hits.items()}
        best = max(model_hits.items(), key=lambda x: len(x[1])) if model_hits else (None, [])
        best = (best[0], [w for w in best[1] if w]) if best[0] else best
        slot_rows.append(dict(slot=name, group=group, present=present, share=present / n, median_g=med(wts),
                              worn=sum(worns) > len(worns) / 2 if worns else False,
                              top_model=best[0], top_model_n=len(best[1]), top_model_median_g=med(best[1]),
                              models={m: len(v) for m, v in model_hits.items()},
                              model_stats={m: [len(v), med([w for w in v if w])] for m, v in model_hits.items()}))
    slot_rows.sort(key=lambda r: (GROUPS.index(r["group"]), -r["share"]))
    cur = None
    for r in slot_rows:
        if r["group"] != cur:
            cur = r["group"]
            P(f"\n-- {cur}")
        tm = f"  | most common model: {r['top_model']} x{r['top_model_n']} ({r['top_model_median_g']:.0f} g)" if r["top_model"] else ""
        P(f"  {100 * r['share']:4.0f}%  {r['slot']:<32} median {r['median_g']:>5.0f} g{' (worn)' if r['worn'] else '       '}{tm}")

    with open(OUTDIR / "item_frequency.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "slot", "lists_with", "share", "median_weight_g", "usually_worn", "top_model", "top_model_lists", "top_model_median_g", "models_top4"])
        for r in slot_rows:
            w.writerow([r["group"], r["slot"], r["present"], round(r["share"], 3), round(r["median_g"]), r["worn"],
                        r["top_model"] or "", r["top_model_n"], round(r["top_model_median_g"]),
                        "; ".join(f"{m} x{k}" for m, k in sorted(r["models"].items(), key=lambda x: -x[1])[:4])])

    # 4. median gear list ---------------------------------------------------------------
    P(f"\n== MEDIAN GEAR LIST (slots carried by >= {int(100 * min_share)}% of lists) ==")
    gl = []
    for role, label in CORE.items():
        ws = [i["tot"] for i in big[role].values()]
        cnt = Counter()
        for i in big[role].values():
            hit = next((m for m, r in CORE_MODELS[role] if re.search(r, i["text"])), None)
            if hit:
                cnt[hit] += 1
        top = cnt.most_common(1)[0] if cnt else (None, 0)
        gl.append(dict(group="Big 4", item=label, model=f"{top[0]} (top brand/model, {top[1]} lists)" if top[0] else "",
                       share=len(ws) / n, grams=med(ws), worn=False))
    for r in slot_rows:
        if r["share"] >= min_share:
            use_model = r["top_model"] and r["top_model_n"] >= 3
            grams = r["top_model_median_g"] if use_model else r["median_g"]
            gl.append(dict(group=r["group"], item=r["slot"], model=f"{r['top_model']} ({r['top_model_n']} lists)" if use_model else "",
                           share=r["share"], grams=grams, worn=r["worn"]))
    also = [r for r in slot_rows if 0.25 <= r["share"] < min_share]
    base_total = sum(g["grams"] for g in gl if not g["worn"])
    worn_total = sum(g["grams"] for g in gl if g["worn"])
    for grp in GROUPS:
        rows = [g for g in gl if g["group"] == grp]
        if not rows:
            continue
        P(f"\n-- {grp}")
        for g in rows:
            P(f"  {g['grams']:>5.0f} g {g['grams'] / G_PER_OZ:>5.1f} oz  {'W ' if g['worn'] else '  '}{g['item']:<32} {100 * g['share']:3.0f}%   {g['model']}")
    P(f"\n-- ALSO COMMON (25% to {int(100 * min_share)}% of lists; not in the total)")
    for r in also:
        P(f"  {r['median_g']:>5.0f} g  {'W ' if r['worn'] else '  '}{r['slot']:<32} {100 * r['share']:3.0f}%   {r['top_model'] or ''}")
    P(f"\nTOTAL base (non-worn slots above): {base_total:.0f} g = {base_total / 453.592:.1f} lb;  worn: {worn_total:.0f} g;  "
      f"cohort median base weight: {med(base):.0f} g.  (Sum of medians is not the median of sums; compare the gap.)")
    with open(OUTDIR / "median_gearlist.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "item", "most_common_model", "share_of_lists", "weight_g", "weight_oz", "worn"])
        for g in gl:
            w.writerow([g["group"], g["item"], g["model"], round(g["share"], 2), round(g["grams"]), round(g["grams"] / G_PER_OZ, 1), g["worn"]])

    import json
    big_stats = {}
    for role in CORE:
        cnt = defaultdict(list)
        for i in big[role].values():
            hit = next((m for m, r in CORE_MODELS[role] if re.search(r, i["text"])), None)
            cnt[hit or "(generic name)"].append(i["tot"])
        big_stats[role] = {m: [len(v), med(v)] for m, v in cnt.items()}
    json.dump(dict(n=n, slots={r["slot"]: dict(group=r["group"], present=r["present"], share=r["share"], median_g=r["median_g"],
                                                 worn=r["worn"], models=r["model_stats"]) for r in slot_rows},
                   big4={r: dict(n=len(big[r]), median_g=med([i["tot"] for i in big[r].values()]), models=big_stats[r]) for r in CORE}),
              open(OUTDIR / "slot_models.json", "w"), indent=1)
    (OUTDIR / "report.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
