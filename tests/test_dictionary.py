"""Teste sem rede: sentidos múltiplos, preservação, deduplicação e integração."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from atualizar_dicionario import atualizar_dicionario, ler_dicionario, escolher_sentidos
from adicionar_historia import salvar_historias

payload = {
    'responseStatus': 200,
    'responseData': {'translatedText': 'certo'},
    'matches': [
        {'segment': 'right', 'translation': 'direita', 'match': 1.0},
        {'segment': 'right', 'translation': 'certo', 'match': 1.0},
        {'segment': 'rights', 'translation': 'direitos', 'match': 1.0},
        {'segment': 'right', 'translation': 'correto', 'match': 0.95},
    ],
}
assert escolher_sentidos(payload, 'right') == 'certo; direita'
assert escolher_sentidos(payload, 'right', max_sentidos=1) == 'certo'
assert escolher_sentidos({'responseStatus': 429}, 'right') is None

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'packs').mkdir()
    (root / 'catalog.json').write_text(json.dumps({'packs': [], 'stories': []}), encoding='utf-8')
    (root / 'dictionary.js').write_text(
        "window.STORYSPEAK_DICTIONARY = {'the':'o; a','ocean':'oceano'};\n", encoding='utf-8')
    pack = {'id':'fantasy','title':'Fantasy','file':'packs/fantasy.json','count':0}
    salvar_historias(pack, True, [{'title':'The Right Path','text':'The right path led to the ocean.',
                                   'level':'B1'}], root=root)
    requests = []
    def fake_api(word):
        requests.append(word)
        return payload if word == 'right' else {
            'responseStatus': 200, 'responseData': {'translatedText': 'caminho' if word == 'path' else 'conduziu'},
            'matches': []}
    result = atualizar_dicionario(root, consultar=fake_api, pausa=0, mostrar=False)
    assert sorted(requests) == ['led', 'path', 'right', 'to'], requests
    mapping = ler_dicionario((root / 'dictionary.js').read_text())
    assert mapping['right'] == 'certo; direita'
    assert mapping['the'] == 'o; a'
    assert result['novas'] == 4 and result['restantes'] == 0, result
    previous = (root / 'dictionary.js').read_bytes()
    result = atualizar_dicionario(root, consultar=fake_api, pausa=0, mostrar=False)
    assert result['consultadas'] == 0 and (root / 'dictionary.js').read_bytes() == previous

print('OK: sentidos múltiplos, preservação de traduções, integração e reexecução sem rede')
