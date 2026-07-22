"""
Assign externally generated product images to database products.

Usage:
    python manage.py assign_images /path/to/images/
"""
import os
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from store.models.products import Products

# Map generated image filenames (partial match) to product names
IMAGE_MAP = {
    "gorra_naval_oficial": "Gorra Naval Oficial",
    "gorra_capitan_dorada": "Gorra Capitán Dorada",
    "gorra_marinero_clasica": "Gorra Marinero Clásica",
    "gorra_tactica_naval": "Gorra Táctica Naval",
    "gorra_bordada_ancla": "Gorra Bordada Ancla Imperial",
    "gorra_bordada_aguila": "Gorra Bordada Águila Marina",
    "gorra_bordada_escudo": "Gorra Bordada Escudo Naval",
    "gorra_bordada_timon": "Gorra Bordada Timón",
    "insignia_almirante": "Insignia Almirante",
    "insignia_capitan": "Insignia Capitán de Navío",
    "insignia_oficial": "Insignia Oficial de Marina",
    "insignia_marinero": "Insignia Marinero Raso",
    "pin_ancla": "Pin Ancla Dorada",
    "cinturon_naval": "Cinturón Naval Ceremonial",
    "parche_bordado": "Parche Bordado Ancla",
    "llavero_ancla": "Llavero Ancla Naval",
    "panuelo_naval": "Pañuelo Naval",
    "gemelos_ancla": "Gemelos Ancla Dorada",
}


class Command(BaseCommand):
    help = "Assign AI-generated product images from a directory to matching products."

    def add_arguments(self, parser):
        parser.add_argument("image_dir", type=str, help="Path to directory with product images")

    def handle(self, *args, **options):
        image_dir = Path(options["image_dir"])
        if not image_dir.is_dir():
            self.stderr.write(self.style.ERROR(f"Directory not found: {image_dir}"))
            return

        assigned = 0
        for img_file in sorted(image_dir.glob("*.png")):
            filename = img_file.stem.lower()
            # Try to match against IMAGE_MAP keys
            for key, product_name in IMAGE_MAP.items():
                if filename.startswith(key):
                    try:
                        product = Products.objects.get(name=product_name)
                        with open(img_file, "rb") as f:
                            product.image.save(
                                f"{key}.png",
                                File(f),
                                save=True,
                            )
                        assigned += 1
                        self.stdout.write(f"  ✓ {product_name} ← {img_file.name}")
                    except Products.DoesNotExist:
                        self.stdout.write(self.style.WARNING(
                            f"  ✗ Product '{product_name}' not found in database"))
                    break

        self.stdout.write(self.style.SUCCESS(f"\nDone. {assigned} images assigned."))
