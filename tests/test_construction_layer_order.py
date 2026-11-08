"""Compile the actual native paint-list ordering helper with small paint entries."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConstructionLayerOrderTest(unittest.TestCase):
    def test_precomplete_below_scv_and_complete_above(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "layer-order"
            subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "upstream/openrct2/src/openrct2/paint"),
                            str(ROOT / "tests/construction_layer_order_fixture.cpp"),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
