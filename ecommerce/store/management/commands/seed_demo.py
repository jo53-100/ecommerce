"""
Seed the store with naval-themed demo data (categories + products + generated
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


# ---- Naval Brand palette ----
BG = (247, 248, 250)        # Light warm white
PANEL = (10, 25, 47)        # Navy blue
GOLD = (212, 175, 55)       # Gold accent
GOLD_DIM = (184, 150, 46)   # Darker gold
NAVY = (15, 34, 64)         # Navy medium
TEXT = (240, 244, 248)       # Light text
DIM = (148, 163, 184)       # Muted text


# name, price (MXN), short description
CATALOG = {
    "Gorras": [
        ("Gorra Naval Oficial", 450, "Gorra de oficial de marina con emblema de ancla dorada bordada y visera con hojas de roble."),
        ("Gorra Capitán Dorada", 680, "Gorra de capitán premium con cordón trenzado dorado, emblema de ancla y laureles en la visera."),
        ("Gorra Marinero Clásica", 320, "Boina clásica de marinero en azul marino con pin de ancla dorada lateral."),
        ("Gorra Táctica Naval", 380, "Gorra tipo baseball azul marino con bordado frontal de ancla y ajuste trasero."),
    ],
    "Gorras Bordadas": [
        ("Gorra Bordada Ancla Imperial", 520, "Bordado a mano con ancla y corona imperial en hilo dorado sobre paño azul marino."),
        ("Gorra Bordada Águila Marina", 580, "Diseño exclusivo con águila marina y laureles, bordado artesanal en hilos metálicos."),
        ("Gorra Bordada Escudo Naval", 550, "Escudo naval completo bordado con ancla, cuerda y estrellas en hilo dorado y plateado."),
        ("Gorra Bordada Timón", 490, "Elegante timón de navegación bordado con detalle de cuerda, estilo clásico naval."),
    ],
    "Insignias": [
        ("Insignia Almirante", 350, "Insignia de rango de almirante con estrella y ancla en metal dorado pulido."),
        ("Insignia Capitán de Navío", 280, "Distintivo de capitán de navío con tres barras y ancla, acabado en oro mate."),
        ("Insignia Oficial de Marina", 250, "Insignia de oficial con ancla cruzada y corona, broche seguro incluido."),
        ("Insignia Marinero Raso", 180, "Insignia básica de marinero con ancla sencilla, acabado en metal plateado."),
        ("Pin Ancla Dorada", 120, "Pin decorativo de ancla en baño de oro de 24K, perfecto para solapa o gorra."),
    ],
    "Accesorios": [
        ("Cinturón Naval Ceremonial", 420, "Cinturón de ceremonia con hebilla de ancla dorada, cuero genuino azul marino."),
        ("Parche Bordado Ancla", 85, "Parche termoadhesivo con ancla y laureles, bordado en hilo dorado sobre fondo azul."),
        ("Llavero Ancla Naval", 95, "Llavero metálico con ancla naval 3D en acabado dorado envejecido, cadena resistente."),
        ("Pañuelo Naval", 150, "Pañuelo de seda con estampado de nudos marineros y anclas en azul y dorado."),
        ("Gemelos Ancla Dorada", 280, "Par de gemelos con diseño de ancla en baño de oro, caja de presentación incluida."),
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
    """Render a 1000x1000 branded naval placeholder image for a product."""
    W = H = 1000
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Subtle grid backdrop
    for x in range(0, W, 50):
        d.line([(x, 0), (x, H)], fill=(235, 238, 242), width=1)
    for y in range(0, H, 50):
        d.line([(0, y), (W, y)], fill=(235, 238, 242), width=1)

    # Centered shield (hexagon) with product initials
    cx, cy, r = W // 2, H // 2 - 20, 210
    shield = [
        (cx, cy - r), (cx + int(r * 0.87), cy - r // 2),
        (cx + int(r * 0.87), cy + r // 2), (cx, cy + r),
        (cx - int(r * 0.87), cy + r // 2), (cx - int(r * 0.87), cy - r // 2),
    ]
    d.polygon(shield, fill=PANEL, outline=GOLD, width=4)

    # Inner decorative border
    r2 = r - 20
    shield2 = [
        (cx, cy - r2), (cx + int(r2 * 0.87), cy - r2 // 2),
        (cx + int(r2 * 0.87), cy + r2 // 2), (cx, cy + r2),
        (cx - int(r2 * 0.87), cy + r2 // 2), (cx - int(r2 * 0.87), cy - r2 // 2),
    ]
    d.polygon(shield2, outline=GOLD_DIM, width=2)

    initials = "".join(w[0] for w in name.split()[:2]).upper()
    f_big = _font(140, bold=True)
    tb = d.textbbox((0, 0), initials, font=f_big)
    d.text((cx - (tb[2] - tb[0]) / 2, cy - (tb[3] - tb[1]) / 2 - tb[1]),
           initials, font=f_big, fill=GOLD)

    # Corner brackets - gold
    b = 45
    for (ox, oy, dx, dy) in [(50, 50, 1, 1), (W - 50, 50, -1, 1),
                             (50, H - 50, 1, -1), (W - 50, H - 50, -1, -1)]:
        d.line([(ox, oy), (ox + dx * b, oy)], fill=GOLD, width=3)
        d.line([(ox, oy), (ox, oy + dy * b)], fill=GOLD, width=3)

    # Category caption below shield
    caption = category.upper()
    f_cap = _font(28, bold=True)
    cb = d.textbbox((0, 0), caption, font=f_cap)
    d.text((cx - (cb[2] - cb[0]) / 2, cy + r + 40), caption, font=f_cap, fill=DIM)

    # Brand text at bottom
    brand = "TIENDA NAVAL"
    f_brand = _font(20, bold=True)
    bb = d.textbbox((0, 0), brand, font=f_brand)
    d.text((cx - (bb[2] - bb[0]) / 2, H - 80), brand, font=f_brand, fill=GOLD_DIM)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue())


class Command(BaseCommand):
    help = "Seed the store with naval demo categories, products, and placeholder images."

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
                filename = name.lower().replace(" ", "-").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u") + ".png"
                product.image.save(filename, _make_image(name, cat_name), save=False)
                product.save()
                created_products += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Categories: {Category.objects.count()}, "
            f"Products: {Products.objects.count()} (+{created_products} new)."))
