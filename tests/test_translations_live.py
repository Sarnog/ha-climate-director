"""De vertalingen in een echte Home Assistant.

The translations inside a real Home Assistant."""

from __future__ import annotations

import pytest
from harness_live import (
    start_bare_house,
    start_house,
    stop_house,
)
from live_helpers import (
    cold_two_rooms,
    two_zone_installation,
)

pytest_plugins = ["live_fixtures"]
pytestmark = pytest.mark.usefixtures("appliance")


class TestTheTranslationsLive:
    """Elke taal wordt echt geladen en ingevuld, niet alleen op vorm gecontroleerd.

    Each language is really loaded and filled in, not just checked for shape.
    """

    LANGUAGES = ("en", "nl", "de", "fr", "es", "ar")

    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_every_language_loads_and_fills_its_sentences(self, language: str) -> None:
        home = await start_house(two_zone_installation(), states=cold_two_rooms())
        try:
            home.hass.config.language = language
            from custom_components.climate_director import texts

            await texts.async_prepare(home.hass)
            message = texts.translated(
                home.hass,
                "precondition_refused",
                "fallback {zone} {openings} {minutes}",
                zone="Woonkamer",
                openings="Achterdeur",
                minutes=120,
            )

            assert "{" not in message, f"{language}: {message}"
            assert "Woonkamer" in message, f"{language}: {message}"
            assert "Achterdeur" in message, f"{language}: {message}"
            if language == "nl":
                assert "kon niet vooruit beginnen" in message
            elif language == "en":
                assert "could not start pre-conditioning" in message
        finally:
            await stop_house(home)

    async def test_the_refusal_event_speaks_dutch_in_a_dutch_interface(self) -> None:
        """De gebeurtenis draagt de zin in de taal van de interface.

        The event carries the sentence in the language of the interface.
        """
        home = await start_house(two_zone_installation(), states=cold_two_rooms())
        try:
            home.hass.config.language = "nl"
            from custom_components.climate_director import texts

            await texts.async_prepare(home.hass)

            home.set("person.danny", "not_home")
            home.set("binary_sensor.achterdeur", "on")
            home.coordinator.async_precondition(["woonkamer"], 30)
            await home.evaluate()

            refused = home.fired("climate_director_precondition_refused")
            assert refused, "een geweigerd verzoek hoort zichzelf te melden"
            message = refused[-1]["message"]
            assert "kon niet vooruit beginnen" in message, message
            assert "Nog open" in message, message
            assert "120 minuten" in message, message
        finally:
            await stop_house(home)

    @pytest.mark.parametrize("language", ["en", "nl"])
    async def test_the_installation_error_carries_a_translated_sentence(
        self, language: str
    ) -> None:
        """Zonder installatie draagt de fout een sleutel, en elke taal kent de zin.

        Without an installation the error carries a key, and every language
        knows the sentence.
        """
        from homeassistant.exceptions import ServiceValidationError
        from homeassistant.helpers import translation

        hass = await start_bare_house()
        try:
            hass.config.language = language
            await translation.async_load_integrations(hass, {"climate_director"})
            with pytest.raises(ServiceValidationError) as caught:
                await hass.services.async_call(
                    "climate_director",
                    "precondition",
                    {"zone_ids": ["woonkamer"], "minutes": 30},
                    blocking=True,
                )
            error = caught.value
            assert error.translation_domain == "climate_director"
            assert error.translation_key == "no_installation_configured"
            assert "installation" in str(error)

            cached = translation.async_get_cached_translations(
                hass, language, "exceptions", "climate_director"
            )
            key = "component.climate_director.exceptions.no_installation_configured.message"
            message = cached[key]
            if language == "nl":
                assert "installatie" in message, message
            else:
                assert "installation" in message, message
        finally:
            await hass.async_stop(force=True)

    @pytest.mark.parametrize("language", ["en", "nl"])
    async def test_the_unknown_zone_error_carries_a_translated_sentence(
        self, language: str
    ) -> None:
        """Onbekende zones dragen een sleutel en een ingevulde zin per taal.

        Unknown zones carry a key and a filled-in sentence per language.
        """
        from homeassistant.exceptions import ServiceValidationError
        from homeassistant.helpers import translation

        home = await start_house(two_zone_installation(), states=cold_two_rooms())
        try:
            home.hass.config.language = language
            await translation.async_load_integrations(home.hass, {"climate_director"})
            with pytest.raises(ServiceValidationError) as caught:
                await home.hass.services.async_call(
                    "climate_director",
                    "precondition",
                    {"zone_ids": ["kelder"], "minutes": 30},
                    blocking=True,
                )
            error = caught.value
            assert error.translation_domain == "climate_director"
            assert error.translation_key == "unknown_zones"
            assert "zones" in str(error)
            assert error.translation_placeholders == {"zones": "kelder"}

            cached = translation.async_get_cached_translations(
                home.hass, language, "exceptions", "climate_director"
            )
            message = cached["component.climate_director.exceptions.unknown_zones.message"]
            if language == "nl":
                assert "Onbekende zones" in message, message
            else:
                assert "zones" in message, message
        finally:
            await stop_house(home)
