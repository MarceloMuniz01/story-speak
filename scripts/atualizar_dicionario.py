#!/usr/bin/env python3
"""Atualiza dictionary.js usando WikDict inglês-português 100% local.

Não usa serviços de tradução, contas, API keys ou dependências Python extras.
No primeiro uso baixa *um arquivo* aberto do WikDict; depois funciona offline.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from audio_common import ROOT, WORD_PATTERN, read_json, write_json
from wikdict_local import download_once, lookup

BEGIN = '// STORYSPEAK: INÍCIO DAS TRADUÇÕES AUTOMÁTICAS'
END = '// STORYSPEAK: FIM DAS TRADUÇÕES AUTOMÁTICAS'
PAIR = re.compile(r'''(?P<key>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")\s*:\s*(?P<value>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")''')

# Pequenas correções já revisadas na v23 são preservadas como fallback, sem API.
FALLBACKS = {
    'hatred': 'ódio; aversão', 'matters': 'assuntos; questões; importa',
    "that's": 'isso é; esse é; essa é', 'relationships': 'relacionamentos; relações',
    'sever': 'cortar; romper; separar', 'sacrificed': 'sacrificado; sacrificou',
    'vanquished': 'derrotado; vencido', 'monster': 'monstro',
    'hell': 'inferno', 'pain': 'dor; sofrimento', 'interest': 'interesse; juros',
    'longer': 'mais longo; por mais tempo', 'wake': 'acordar; despertar',
    'matter': 'assunto; matéria; importar', 'such': 'tal; desse tipo',
    'eaten': 'comido; ingerido', 'nuisance': 'incômodo; inconveniência',
    'academics': 'acadêmicos; estudos acadêmicos', 'concepts': 'conceitos',
    'concept': 'conceito',
}


def ler_dicionario(source: str) -> dict[str, str]:
    found = {}
    for match in PAIR.finditer(source):
        try:
            key = ast.literal_eval(match['key'])
            value = ast.literal_eval(match['value'])
        except (SyntaxError, ValueError):
            continue
        if isinstance(key, str) and WORD_PATTERN.fullmatch(key) and isinstance(value, str):
            found[key.lower().replace('’', "'")] = value
    return found


def _separar_bloco(source: str) -> tuple[str, dict[str, str]]:
    if BEGIN not in source:
        return source.rstrip() + '\n', {}
    before, rest = source.split(BEGIN, 1)
    if END not in rest:
        raise ValueError('Bloco automático incompleto em dictionary.js')
    raw_auto, after = rest.split(END, 1)
    return before.rstrip() + after.rstrip() + '\n', ler_dicionario(raw_auto)


def escrever_dicionario(path: Path, updates: dict[str, str]) -> None:
    source = path.read_text(encoding='utf-8')
    manual, previous = _separar_bloco(source)
    base = ler_dicionario(manual)
    previous.update({k: v for k, v in updates.items() if k not in base})
    previous = {key: value for key, value in previous.items() if key not in base}
    if previous:
        payload = json.dumps(previous, ensure_ascii=False, sort_keys=True, indent=2)
        result = (manual.rstrip() + '\n\n' + BEGIN + '\n'
                  + 'Object.assign(window.STORYSPEAK_DICTIONARY, ' + payload + ');\n'
                  + END + '\n')
    else:
        result = manual.rstrip() + '\n'
    if result != source:
        tmp = path.with_suffix('.js.tmp')
        tmp.write_text(result, encoding='utf-8')
        tmp.replace(path)


def palavras_das_historias(root: Path) -> set[str]:
    result = set()
    catalog = read_json(root / 'catalog.json')
    for pack in catalog.get('packs', []):
        data = read_json(root / pack['file'])
        for story in data.get('stories', []):
            result.update(w.lower().replace('’', "'") for w in WORD_PATTERN.findall(story['text']))
    return result


def atualizar_dicionario(root: Path = ROOT, *, words: set[str] | None = None,
                          max_sentidos: int = 3, limite: int = 0, revisar: bool = False,
                          sem_download: bool = False, caminho_wikdict: Path | None = None,
                          workers: int = 1, pausa: float = 0, mostrar: bool = True,
                          **_compat) -> dict:
    """Acrescenta palavras ausentes; --revisar substitui só traduções automáticas.

    `workers`/`pausa` são aceitos por compatibilidade com adicionar_historia.py;
    consultas locais não precisam de concorrência nem delay.
    """
    if not 1 <= max_sentidos <= 5:
        raise ValueError('Use 1–5 sentidos.')
    path = root / 'dictionary.js'
    manual, automatic = _separar_bloco(path.read_text(encoding='utf-8'))
    base = ler_dicionario(manual)
    all_words = palavras_das_historias(root)
    source_words = all_words if words is None else words
    candidates = {w.lower().replace('’', "'") for w in source_words if WORD_PATTERN.fullmatch(w)}
    pending = sorted(candidates - base.keys() if revisar else candidates - (base.keys() | automatic.keys()))
    if limite > 0:
        pending = pending[:limite]
    stats = {'novas': 0, 'revisadas': 0, 'falhas': 0, 'consultadas': len(pending), 'restantes': 0}
    if mostrar:
        print(f'Dicionário local: {len(base) + len(set(automatic) - set(base))} palavras atuais; '
              f'{len(pending)} a consultar. Fonte: WikDict (sem API).', flush=True)
    if not pending:
        return stats

    dict_path = caminho_wikdict or root / 'data' / 'wikdict-en-pt.zip'
    try:
        if not sem_download:
            download_once(dict_path)
        elif not dict_path.is_file():
            raise FileNotFoundError(f'Baixe o pacote WikDict en-pt em {dict_path}')
        found = lookup(dict_path, set(pending), max_meanings=max_sentidos)
    except Exception as exc:
        # Sem internet no primeiro uso: preserva o dicionário atual e informa.
        if mostrar:
            print('WikDict indisponível: ' + str(exc), flush=True)
            print('Sem alterações. Baixe manualmente: https://download.wikdict.com/'
                  'dictionaries/stardict/wikdict-en-pt.zip', flush=True)
        raise

    errors = read_json(root / 'dictionary-pending.json')
    if not isinstance(errors, dict):
        errors = {}
    for i, word in enumerate(pending, 1):
        translation = FALLBACKS.get(word) or found.get(word)
        if translation:
            if word in automatic:
                if revisar and automatic[word] != translation:
                    automatic[word] = translation
                    stats['revisadas'] += 1
            else:
                automatic[word] = translation
                stats['novas'] += 1
            errors.pop(word, None)
            if mostrar:
                print(f'[{i}/{len(pending)}] {word} → {translation}', flush=True)
        elif word not in automatic:
            errors[word] = 'Sem verbete no WikDict en-pt; revisão posterior necessária'
            stats['falhas'] += 1
            if mostrar:
                print(f'[{i}/{len(pending)}] Sem verbete: {word}', flush=True)
    escrever_dicionario(path, automatic)
    write_json(root / 'dictionary-pending.json', errors)
    stats['restantes'] = len(all_words - ler_dicionario(path.read_text(encoding='utf-8')).keys())
    if mostrar:
        print(f"Concluído: +{stats['novas']} novas, {stats['revisadas']} revisadas; "
              f"{stats['restantes']} palavras ainda pendentes.", flush=True)
    return stats


def main():
    parser = argparse.ArgumentParser(description='Traduções sem contas e sem API via WikDict local.')
    parser.add_argument('--revisar', action='store_true', help='Revisa o bloco automático com o WikDict.')
    parser.add_argument('--limite', type=int, default=0, help='Máximo de palavras (0 = todas).')
    parser.add_argument('--sentidos', type=int, default=3, help='Até quantos sentidos (1–5).')
    parser.add_argument('--sem-download', action='store_true', help='Não tenta baixar WikDict.')
    parser.add_argument('--wikdict', type=Path, help='Usa um ZIP StarDict en-pt baixado manualmente.')
    args = parser.parse_args()
    try:
        atualizar_dicionario(max_sentidos=args.sentidos, limite=args.limite, revisar=args.revisar,
                              sem_download=args.sem_download, caminho_wikdict=args.wikdict)
    except Exception as exc:
        parser.exit(1, f'Erro: {exc}\n')


if __name__ == '__main__':
    main()
