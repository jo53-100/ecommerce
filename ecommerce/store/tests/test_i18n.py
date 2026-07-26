"""Translations and the language switcher."""

import re

from django.urls import reverse

from .base import StoreTestCase


class LanguageSwitchTests(StoreTestCase):
    """Spanish is the source language; English comes from locale/en/."""

    def test_default_language_is_spanish(self):
        response = self.client.get('/store/')
        self.assertContains(response, 'Nuestros Productos')

    def test_switching_to_english_translates_the_page(self):
        response = self.client.post(reverse('set_language'), {
            'language': 'en', 'next': '/store/'})
        self.assertEqual(response.status_code, 302)
        response = self.client.get('/store/')
        self.assertContains(response, 'Our Products')
        self.assertNotContains(response, 'Nuestros Productos')

    def test_switching_back_to_spanish(self):
        self.client.post(reverse('set_language'), {
            'language': 'en', 'next': '/store/'})
        self.client.post(reverse('set_language'), {
            'language': 'es', 'next': '/store/'})
        response = self.client.get('/store/')
        self.assertContains(response, 'Nuestros Productos')

    def test_navigation_is_translated(self):
        """Guards against a stale catalog leaving the chrome untranslated."""
        self.client.post(reverse('set_language'), {
            'language': 'en', 'next': '/store/'})
        response = self.client.get('/store/')
        for english, spanish in [('Home', 'Inicio'), ('Catalog', 'Catálogo'),
                                 ('Store', 'Tienda')]:
            with self.subTest(term=english):
                self.assertContains(response, english)
                self.assertNotContains(response, f'>{spanish}<')

    def test_switcher_returns_to_the_current_page(self):
        response = self.client.post(reverse('set_language'), {
            'language': 'es', 'next': '/login/'})
        self.assertEqual(response.url, '/login/')

    def test_html_lang_attribute_follows_the_language(self):
        self.client.post(reverse('set_language'), {
            'language': 'es', 'next': '/store/'})
        response = self.client.get('/store/')
        self.assertContains(response, '<html lang="es"')


class TranslationCatalogTests(StoreTestCase):
    """The compiled .mo must exist and actually contain Spanish."""

    def test_english_catalog_is_compiled(self):
        from django.conf import settings
        mo = settings.LOCALE_PATHS[0] / 'en' / 'LC_MESSAGES' / 'django.mo'
        self.assertTrue(
            mo.exists(),
            'locale/en/LC_MESSAGES/django.mo is missing — '
            'run: python manage.py compilemessages')

    def test_english_catalog_is_not_stale(self):
        """Every {% trans %} string must have an English translation.

        Fails when someone adds Spanish copy without running
        `makemessages -l en` and filling in the new msgstr.
        """
        from django.conf import settings

        po = settings.LOCALE_PATHS[0] / 'en' / 'LC_MESSAGES' / 'django.po'
        text = po.read_text(encoding='utf-8')

        # Spanish-looking msgids left with an empty msgstr are untranslated.
        entries = re.findall(r'^msgid ((?:"[^"]*"\n?)+)msgstr ""$',
                             text, re.M)
        spanish_chars = set('áéíóúñ¿¡ÁÉÍÓÚÑ')
        untranslated = [
            e.strip() for e in entries
            if set(e) & spanish_chars and e.strip() != '""'
        ]
        self.assertEqual(
            untranslated, [],
            f'{len(untranslated)} Spanish string(s) have no English '
            f'translation: {untranslated[:5]}')

    def test_key_pages_render_in_both_languages(self):
        for language in ('en', 'es'):
            for path in ('/store/', '/login/', '/signup/'):
                with self.subTest(language=language, path=path):
                    self.client.post(reverse('set_language'), {
                        'language': language, 'next': path})
                    self.assertEqual(self.client.get(path).status_code, 200)
