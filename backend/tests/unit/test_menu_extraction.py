"""ExtractedMenuItem normalization — the deterministic guard behind the
extraction prompt. The model is asked to keep numbering out of `name` and to
skip echo-translations, but occasionally misses; the validator enforces it."""

from app.domain import ExtractedMenuItem


class TestNumberPrefix:
    def test_strips_number_prefix_into_number(self):
        item = ExtractedMenuItem(name="12. Bún Chạo Tôm")
        assert item.name == "Bún Chạo Tôm"
        assert item.number == "12"

    def test_supports_letter_codes_and_other_separators(self):
        assert ExtractedMenuItem(name="A3) Pad Thai").name == "Pad Thai"
        assert ExtractedMenuItem(name="7 - Ramen").number == "7"

    def test_keeps_explicit_number_over_prefix(self):
        item = ExtractedMenuItem(name="12. Bún Chạo Tôm", number="12a")
        assert item.number == "12a"
        assert item.name == "Bún Chạo Tôm"

    def test_plain_names_untouched(self):
        item = ExtractedMenuItem(name="Chả Giò Tôm Thịt")
        assert item.name == "Chả Giò Tôm Thịt"
        assert item.number is None

    def test_name_that_is_only_a_number_survives(self):
        item = ExtractedMenuItem(name="42. ")
        assert item.name == "42. "

    def test_number_stripped_from_translated_name_too(self):
        item = ExtractedMenuItem(
            name="12. Bún Chạo Tôm", translated_name="12. Krevetová nudlová mísa"
        )
        assert item.translated_name == "Krevetová nudlová mísa"
        assert item.number == "12"


class TestEchoTranslations:
    def test_translation_equal_to_original_is_dropped(self):
        item = ExtractedMenuItem(name="Francesinha", translated_name="Francesinha")
        assert item.translated_name is None

    def test_description_echo_is_dropped(self):
        item = ExtractedMenuItem(
            name="x", description="with fries", translated_description="with fries"
        )
        assert item.translated_description is None

    def test_real_translations_survive(self):
        item = ExtractedMenuItem(
            name="Kachna s bramborem",
            translated_name="Duck with potatoes",
            description="s knedlíkem",
            translated_description="with dumplings",
        )
        assert item.translated_name == "Duck with potatoes"
        assert item.translated_description == "with dumplings"
