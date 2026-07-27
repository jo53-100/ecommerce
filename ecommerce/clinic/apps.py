from django.apps import AppConfig


class ClinicConfig(AppConfig):
    name = 'clinic'
    # Matches the BigAutoField ids already baked into 0001_initial. Declared on
    # the app rather than globally so `store`'s existing AutoField ids are left
    # alone — changing those would generate a migration for every store model.
    default_auto_field = 'django.db.models.BigAutoField'
