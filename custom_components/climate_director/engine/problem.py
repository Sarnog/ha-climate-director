"""Eén klacht over de configuratie.

One configuration complaint.
"""

from __future__ import annotations


class Problem(str):
    """One configuration complaint, readable as text and identifiable by code.

    Een `str`-subklasse met opzet: alles wat er al mee werkte - de diagnose, het
    logboek, de tests - blijft werken alsof er niets veranderd is. De code komt
    er alleen bij, zodat de Home Assistant-laag er een vertaling bij kan zoeken.
    De Engelse tekst blijft de terugval, dus een melding zonder vertaling is
    nooit erger dan hij was.

    A `str` subclass on purpose: everything already working with these - the
    diagnostics, the log, the tests - keeps working as though nothing changed.
    The code is merely added, so the Home Assistant layer can look up a
    translation for it. The English text stays the fallback, so a complaint
    without a translation is never worse off than it was.
    """

    code: str
    params: dict[str, str]

    def __new__(cls, code: str, text: str, **params: object) -> Problem:
        """Return the complaint, carrying its code and placeholders."""
        item = super().__new__(cls, text)
        item.code = code
        item.params = {key: str(value) for key, value in params.items()}
        return item
