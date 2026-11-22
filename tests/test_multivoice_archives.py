"""Multi-voice manifest, complete-only packaging, checksums and safe publish."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audio_common as a
import gerar_tudo as g
import empacotar_offline as ep


class MultiVoiceArchives(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for rel in ep.PUBLIC_FILES:
            source = ROOT / rel
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rel == 'tts/index.json':
                dest.write_text('{"version":1,"voices":{}}')
            else:
                shutil.copy2(source, dest)
        for pack in ('animes', 'everyday'):
            dst = self.root / 'packs' / f'{pack}.json'
            dst.parent.mkdir(parents=True, exist_ok=True)
            story = {'id': f'{pack}-one', 'title': f'{pack} story', 'summary': 'Test',
                     'level': 'A1', 'genre': 'Test', 'text': 'Hello world. Decide now!'}
            dst.write_text(json.dumps({'id': pack, 'stories': [story]}))
        catalog = {'version': 1, 'packs': [
            {'id': pid, 'title': pid, 'file': f'packs/{pid}.json', 'count': 1}
            for pid in ('animes', 'everyday')]}
        (self.root / 'catalog.json').write_text(json.dumps(catalog))
        self.saved = {}
        self.patchers = [patch.object(a, 'ROOT', self.root), patch.object(a, 'TTS', self.root / 'tts'),
                         patch.object(g, 'ROOT', self.root), patch.object(g, 'TTS', self.root / 'tts')]
        for item in self.patchers: item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patchers)])
        # Andrew complete for both categories. Ava complete for animes only.
        self.populate('andrew', 'animes')
        self.populate('andrew', 'everyday')
        self.populate('ava', 'animes')
        (self.root / 'tts' / 'generated.json').write_text(json.dumps(self.saved))

    def populate(self, short, pack):
        voice, slug = a.VOICES[short]
        for _, file, text in g.collect({pack}, slug):
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'ID3' + b'\x00' * 512)
            self.saved[file.relative_to(self.root).as_posix()] = a.sha(text, voice)

    def test_voice_discovery_and_nested_packs(self):
        m = ep.build(self.root, self.root / 'dist')
        self.assertEqual(m['version'], 2)
        self.assertEqual(m['defaultVoice'], a.VOICES['andrew'][0])
        self.assertEqual(set(m['voices']), {a.VOICES['andrew'][0], a.VOICES['ava'][0]})
        andrew, ava = m['voices'][a.VOICES['andrew'][0]], m['voices'][a.VOICES['ava'][0]]
        self.assertEqual(andrew['name'], 'Andrew')
        self.assertEqual(ava['locale'], 'en-US')
        self.assertEqual(set(andrew['packs']), {'animes', 'everyday'})
        self.assertEqual(set(ava['packs']), {'animes'})
        files = self.root / 'dist' / 'archives'
        self.assertEqual({p.name for p in files.iterdir()},
                         {'manifest.json','words-andrew.zip','words-ava.zip','animes-andrew.zip',
                          'everyday-andrew.zip','animes-ava.zip'})
        for voice in (andrew, ava):
            for entry in (voice['words'], *voice['packs'].values()):
                z = self.root / 'dist' / entry['url']
                content = z.read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), entry['sha256'])
                self.assertEqual(len(content), entry['bytes'])
                with zipfile.ZipFile(z) as data:
                    self.assertIsNone(data.testzip())
                    for item in data.infolist():
                        self.assertEqual(item.compress_type,
                                         zipfile.ZIP_DEFLATED if item.filename.endswith('.json') else zipfile.ZIP_STORED)
        self.assertNotEqual(andrew['words']['sha256'], ava['words']['sha256'])
        with zipfile.ZipFile(files / 'words-andrew.zip') as data:
            self.assertIn('pronunciations-en-US.json', data.namelist())
            gloss = json.loads(data.read('pronunciations-en-US.json'))
            self.assertEqual(gloss['locale'], 'en-US')
            self.assertIn('decide', gloss['words'])
            self.assertEqual(gloss['words']['decide'], 'di-SÁID')
        self.assertFalse((self.root / 'dist' / 'scripts').exists())
        self.assertFalse((self.root / 'dist' / 'tts/andrew_neural_en-us').exists())
        self.assertFalse((self.root / 'dist' / 'scripts').exists())

    def test_british_voice_does_not_receive_american_pronunciation(self):
        self.populate('sonia', 'animes')
        (self.root / 'tts' / 'generated.json').write_text(json.dumps(self.saved))
        manifest = ep.build(self.root, self.root / 'dist')
        self.assertIn(a.VOICES['sonia'][0], manifest['voices'])
        with zipfile.ZipFile(self.root / 'dist' / 'archives' / 'words-sonia.zip') as data:
            self.assertNotIn('pronunciations-en-US.json', data.namelist())

    def test_auto_skips_incomplete_voice_but_keeps_others(self):
        voice, slug = a.VOICES['ava']
        path = self.root / 'tts' / slug / 'hello.mp3'
        path.unlink()
        m = ep.build(self.root, self.root / 'dist')
        self.assertNotIn(voice, m['voices'])
        self.assertIn(a.VOICES['andrew'][0], m['voices'])

    def test_explicit_strict_refuses_incomplete(self):
        with self.assertRaisesRegex(ValueError, 'Faltam MP3'):
            ep.build(self.root, self.root / 'dist', ['ava'], strict=True)

    def test_if_no_complete_voice_do_not_replace_dist(self):
        out = self.root / 'dist'
        out.mkdir()
        (out / 'keep.txt').write_text('old complete build')
        for voice in ('andrew', 'ava'):
            _, slug = a.VOICES[voice]
            for file in (self.root / 'tts' / slug).glob('*.mp3'):
                file.unlink()
        with self.assertRaisesRegex(ValueError, 'Nenhuma combinação'):
            ep.build(self.root, out)
        self.assertEqual((out / 'keep.txt').read_text(), 'old complete build')

    def test_path_protection_and_stale_purge(self):
        with self.assertRaisesRegex(ValueError, 'Use dist'):
            ep.build(self.root, self.root / 'scripts')
        out = self.root / 'dist'
        out.mkdir()
        (out / 'obsolete.zip').write_bytes(b'old')
        ep.build(self.root, out)
        self.assertFalse((out / 'obsolete.zip').exists())


if __name__ == '__main__':
    unittest.main()
