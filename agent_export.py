"""Zieht die Gewichte aus einer ``.keras``-Datei in ein ``.npz``.

    python agent_export.py <modell.keras> [ziel.npz]

Damit braucht die Anwendung kein TensorFlow: das Netz ist reines
Dense/ReLU/Softmax, die Vorwaertsrechnung steckt in ``agent_infer.py``.

Die ``.keras``-Datei ist ein ZIP aus ``config.json`` und
``model.weights.h5``. In der H5 heissen die Lagen generisch
(``layers/dense_6/vars/0``), die echten Namen stehen nur in der config.

⚠️ Die Zuordnung MUSS ueber die Reihenfolge in ``config.json`` laufen, nicht
ueber die Form der Tensoren: ``head_laufzeit`` und ``head_kontrakte`` haben
beide die Form (128, 3). Wer nach Form zuordnet, vertauscht Laufzeit und
Kontraktzahl mit 50 % Wahrscheinlichkeit — und merkt es nie, weil beide
Ausgaben plausibel aussehen.

Das Ziel liegt bewusst unter ``/data`` und nicht im Repo: ``/docker/research``
ist oeffentlich.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile

import numpy as np


def exportiere(keras_pfad: str, ziel: str) -> dict[str, tuple]:
    try:
        import h5py
    except ImportError:
        raise SystemExit("h5py fehlt — pip install h5py")

    z = zipfile.ZipFile(keras_pfad)
    cfg = json.loads(z.read("config.json"))
    namen = [l["config"]["name"] for l in cfg["config"]["layers"]
             if l["class_name"] == "Dense"]

    f = h5py.File(io.BytesIO(z.read("model.weights.h5")), "r")
    roh: dict[str, np.ndarray] = {}
    f.visititems(lambda n, o: roh.__setitem__(n, np.array(o))
                 if isinstance(o, h5py.Dataset) else None)

    out: dict[str, np.ndarray] = {}
    form: dict[str, tuple] = {}
    for i, name in enumerate(namen):
        schluessel = "dense" if i == 0 else f"dense_{i}"
        w = roh[f"layers/{schluessel}/vars/0"]
        b = roh[f"layers/{schluessel}/vars/1"]
        out[f"{name}.w"] = w.astype(np.float32)
        out[f"{name}.b"] = b.astype(np.float32)
        form[name] = tuple(w.shape)

    erwartet = {"shared_1", "shared_2", "shared_3", "value_hidden", "value",
                "head_aktion", "head_strike", "head_laufzeit", "head_kontrakte"}
    fehlt = erwartet - set(form)
    if fehlt:
        raise SystemExit(f"Unerwartete Modellstruktur, es fehlen: {sorted(fehlt)}")
    if form["shared_1"][0] != 24:
        raise SystemExit(f"Eingang ist {form['shared_1'][0]}, erwartet 24 Features")
    for kopf, dim in (("head_aktion", 6), ("head_strike", 9),
                      ("head_laufzeit", 3), ("head_kontrakte", 3)):
        if form[kopf][1] != dim:
            raise SystemExit(f"{kopf} hat {form[kopf][1]} Ausgaenge, erwartet {dim}")

    np.savez_compressed(ziel, **out)
    return form


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    quelle = sys.argv[1]
    ziel = sys.argv[2] if len(sys.argv) > 2 else "/data/agent_v8.npz"
    form = exportiere(quelle, ziel)
    print(f"{quelle}  ->  {ziel}")
    for name, f in form.items():
        print(f"   {name:<16} {f}")
    par = sum(np.prod(f) + f[1] for f in form.values())
    print(f"   {int(par):,} Parameter")


if __name__ == "__main__":
    main()
