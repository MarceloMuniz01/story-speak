#!/usr/bin/env python3
"""Adiciona ao dictionary.js as palavras novas de packs/, com até 3 sentidos.

Consulta MyMemory somente para palavras ainda não presentes; preserva as traduções
originais e grava um bloco gerado separado. Não precisa de dependências externas.

  python scripts/atualizar_dicionario.py
  python scripts/atualizar_dicionario.py --limite 20
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from audio_common import ROOT, WORD_PATTERN, read_json, write_json

BEGIN = '// STORYSPEAK: INÍCIO DAS TRADUÇÕES AUTOMÁTICAS'
END = '// STORYSPEAK: FIM DAS TRADUÇÕES AUTOMÁTICAS'
PAIR = re.compile(r'''(?P<key>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")\s*:\s*(?P<value>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")''')


class RateLimit(Exception):
    """Limite/negação do serviço: encerra o lote, sem insistir."""


def _literal(text: str) -> str:
    return ast.literal_eval(text) if text.startswith("'") else json.loads(text)


def ler_dicionario(source: str) -> dict[str, str]:
    """Lê os pares do dictionary.js atual, inclusive os gerados anteriormente."""
    found = {}
    for match in PAIR.finditer(source):
        try:
            key = _literal(match['key'])
            value = _literal(match['value'])
        except (SyntaxError, ValueError, json.JSONDecodeError):
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
    generated_text, after = rest.split(END, 1)
    return before.rstrip() + after.rstrip() + '\n', ler_dicionario(generated_text)


def escrever_dicionario(path: Path, updates: dict[str, str]) -> None:
    source = path.read_text(encoding='utf-8')
    manual, previous = _separar_bloco(source)
    # As traduções manuais/básicas vencem qualquer tradução automática.
    base = ler_dicionario(manual)
    previous.update({k: v for k, v in updates.items() if k not in base})
    previous = {k: v for k, v in previous.items() if k not in base}
    if not previous:
        return
    payload = json.dumps(previous, ensure_ascii=False, sort_keys=True, indent=2)
    block = (f'\n{BEGIN}\n'
             f'Object.assign(window.STORYSPEAK_DICTIONARY, {payload});\n'
             f'{END}\n')
    result = manual.rstrip() + '\n' + block
    if result != source:
        temporary = path.with_suffix('.js.tmp')
        temporary.write_text(result, encoding='utf-8')
        temporary.replace(path)


def palavras_das_historias(root: Path) -> set[str]:
    result = set()
    catalog = read_json(root / 'catalog.json')
    for pack in catalog.get('packs', []):
        data = read_json(root / pack['file'])
        for story in data.get('stories', []):
            result.update(word.lower().replace('’', "'") for word in WORD_PATTERN.findall(story['text']))
    return result


def limpar_sentido(value: object, word: str) -> list[str]:
    if not isinstance(value, str):
        return []
    text = html.unescape(value).strip().lower().replace('\u00a0', ' ')
    if any(x in text for x in ('<', '>', '{', '}', 'http://', 'https://', '\n')):
        return []
    out = []
    for part in re.split(r'[;,]', text):
        part = ' '.join(part.strip(' .,:\t\r').split())
        if (part and len(part) <= 48 and len(part.split()) <= 6
                and part.casefold() != word.casefold()
                and any(ch.isalpha() for ch in part)):
            out.append(part)
    return out


def escolher_sentidos(payload: dict, word: str, max_sentidos: int = 3) -> str | None:
    """Usa a tradução principal e alternativas exatas do mesmo vocábulo."""
    if not isinstance(payload, dict) or str(payload.get('responseStatus', '200')) != '200':
        return None
    options = []
    response = payload.get('responseData', {})
    if isinstance(response, dict):
        options.extend(limpar_sentido(response.get('translatedText'), word))
    matches = payload.get('matches', [])
    if isinstance(matches, list):
        for item in sorted((m for m in matches if isinstance(m, dict)),
                           key=lambda m: _quality(m.get('match')), reverse=True):
            segment = str(item.get('segment', '')).strip().lower().replace('’', "'")
            if segment != word or _quality(item.get('match')) < 0.97:
                continue
            options.extend(limpar_sentido(item.get('translation'), word))
    unique = []
    for option in options:
        if option.casefold() not in [x.casefold() for x in unique]:
            unique.append(option)
        if len(unique) >= max_sentidos:
            break
    return '; '.join(unique) if unique else None


def _quality(value) -> float:
    try:
        quality = float(value)
        return quality / 100 if quality > 1 else quality
    except (TypeError, ValueError):
        return 0


def consultar_api(word: str) -> dict:
    query = urlencode({'q': word, 'langpair': 'en|pt-BR'})
    request = Request('https://api.mymemory.translated.net/get?' + query,
                      headers={'User-Agent': 'StorySpeak-dictionary/1.0'})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read(128_000).decode('utf-8'))


def atualizar_dicionario(root: Path = ROOT, *, words: set[str] | None = None,
                          max_sentidos: int = 3, limite: int = 0, pausa: float = 0.8,
                          consultar=consultar_api, mostrar: bool = True) -> dict:
    """Atualiza só as traduções inéditas; pode receber um consultor simulado em testes."""
    if not 1 <= max_sentidos <= 5:
        raise ValueError('Use entre 1 e 5 sentidos.')
    path = root / 'dictionary.js'
    manual, auto = _separar_bloco(path.read_text(encoding='utf-8'))
    known = ler_dicionario(manual) | auto
    candidates = sorted(words if words is not None else palavras_das_historias(root))
    pending = sorted({w.lower().replace('’', "'") for w in candidates if WORD_PATTERN.fullmatch(w)
                      and w.lower().replace('’', "'") not in known})
    if limite > 0:
        pending = pending[:limite]
    errors = read_json(root / 'dictionary-pending.json')
    stats = {'novas': 0, 'falhas': 0, 'consultadas': len(pending), 'restantes': 0}
    if mostrar:
        print(f'Dicionário: {len(known)} palavras prontas; {len(pending)} novas nesta execução.')
    try:
        for i, word in enumerate(pending, 1):
            try:
                response = consultar(word)
                if not isinstance(response, dict):
                    raise ValueError('Resposta inválida da API')
                if 'quota' in str(response.get('responseDetails', '')).lower():
                    raise RateLimit(str(response.get('responseDetails')))
                translation = escolher_sentidos(response, word, max_sentidos)
                if not translation:
                    raise ValueError('Sem tradução confiável')
                auto[word] = translation
                errors.pop(word, None)
                stats['novas'] += 1
                if mostrar:
                    print(f'[{i}/{len(pending)}] {word} → {translation}')
            except HTTPError as exc:
                errors[word] = f'HTTP {exc.code}'
                stats['falhas'] += 1
                if exc.code in (401, 403, 429):
                    if mostrar:
                        print(f'Serviço limitou as requisições (HTTP {exc.code}).')
                    break
            except RateLimit as exc:
                errors[word] = str(exc)
                stats['falhas'] += 1
                if mostrar:
                    print('Limite da API atingido; pode continuar em outra execução.')
                break
            except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors[word] = str(exc)
                stats['falhas'] += 1
                if mostrar:
                    print(f'[{i}/{len(pending)}] Sem tradução para {word}: {exc}')
            if pausa > 0 and i < len(pending):
                time.sleep(pausa)
    except KeyboardInterrupt:
        if mostrar:
            print('\nInterrompido. Salvando as traduções já obtidas...')
    finally:
        escrever_dicionario(path, auto)
        write_json(root / 'dictionary-pending.json', errors)
        stats['restantes'] = len([w for w in palavras_das_historias(root)
                                  if w not in ler_dicionario(path.read_text(encoding='utf-8'))])
    if mostrar:
        print(f"Dicionário atualizado: +{stats['novas']} palavras; "
              f"{stats['restantes']} ainda sem tradução local.")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Traduz palavras novas para dictionary.js (até 3 sentidos).')
    parser.add_argument('--limite', type=int, default=0, help='Máximo de palavras nesta execução (0 = todas).')
    parser.add_argument('--pausa', type=float, default=0.8, help='Segundos entre requisições.')
    parser.add_argument('--sentidos', type=int, default=3, help='Máximo de sentidos por palavra (1–5).')
    args = parser.parse_args()
    try:
        atualizar_dicionario(limite=args.limite, pausa=max(args.pausa, 0), max_sentidos=args.sentidos)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Erro: {exc}\n')


if __name__ == '__main__':
    main()
