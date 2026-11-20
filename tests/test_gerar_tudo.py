"""Offline tests of the one-command generator and resume/index logic."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
with TemporaryDirectory(prefix='storyspeak-v17-') as folder:
    dest = Path(folder) / 'site'
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('__pycache__','*.mp3','*.part'))
    sys.path.insert(0, str(dest / 'scripts'))
    from gerar_tudo import collect
    from audio_common import VOICES, sha
    voice, slug = VOICES['andrew']
    everyday = collect({'everyday'}, slug)
    all_audio = collect({'everyday', 'technology', 'mystery', 'ideas'}, slug)
    assert len(everyday) == 215
    assert len(all_audio) == 749
    assert sum(t == 'palavras' for t,_,_ in everyday) == 183
    assert sum(t == 'frases' for t,_,_ in everyday) == 29
    assert sum(t == 'histórias' for t,_,_ in everyday) == 3
    meta = {}
    for _, path, text in everyday:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'ID3' + b'\x00' * 600)
        meta[path.relative_to(dest).as_posix()] = sha(text, voice)
    (dest/'tts/generated.json').write_text(json.dumps(meta))
    def command(*args):
        return subprocess.run([sys.executable,'scripts/gerar_tudo.py',*args],cwd=dest,check=True,capture_output=True,text=True).stdout
    assert 'Índice atual: 0/215' in command('--pack','everyday','--status')
    command('--pack','everyday','--reindex')
    assert 'Índice atual: 215/215' in command('--pack','everyday','--status')
    assert '215' in command('--pack','everyday','--dry-run')
    # all previously generated files are reused and a corrupt/missing file is detected
    next(p for k,p,_ in everyday if k=='palavras').unlink()
    assert '214/215' in command('--pack','everyday','--status')
    print('OK: generator totals, no-network index, reuse and missing detection')
