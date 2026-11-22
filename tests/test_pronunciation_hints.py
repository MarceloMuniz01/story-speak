"""Independent offline CMUdict integration and Brazilian-friendly respelling tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gerar_pronuncias as p


class PronunciationHints(unittest.TestCase):
    def test_real_cmudict_and_examples(self):
        data = p.cmu_lookup({'value', 'decide', 'intention', 'read', 'through'})
        self.assertEqual(p.respell(data['value'][0]), 'VÉL-iu')
        self.assertEqual(p.OVERRIDES['decide'], 'di-SÁID')
        self.assertEqual(p.OVERRIDES['intention'], 'in-TÉN-shãn')
        self.assertTrue(p.ambiguous(data['read']))
        self.assertTrue(p.respell(data['through'][0]))

    def test_extracts_only_story_words_and_excludes_ambiguous(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / 'packs').mkdir()
            (root / 'catalog.json').write_text(json.dumps({'packs':[{'file':'packs/animes.json'}]}))
            (root / 'packs/animes.json').write_text(json.dumps({'stories':[
                {'text': 'Value is great. I read many things. Decide now!'}]}))
            data = p.build_data(root)
            self.assertEqual(data['words']['value'], 'VÉL-iu')
            self.assertEqual(data['words']['decide'], 'di-SÁID')
            self.assertNotIn('read', data['words'])
            self.assertIn('read', data['uncertain'])
            self.assertNotIn('ghost', data['words'])
            self.assertEqual(data['locale'], 'en-US')

    def test_syllabic_stress_uses_regular_letters(self):
        lookup = p.cmu_lookup({'value', 'decide', 'computer', 'beautiful'})
        for word, pronunciations in lookup.items():
            hint = p.OVERRIDES.get(word) or p.respell(pronunciations[0])
            self.assertTrue(hint)
            self.assertTrue(any(letter.isupper() for letter in hint))
            self.assertFalse(any(x in hint for x in '/ˈˌɑɛəɪʊɔθðʃʒ/'))


if __name__ == '__main__':
    unittest.main()
