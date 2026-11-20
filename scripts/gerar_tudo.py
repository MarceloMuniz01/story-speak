#!/usr/bin/env python3
"""Gera ou completa os MP3 das histórias, frases e palavras com um único comando.

Examples:
    python scripts/gerar_tudo.py --pack everyday --voice andrew
    python scripts/gerar_tudo.py --voice andrew --status

By default --limit is 0 (no limit). Existing valid MP3s are never regenerated.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from audio_common import (
    ROOT, TTS, VOICES, WORD_PATTERN, load_packs, load_metadata,
    mp3_valid, norm, sentences, sha, synthesize, rebuild_index, read_json, write_json,
)


def pack_ids() -> list[str]:
    import json
    catalog = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
    return [pack['id'] for pack in catalog['packs']]


def collect(selected: set[str], voice_slug: str) -> list[tuple[str, Path, str]]:
    """A single source of truth for the files that each pack needs.

    The sentence segmentation and deduplication mirror audioItems() in app.js:
    word filenames are lowercase, sentences keep their original text and order.
    """
    stories = list(load_packs(selected))
    if not stories:
        raise ValueError('Nenhuma história encontrada nos packs solicitados.')
    tasks: list[tuple[str, Path, str]] = []
    words = set()
    for pack_id, story in stories:
        text = story['text'].strip()
        base = TTS / voice_slug / 'packs' / pack_id / story['id']
        tasks.append(('histórias', base / 'full.mp3', text))
        parts = [s for para in re.split(r'\n\s*\n', text) for s in sentences(para)]
        tasks.extend(('frases', base / f's{i:04d}.mp3', sentence)
                     for i, sentence in enumerate(parts, 1))
        words.update(norm(match.group()) for match in WORD_PATTERN.finditer(text))
    tasks.extend(('palavras', TTS / voice_slug / f'{word}.mp3', word)
                 for word in sorted(words))
    # A word repeated across several stories is one MP3, not multiple requests.
    return tasks


def audit_tasks(tasks: list[tuple[str, Path, str]], voice: str, force: bool):
    """Distinguish absent files from locally present but outdated/unindexed files."""
    hashes = load_metadata()
    index = read_json(TTS / 'index.json')
    recorded = index.get('voices', {}).get(voice, {})
    indexed_paths = set(recorded.get('words', {}).values())
    for story in recorded.get('stories', {}).values():
        if story.get('full'):
            indexed_paths.add(story['full']['path'])
        indexed_paths.update(piece['path'] for piece in story.get('sentences', []))
    waiting = []
    missing_examples = []
    counts: dict[str, Counter] = {label: Counter() for label in ('histórias', 'frases', 'palavras')}
    for label, path, text in tasks:
        key = path.relative_to(ROOT).as_posix()
        physically_ok = mp3_valid(path)
        verified = physically_ok and hashes.get(key) == sha(text, voice)
        if verified:
            category = 'ready'
        elif not physically_ok:
            category = 'missing'
        elif key not in hashes:
            category = 'unindexed'
        else:
            category = 'stale'
        counts[label][category] += 1
        counts[label]['total'] += 1
        if verified and key in indexed_paths:
            counts[label]['published'] += 1
        if not verified:
            missing_examples.append((category, key))
        if force or not verified:
            waiting.append((path, text))
    return waiting, counts, missing_examples


def adopt_existing_audio(tasks: list[tuple[str, Path, str]], voice: str) -> tuple[int, int, int, int]:
    """Opt-in: trust existing MP3 filenames for records lacking a fingerprint.

    This validates a basic MP3 signature/size, NOT spoken content or voice.
    Mismatching fingerprints are never overwritten.
    """
    saved = load_metadata()
    adopted = unchanged = conflicts = invalid = 0
    for _label, path, spoken_text in tasks:
        key = path.relative_to(ROOT).as_posix()
        if not mp3_valid(path):
            invalid += 1
            continue
        fingerprint = sha(spoken_text, voice)
        if saved.get(key) == fingerprint:
            unchanged += 1
        elif key in saved:
            conflicts += 1
        else:
            saved[key] = fingerprint
            adopted += 1
    if adopted:
        write_json(TTS / 'generated.json', saved)
    rebuild_index()
    return adopted, unchanged, conflicts, invalid


def main():
    parser = argparse.ArgumentParser(
        description='Gera todos os MP3 (histórias, frases e palavras) com retomada automática.')
    parser.add_argument('--pack', action='append', choices=pack_ids(),
                        help='Pack desejado. Repetir para vários; omitido = todos.')
    parser.add_argument('--voice', choices=VOICES, default='andrew')
    parser.add_argument('--status', action='store_true', help='Somente relatório do que falta; sem acessar TTS.')
    parser.add_argument('--show-missing', type=int, default=0, metavar='N',
                        help='Lista até N MP3 pendentes (0 = não listar).')
    parser.add_argument('--adopt-existing', '--aproveitar-existentes', action='store_true',
                        help='Registra MP3 já existentes SEM hash, sem regenerar; confie apenas nos próprios arquivos.')
    parser.add_argument('--reindex', action='store_true',
                        help='Atualiza somente tts/index.json a partir dos MP3 já validados; não gera novos arquivos.')
    parser.add_argument('--dry-run', action='store_true', help='Exibe arquivos pendentes sem gerar.')
    parser.add_argument('--limit', type=int, default=0,
                        help='Máximo de MP3 novos nesta rodada; 0 = TODOS (padrão).')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--delay', type=float, default=0.8)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=50)
    parser.add_argument('--force', action='store_true', help='Recria MP3 válidos também; não usar na rotina normal.')
    args = parser.parse_args()
    if not 0.5 <= args.delay <= 60 or args.limit < 0 or not 0 <= args.retries <= 4 or not 1 <= args.workers <= 3 or args.timeout < 10 or args.show_missing < 0:
        parser.error('--delay 0.5–60, --workers 1–3, --retries 0–4, --limit >= 0, --show-missing >= 0, --timeout >= 10')
    voice, slug = VOICES[args.voice]
    selected = set(args.pack or pack_ids())
    tasks = collect(selected, slug)
    pending, counts, examples = audit_tasks(tasks, voice, args.force)
    print(f'Voz: {args.voice} | Coleções: {", ".join(sorted(selected))}', flush=True)
    print(f'{"Tipo":<14} {"Validados":>10} {"Sem hash":>10} {"Divergentes":>12} {"Ausentes":>9} {"Total":>7}')
    for label in ('palavras', 'frases', 'histórias'):
        c = counts[label]
        print(f'{label:<14} {c["ready"]:>10} {c["unindexed"]:>10} {c["stale"]:>12} {c["missing"]:>9} {c["total"]:>7}')
    print(f'TOTAL          {sum(c["ready"] for c in counts.values()):>10} '
          f'{sum(c["unindexed"] for c in counts.values()):>10} '
          f'{sum(c["stale"] for c in counts.values()):>12} '
          f'{sum(c["missing"] for c in counts.values()):>9} {len(tasks):>7}', flush=True)
    published = sum(c['published'] for c in counts.values())
    verified = sum(c['ready'] for c in counts.values())
    print(f'Índice atual: {published}/{len(tasks)} arquivos válidos listados em tts/index.json.', flush=True)
    print('Sem hash: arquivo existe sem registro. Divergentes: existe registro de outro texto/voz.', flush=True)
    if verified > published:
        print('AVISO: índice desatualizado! Use --reindex e publique tts/index.json novamente.', flush=True)
    if args.show_missing:
        for kind, path in examples[:args.show_missing]:
            print(f'  [{kind}] {path}')
        if len(examples) > args.show_missing:
            print(f'  ... e mais {len(examples) - args.show_missing} itens.')
    if args.adopt_existing:
        if args.force:
            parser.error('--adopt-existing não pode ser combinado com --force')
        adopted, unchanged, conflicts, invalid = adopt_existing_audio(tasks, voice)
        print(f'Adotados sem API: {adopted} | já corretos: {unchanged} | '
              f'hash divergente: {conflicts} | MP3 ausente/inválido: {invalid}.', flush=True)
        if conflicts:
            print('Hash divergente indica possível mudança de texto/voz: não foi adotado; gere novamente estes itens.')
        print('ATENÇÃO: somente o cabeçalho/tamanho foi verificado; confira a voz e o conteúdo desses MP3.')
        print('Índice tts/index.json atualizado. Publique-o junto aos MP3 no GitHub Pages.')
        return
    if args.reindex:
        rebuild_index()
        print('tts/index.json reconstruído sem chamar a API. Publique esse JSON e os MP3 no site.')
        return
    if args.status:
        print('Somente consulta: nenhum arquivo foi alterado.')
        return
    if not pending and not args.force:
        # Rebuild in case the file index needs refreshing; no network call.
        rebuild_index()
        print('Pack completo! Índice tts/index.json atualizado.')
        return
    print(f'Gerando {min(len(pending), args.limit) if args.limit else len(pending)} de '
          f'{len(pending)} MP3 pendentes. Arquivos já existentes serão preservados.', flush=True)
    try:
        asyncio.run(synthesize(
            [(path, text) for path, text in pending], voice=voice,
            delay=args.delay, workers=args.workers, retries=args.retries,
            timeout=args.timeout, force=args.force, max_items=args.limit,
            dry_run=args.dry_run, group='pack'))
    except KeyboardInterrupt:
        print('\nInterrompido. Execute o mesmo comando para completar os MP3 restantes.', flush=True)


if __name__ == '__main__':
    main()
