"""Il piano reale non gira con le prove veloci: un nome tolto da `prossima` lo
romperebbe solo sul server, dopo minuti di prove (il 2026-10-10 `testi.quasi`,
sparito con gli annunci nuovi). Qui si controlla che i nomi dei moduli di
`prossima` che usa esistano ancora."""

import ast
import importlib
from pathlib import Path

REALE = Path(__file__).parent / "reale"


def test_il_piano_reale_usa_solo_nomi_che_esistono():
    mancanti = []
    for file in sorted(REALE.glob("*.py")):
        albero = ast.parse(file.read_text(encoding="utf-8"))
        moduli = {
            alias.asname or alias.name: importlib.import_module(f"prossima.{alias.name}")
            for nodo in ast.walk(albero)
            if isinstance(nodo, ast.ImportFrom) and nodo.module == "prossima"
            for alias in nodo.names
        }
        for nodo in ast.walk(albero):
            if (
                isinstance(nodo, ast.Attribute)
                and isinstance(nodo.value, ast.Name)
                and nodo.value.id in moduli
                and not hasattr(moduli[nodo.value.id], nodo.attr)
            ):
                mancanti.append(f"{file.name}:{nodo.lineno} {nodo.value.id}.{nodo.attr}")
    assert mancanti == []
