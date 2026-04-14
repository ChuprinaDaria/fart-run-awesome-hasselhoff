import os
import random
import glob
from claude_nagger.i18n import get_language

PHRASES: dict[str, list[str]] = {
    "en": [
        "Don't Hassel the Hoff! You saved tokens, champ!",
        "Hasselhoff would be proud. Few tokens \u2014 big results!",
        "Looking for Freedom! And you found it \u2014 freedom from wasted tokens!",
        "Knight Rider says: efficiency is sexy.",
        "Baywatch mode: saving your budget like Hasselhoff saves the beach!",
        "Hasselhoff approved! Fewer tokens \u2014 more Baywatch time.",
        "The Berlin Wall fell. So did your token costs. HOFF!",
        "David Hasselhoff gives a standing ovation! Efficient coder!",
    ],
    "ua": [
        "Don't Hassel the Hoff! Ти зекономив токени, красунчик!",
        "Hasselhoff б пишався тобою. Мало токенів \u2014 багато результату!",
        "Looking for Freedom! І ти знайшов \u2014 свободу від зайвих токенів!",
        "Knight Rider каже: ефективність \u2014 це сексі.",
        "Baywatch mode: ти рятуєш свій бюджет як Hasselhoff рятує пляж!",
        "Hasselhoff approved! Менше токенів \u2014 більше часу на Baywatch.",
        "Берлінська стіна впала. Як і твої витрати на токени. HOFF!",
        "David Hasselhoff аплодує стоячи! Ефективний кодер!",
    ],
}

_HOFF_DIRS = [
    os.path.expanduser("~/bin/hasselhoff"),
    os.path.join(os.path.dirname(__file__), "..", "assets_hasselhoff"),
]


def get_hoff_phrase() -> str:
    lang = get_language()
    return random.choice(PHRASES.get(lang, PHRASES["en"]))


def get_hoff_image() -> str | None:
    for d in _HOFF_DIRS:
        images = glob.glob(os.path.join(d, "hoff*.jpg")) + glob.glob(os.path.join(d, "hoff*.png"))
        if images:
            return random.choice(images)
    return None


def get_victory_sound() -> str | None:
    for d in _HOFF_DIRS:
        path = os.path.join(d, "victory.mp3")
        if os.path.exists(path):
            return path
    return None
