import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ResourceVisualStateTests(unittest.TestCase):
    def test_declarations_use_native_amount_states(self):
        mineral = json.loads((ROOT / 'bridge-protocol/entities/mineral_field.json').read_text())
        geyser = json.loads((ROOT / 'bridge-protocol/entities/vespene_geyser.json').read_text())
        self.assertEqual(mineral['visual']['animations']['idle']['frames'], [0])
        self.assertEqual(mineral['visual']['animations']['reduced']['frames'], [1])
        self.assertEqual(mineral['visual']['animations']['low']['frames'], [2])
        self.assertEqual(mineral['visual']['animations']['very_low']['frames'], [3])
        self.assertEqual(geyser['visual']['animations']['idle']['frames'], [0])
        self.assertEqual(geyser['visual']['animations']['depleted']['frames'], [0])
        smoke = geyser['visual']['attachments'][0]
        self.assertEqual(smoke['source'], 'unit/thingy/GeySmok1.grp')
        self.assertEqual(smoke['animations']['depleted']['source'], 'unit/thingy/GeySmoS1.grp')

    def test_native_amount_reaches_the_shared_painter(self):
        adapter = (ROOT / 'openbw-bwapi-module/src/WorldAdapter.h').read_text()
        plugin = (ROOT / 'openrct2-plugin/rts-bridge.js').read_text()
        painter = (ROOT / 'openrct2-patches/0029-resource-amount-visuals.patch').read_text()
        self.assertTrue('actor["resource_amount"]' in adapter)
        self.assertTrue('actor["resource_site_id"]' in adapter)
        self.assertTrue('unit.resource_amount' in plugin)
        self.assertTrue('unit.resource_site_id === footprint.geyserSiteID' in plugin)
        self.assertTrue('resourceAmount' in painter)
        self.assertTrue('resourceMotion = actor.resourceAmount == 0 ? "depleted" : "idle"' in painter)
        for threshold in (250, 500, 750):
            self.assertIn(f'actor.resourceAmount < {threshold}', painter)

    def test_local_asset_frames_keep_native_source_anchors(self):
        for kind, canvas in (('mineral_field', [64, 96]), ('vespene_geyser', [128, 64])):
            path = ROOT / 'run-data/generated-assets/starcraft' / kind / 'manifest.json'
            if not path.is_file():
                self.skipTest('licensed local sprite manifest is unavailable')
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest['canvas'], canvas)
            self.assertEqual(manifest['frames']['idle0.png']['source_frame'], 0)
            self.assertEqual(manifest['frames']['very_low0.png' if kind == 'mineral_field'
                                               else 'depleted0.png']['source_frame'],
                             3 if kind == 'mineral_field' else 0)
            for frame in ('idle0.png', 'very_low0.png' if kind == 'mineral_field'
                          else 'depleted0.png'):
                self.assertEqual(manifest['frames'][frame]['source'], manifest['source'])
            if kind == 'vespene_geyser':
                self.assertEqual(manifest['frames']['smoke_depleted0.png']['source'],
                                 'unit/thingy/GeySmoS1.grp')


if __name__ == '__main__':
    unittest.main()
