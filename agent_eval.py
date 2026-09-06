"""Bewertungslauf ohne TensorFlow — serverseitig.

    python agent_eval.py <Trainingsskript.py> <modell.keras|.npz> [Episoden] [bericht.json]

Warum das geht: In ``Opt_tensorflowV9.py`` steckt TensorFlow ausschliesslich
in der Klasse ``PPOAgent``. Datenladen, Binomialpreis, Margin-Rechnung, die
Umgebung und die Vergleichsregel sind reines NumPy und pandas. Für die
Bewertung wird der Agent nur an einer einzigen Stelle gebraucht: um aus einem
Zustand einen Aktionsindex zu machen. Genau diese Funktion reicht
``evaluiere()`` seit v9.1 als Parameter ``politik`` herein.

Deshalb wird hier NICHTS nachgebaut. Die Umgebung, die Preisrechnung, die
Vergleichsregel und das Berichtsformat kommen unveraendert aus dem
Trainingsskript; ersetzt wird allein die Vorwaertsrechnung des Netzes durch
``agent_infer`` (Dense/ReLU/Softmax in NumPy).

Der Import von ``tensorflow`` wird durch eine Attrappe bedient. Das ist
gefahrlos, solange ``PPOAgent`` nie gebaut wird -- und das passiert nicht,
wenn eine Politik uebergeben wird. Sollte das Skript spaeter TensorFlow an
anderer Stelle brauchen, schlaegt der Import fehl statt still Unsinn zu
rechnen: die Attrappe hat keine Attribute.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types

import numpy as np

import agent_export
import agent_infer as ai


def _tensorflow_attrappe() -> None:
    if "tensorflow" in sys.modules:
        return
    tf = types.ModuleType("tensorflow")
    keras = types.ModuleType("tensorflow.keras")
    tf.keras = keras
    sys.modules["tensorflow"] = tf
    sys.modules["tensorflow.keras"] = keras


def lade_skript(pfad: str):
    _tensorflow_attrappe()
    spec = importlib.util.spec_from_file_location("trainingsskript", pfad)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["trainingsskript"] = modul
    spec.loader.exec_module(modul)
    return modul


def pruefe_uebereinstimmung(modul) -> None:
    """Die Listen in agent_infer muessen denen der Umgebung entsprechen.

    Sonst zeigt der Aktionsindex auf etwas anderes als gemeint -- und zwar
    lautlos, weil jede Zahl im gueltigen Bereich liegt.
    """
    env = modul.OptionsEnvV9
    paare = [
        ("Aktionen", ai.AKTIONEN, env.leg_actions),
        ("Strikes", ai.STRIKE_PCT, env.strike_prozent),
        ("Laufzeiten", ai.LAUFZEITEN, env.laufzeiten),
        ("Kontrakte", ai.KONTRAKTE, env.kontraktgroessen),
    ]
    for name, a, b in paare:
        if list(a) != list(b):
            raise SystemExit(
                f"{name} stimmen nicht ueberein:\n  agent_infer {list(a)}\n"
                f"  Umgebung    {list(b)}")


def politik_aus_gewichten(npz_pfad: str):
    G = ai.lade_gewichte(npz_pfad)

    def politik(state: np.ndarray) -> int:
        koepfe, _ = ai.vorwaerts(G, state)
        return ai.entscheidung(koepfe)["aktion_idx"]

    return politik


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    skript, modell = sys.argv[1], sys.argv[2]
    episoden = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    bericht = sys.argv[4] if len(sys.argv) > 4 else None

    modul = lade_skript(skript)
    pruefe_uebereinstimmung(modul)
    print(f"Trainingsskript geladen: {skript} (Version {modul.VERSION})")

    if modell.endswith(".keras"):
        npz = os.path.join("/tmp", os.path.basename(modell)[:-6] + ".npz")
        agent_export.exportiere(modell, npz)
        print(f"Gewichte exportiert: {npz}")
    else:
        npz = modell

    modul.evaluiere(os.path.basename(modell), episoden, bericht,
                    politik=politik_aus_gewichten(npz))


if __name__ == "__main__":
    main()
