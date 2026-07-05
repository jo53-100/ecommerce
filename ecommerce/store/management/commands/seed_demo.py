"""
Seed the store with on-theme demo data (categories + products + generated
placeholder images).

Usage:
    python manage.py seed_demo          # add demo data, keep existing rows
    python manage.py seed_demo --reset  # wipe products/categories first

The command is idempotent: running it twice will not create duplicates.
Generated product images are written to MEDIA_ROOT/uploads/products/.
"""
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from store.models.categories import Category
from store.models.products import Products

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:  # pragma: no cover - PIL is expected to be installed
    HAS_PIL = False


# ---- Brand palette (matches the tactical theme in base.html) ----
BG = (18, 20, 18)
PANEL = (28, 31, 26)
OLIVE = (107, 122, 58)
OLIVE_HI = (142, 165, 74)
TAN = (196, 168, 130)
TEXT = (236, 235, 228)
DIM = (143, 144, 132)


# name, price (USD), short description
CATALOG = {
    "Apparel": [
        ("Ranger Combat Shirt", 89, "Moisture-wicking torso, ripstop sleeves. Built for the plate carrier."),
        ("Softshell Recon Jacket", 179, "Wind- and water-resistant softshell with pit zips and MOLLE-ready arms."),
        ("Ripstop Field Pants", 119, "Articulated knees, 11 pockets, teflon-treated ripstop. All-day mobility."),
    ],
    "Headwear": [
        ("Boonie Field Hat", 34, "Wide-brim sun defeat, drain grommets, laser-cut ventilation."),
        ("Operator Ball Cap", 29, "Low-profile crown with hook panel for patches and IR markers."),
    ],
    "Packs & Bags": [
        ("72HR Assault Pack", 189, "40L three-day loadout with hydration sleeve and laser-cut MOLLE."),
        ("Low-Vis Sling Bag", 79, "Ambidextrous EDC sling with concealed-carry back panel."),
        ("Deploy Duffel 90L", 149, "Cavernous grab-and-go duffel with backpack straps and lockable zips."),
    ],
    "Optics": [
        ("Recon Red Dot Sight", 249, "2 MOA dot, 50k-hour runtime, absolute co-witness mount."),
        ("Nightfall Monocular", 329, "Gen-2 digital night vision with IR illuminator and recording."),
    ],
    "Footwear": [
        ("Terrain GTX Boots", 219, "Waterproof GORE-TEX membrane, Vibram sole, side-zip fast entry."),
    ],
    "Accessories": [
        ("MOLLE Admin Pouch", 39, "Organizer panel for maps, tools, and comms. Loop-lined interior."),
        ("Rigger Tactical Belt", 49, "AUS-made webbing rated to 2,500 lbf with quick-release cobra buckle."),
        ("Field Trauma Kit", 59, "IFAK essentials: tourniquet, hemostatic gauze, chest seal, shears."),
    ],
}


def _font(size, bold=False):
    """Best-effort load of a bundled/system font, falling back to PIL default."""
    candidates = [
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _make_image(name, category):
    """Render a 1000x1000 branded placeholder image for a product."""
    W = H = 1000
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # faint grid backdrop
    for x in range(0, W, 50):
        d.line([(x, 0), (x, H)], fill=(24, 27, 23), width=1)
    for y in range(0, H, 50):
        d.line([(0, y), (W, y)], fill=(24, 27, 23), width=1)

    # centered shield (hexagon-ish) with product initials
    cx, cy, r = W // 2, H // 2 - 20, 210
    shield = [
        (cx, cy - r), (cx + int(r * 0.87), cy - r // 2),
        (cx + int(r * 0.87), cy + r // 2), (cx, cy + r),
        (cx - int(r * 0.87), cy + r // 2), (cx - int(r * 0.87), cy - r // 2),
    ]
    d.polygon(shield, fill=PANEL, outline=OLIVE_HI, width=4)

    initials = "".join(w[0] for w in name.split()[:2]).upper()
    f_big = _font(150, bold=True)
    tb = d.textbbox((0, 0), initials, font=f_big)
    d.text((cx - (tb[2] - tb[0]) / 2, cy - (tb[3] - tb[1]) / 2 - tb[1]),
           initials, font=f_big, fill=OLIVE_HI)

    # corner brackets
    b = 40
    for (ox, oy, dx, dy) in [(50, 50, 1, 1), (W - 50, 50, -1, 1),
                             (50, H - 50, 1, -1), (W - 50, H - 50, -1, -1)]:
        d.line([(ox, oy), (ox + dx * b, oy)], fill=OLIVE_HI, width=4)
        d.line([(ox, oy), (ox, oy + dy * b)], fill=OLIVE_HI, width=4)

    # single centered caption under the shield (card supplies name/SKU/category)
    caption = category.upper()
    f_cap = _font(30, bold=True)
    cb = d.textbbox((0, 0), caption, font=f_cap)
    d.text((cx - (cb[2] - cb[0]) / 2, cy + r + 40), caption, font=f_cap, fill=DIM)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue())


class Command(BaseCommand):
    help = "Seed the store with demo categories, products, and placeholder images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete existing products and categories before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not HAS_PIL:
            self.stderr.write(self.style.ERROR(
                "Pillow is required. Install it with: pip install Pillow"))
            return

        if options["reset"]:
            Products.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing products and categories."))

        created_products = 0
        for cat_name, items in CATALOG.items():
            category, _ = Category.objects.get_or_create(name=cat_name)
            for name, price, desc in items:
                if Products.objects.filter(name=name).exists():
                    continue
                product = Products(
                    name=name, price=price, category=category, description=desc,
                )
                filename = name.lower().replace(" ", "-").replace("&", "and") + ".png"
                product.image.save(filename, _make_image(name, cat_name), save=False)
                product.save()
                created_products += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Categories: {Category.objects.count()}, "
            f"Products: {Products.objects.count()} (+{created_products} new)."))
