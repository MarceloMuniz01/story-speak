#!/usr/bin/env python3
"""Assistente interativo para criar histórias ou importar JSON para o StorySpeak.

Uso: python scripts/adicionar_historia.py
     python scripts/adicionar_historia.py --arquivo historia.json
     python scripts/adicionar_historia.py --arquivo historia.txt

Depois use: python scripts/gerar_tudo.py
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

from audio_common import ROOT, WORD_PATTERN, read_json, write_json
from atualizar_dicionario import atualizar_dicionario

LEVELS = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'^-+|-+$', '', re.sub(r'[^a-z0-9]+', '-', ascii_text))[:65].strip('-')


def pergunta(label: str, default: str = '', required=False) -> str:
    suffix = f' [{default}]' if default else ''
    while True:
        value = input(f'{label}{suffix}: ').strip() or default
        if value or not required:
            return value
        print('Este campo é obrigatório.')


def escolher_categoria(catalog: dict, entrada=input) -> tuple[dict, bool]:
    packs = catalog.get('packs', [])
    print('\nCategorias disponíveis:')
    for i, pack in enumerate(packs, 1):
        print(f'  {i}. {pack["title"]} ({pack["id"]})')
    print(f'  {len(packs)+1}. Criar nova categoria')
    while True:
        choice = entrada('Categoria (número): ').strip()
        if choice.isdigit() and 1 <= int(choice) <= len(packs) + 1:
            break
        print('Digite um número da lista.')
    if int(choice) <= len(packs):
        return packs[int(choice)-1], False
    title = pergunta('Nome da nova categoria', required=True)
    pack_id = slug(title)
    if not pack_id or any(p['id'] == pack_id for p in packs):
        raise ValueError('Nome de categoria inválido ou já existente.')
    description = pergunta('Descrição (opcional)', 'Histórias para praticar inglês')
    emoji = pergunta('Emoji (opcional)', '📚')
    return {'id': pack_id, 'title': title, 'description': description,
            'emoji': emoji, 'file': f'packs/{pack_id}.json', 'count': 0}, True


def colar_multilinhas(label: str) -> str:
    print(f'\n{label}')
    print('Cole o conteúdo. Para finalizar, digite :fim sozinho em uma linha.')
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            if not lines:
                raise ValueError('Nenhum conteúdo recebido.') from None
            break
        if line.strip() == ':fim':
            break
        lines.append(line)
    result = '\n'.join(lines).strip()
    if not result:
        raise ValueError('O conteúdo não pode ficar vazio.')
    return result


def normalizar_historia(obj: dict, used_ids: set[str], used_titles: set[str]) -> dict:
    if not isinstance(obj, dict):
        raise ValueError('O JSON deve conter um objeto de história.')
    title = obj.get('title')
    text = obj.get('text')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Cada história precisa de um título (title).')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Cada história precisa de um texto (text).')
    title = title.strip()
    if title.casefold() in used_titles:
        raise ValueError(f'Já existe uma história com este título: {title}')
    level = obj.get('level', 'B1')
    if not isinstance(level, str) or level.upper() not in LEVELS:
        raise ValueError('Nível inválido. Escolha A1, A2, B1, B2, C1 ou C2.')
    tags = obj.get('tags', [])
    if isinstance(tags, str):
        tags = tags.split(',')
    if not isinstance(tags, list) or any(not isinstance(item, str) for item in tags):
        raise ValueError('tags precisa ser uma lista de textos ou string separada por vírgulas.')
    given_id = obj.get('id')
    if given_id is not None and (not isinstance(given_id, str) or not SLUG.fullmatch(given_id)):
        raise ValueError('id deve conter apenas letras minúsculas, números e hífens.')
    base = given_id or slug(title)
    if not base:
        raise ValueError('Não consegui gerar o ID para essa história.')
    story_id = base
    if given_id and given_id in used_ids:
        raise ValueError(f'O ID {given_id} já está em uso.')
    num = 2
    while story_id in used_ids:
        story_id = f'{base}-{num}'
        num += 1
    used_ids.add(story_id)
    used_titles.add(title.casefold())
    return {
        'id': story_id,
        'title': title,
        'level': level.upper(),
        'genre': str(obj.get('genre') or 'General').strip(),
        'summary': str(obj.get('summary') or title).strip(),
        'tags': list(dict.fromkeys(t.strip().lower() for t in tags if t.strip())),
        'text': text.strip(),
    }


def preparar_historias(source: str, fmt: str) -> list[dict]:
    if fmt == 'json':
        data = json.loads(source)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and isinstance(data.get('stories'), list):
            items = data['stories']
        else:
            items = [data]
        if not items:
            raise ValueError('O JSON não contém histórias.')
        return items
    if fmt == 'txt':
        return [{
            'title': pergunta('Título da história', required=True),
            'level': pergunta('Nível (A1, A2, B1, B2, C1, C2)', 'B1'),
            'genre': pergunta('Gênero', 'General'),
            'summary': pergunta('Resumo curto', 'Texto para praticar inglês'),
            'tags': pergunta('Tags separadas por vírgula (opcional)'),
            'text': source,
        }]
    raise ValueError('Formato não reconhecido.')


def salvar_historias(pack: dict, nova_categoria: bool, items: list[dict], root: Path = ROOT) -> list[dict]:
    catalog_path = root / 'catalog.json'
    catalog = read_json(catalog_path)
    target = root / pack['file']
    if not target.resolve().is_relative_to((root / 'packs').resolve()):
        raise ValueError('Caminho de categoria inválido.')
    current = {'id': pack['id'], 'stories': []} if nova_categoria else read_json(target)
    if current.get('id') != pack['id'] or not isinstance(current.get('stories'), list):
        raise ValueError('Pack JSON inconsistente.')
    ids = {s['id'] for s in catalog.get('stories', [])}
    titles = {s['title'].casefold() for s in catalog.get('stories', [])}
    new_stories = [normalizar_historia(item, ids, titles) for item in items]
    for story in new_stories:
        current['stories'].append(story)
        words = [w.lower().replace('’', "'") for w in WORD_PATTERN.findall(story['text'])]
        catalog['stories'].append({
            'id': story['id'], 'packId': pack['id'], 'title': story['title'],
            'level': story['level'], 'genre': story['genre'], 'summary': story['summary'],
            'tags': story['tags'], 'terms': sorted(set(words)), 'words': len(words),
        })
    if nova_categoria:
        pack['count'] = len(current['stories'])
        catalog['packs'].append(pack)
    else:
        next(p for p in catalog['packs'] if p['id'] == pack['id'])['count'] = len(current['stories'])
    write_json(target, current)
    write_json(catalog_path, catalog)
    return new_stories


def main():
    parser = argparse.ArgumentParser(description='Adiciona histórias ao catálogo e aos packs do StorySpeak.')
    parser.add_argument('--arquivo', type=Path, help='Arquivo .json ou .txt em vez de colar no terminal.')
    parser.add_argument('--sem-traducao', action='store_true', help='Não consulta tradução agora; use atualizar_dicionario.py depois.')
    parser.add_argument('--sentidos', type=int, default=3, help='Máximo de sentidos por palavra (padrão: 3).')
    args = parser.parse_args()
    try:
        catalog = read_json(ROOT / 'catalog.json')
        pack, new_category = escolher_categoria(catalog)
        if args.arquivo:
            source = args.arquivo.expanduser().read_text(encoding='utf-8')
            fmt = 'json' if args.arquivo.suffix.lower() == '.json' else 'txt'
        else:
            format_choice = pergunta('Formato: 1 = colar texto, 2 = colar JSON', '1')
            if format_choice not in {'1', '2'}:
                raise ValueError('Formato inválido.')
            fmt = 'json' if format_choice == '2' else 'txt'
            source = colar_multilinhas('Cole JSON' if fmt == 'json' else 'Cole a história em inglês')
        stories = preparar_historias(source, fmt)
        # Pré-visualiza os dados antes de modificar arquivos.
        print(f'\nCategoria: {pack["title"]}')
        for story in stories:
            print(' +', story.get('title', '(sem título)'))
        if pergunta('Salvar? (s/N)', 'n').lower() not in {'s', 'sim', 'y', 'yes'}:
            print('Cancelado sem modificar os arquivos.')
            return
        saved = salvar_historias(pack, new_category, stories)
        print(f'\n{len(saved)} história(s) adicionada(s).')
        if not args.sem_traducao:
            vocabulary = {w.lower().replace('’', "'")
                          for story in saved for w in WORD_PATTERN.findall(story['text'])}
            print('\nAtualizando o dicionário com novos significados...')
            try:
                atualizar_dicionario(words=vocabulary, max_sentidos=args.sentidos)
            except (ValueError, OSError) as exc:
                print(f'Não foi possível concluir as traduções: {exc}')
                print('História salva. Tente depois: python scripts/atualizar_dicionario.py')
        else:
            print('Traduções pendentes. Execute: python scripts/atualizar_dicionario.py')
        print('Próximos passos:')
        print('  python scripts/gerar_tudo.py --voice andrew')
        print('  git add catalog.json packs/ dictionary.js tts/ && git commit -m "Novas histórias"')
        print('  git push')
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f'Erro: {exc}\n')


if __name__ == '__main__':
    main()
