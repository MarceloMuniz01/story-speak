"""Testes locais, sem conexão: atualizador seguro e importador de histórias."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from atualizar_projeto import atualizar
from adicionar_historia import salvar_historias

with TemporaryDirectory() as tmp:
    base = Path(tmp)
    (base / 'index.html').write_text('original', encoding='utf8')
    (base / 'catalog.json').write_text((ROOT / 'catalog.json').read_text(), encoding='utf8')
    (base / 'packs').mkdir()
    for source in (ROOT / 'packs').glob('*.json'):
        (base / 'packs' / source.name).write_bytes(source.read_bytes())
    (base / 'tts').mkdir()
    (base / 'tts' / 'andrew.mp3').write_bytes(b'old mp3 stays')
    zip_path = base / 'update.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('app.js', 'NEW APP')
        zf.writestr('tts/andrew.mp3', 'SHOULD NOT OVERWRITE')
        zf.writestr('catalog.json', '{"bad":true}')
        zf.writestr('packs/everyday.json', '{"bad":true}')
    previous_catalog = (base / 'catalog.json').read_bytes()
    previous_pack = (base / 'packs/everyday.json').read_bytes()
    result = atualizar(zip_path, base)
    assert result['copiados'] == 1, result
    assert (base / 'app.js').read_text() == 'NEW APP'
    assert (base / 'tts/andrew.mp3').read_bytes() == b'old mp3 stays'
    assert (base / 'catalog.json').read_bytes() == previous_catalog
    assert (base / 'packs/everyday.json').read_bytes() == previous_pack
    # Story import creates a new category and updates both catalog and pack JSON.
    pack = {'id': 'fantasy', 'title': 'Fantasia', 'file': 'packs/fantasy.json',
            'count': 0, 'emoji': '✨', 'description': 'Contos fantásticos'}
    story = {'title': 'A Starry Night', 'text': 'The dragon was asleep. A knight entered.',
             'level': 'B1', 'genre': 'Fantasy', 'tags': ['dragon'], 'summary': 'A magical night'}
    saved = salvar_historias(pack, True, [story], root=base)
    assert saved[0]['id'] == 'a-starry-night'
    catalog = json.loads((base / 'catalog.json').read_text())
    assert any(p['id'] == 'fantasy' for p in catalog['packs'])
    assert any(s['id'] == 'a-starry-night' for s in catalog['stories'])
    assert json.loads((base / 'packs/fantasy.json').read_text())['stories'][0]['text'] == story['text']
print('OK: atualização protege tts/histórias e cadastro de categoria/história')
