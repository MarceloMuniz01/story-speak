#!/usr/bin/env python3
"""Build a static multi-voice offline reader for Surge / GitHub Pages.

Only complete (voice, collection) pairs are published. Words are deduplicated
within each voice. All ZIPs are validated before replacing dist/ atomically.

    python scripts/gerar_tudo.py --voice ava --pack animes
    python scripts/empacotar_offline.py
    surge dist/ story-speak.surge.sh
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from audio_common import ROOT, TTS, VOICES, load_metadata, mp3_valid, rebuild_index, sha, write_json
from gerar_tudo import collect
from gerar_pronuncias import build_data as build_pronunciations

PUBLIC_FILES = (
    'index.html', 'app.js', 'styles.css', 'dictionary.js', 'catalog.json',
    'manifest.webmanifest', 'sw.js', 'tts/index.json',
    'vendor/jszip.min.js', 'assets/icon-192.png', 'assets/icon-512.png',
)
MAX_ZIP_FILE = 512 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def archive(path: Path, entries: list[tuple[Path, str, bool]]) -> dict:
    """MP3 => STORE, JSON => DEFLATE; verify CRC, checksum and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(tmp, 'w', allowZip64=True) as output:
            for source, target, is_json in entries:
                if source.stat().st_size > MAX_ZIP_FILE:
                    raise ValueError(f'Arquivo muito grande: {source}')
                output.write(source, arcname=target,
                             compress_type=zipfile.ZIP_DEFLATED if is_json else zipfile.ZIP_STORED,
                             compresslevel=6 if is_json else None)
        with zipfile.ZipFile(tmp) as check:
            if len(set(check.namelist())) != len(entries):
                raise RuntimeError('Entradas duplicadas no ZIP.')
            bad = check.testzip()
            if bad:
                raise RuntimeError(f'Arquivo corrompido no ZIP: {bad}')
        tmp.replace(path)
        return {
            'url': path.relative_to(path.parent.parent).as_posix(),
            'sha256': sha256_file(path), 'bytes': path.stat().st_size,
            'files': len(entries),
        }
    finally:
        tmp.unlink(missing_ok=True)


def _verified_tasks(root: Path, pack_id: str, voice: str, slug: str, hashes: dict):
    """Return all items iff this exact voice has all word, sentence and full MP3s."""
    tasks = collect({pack_id}, slug)
    missing = []
    for _kind, file, text in tasks:
        relative = file.relative_to(root).as_posix()
        if not mp3_valid(file) or hashes.get(relative) != sha(text, voice):
            missing.append(relative)
    return tasks if not missing else [], missing


def _catalog(root: Path):
    catalog = json.loads((root / 'catalog.json').read_text(encoding='utf-8'))
    packs = catalog.get('packs')
    if not isinstance(packs, list) or not packs:
        raise ValueError('Catálogo sem categorias.')
    ids = [pack['id'] for pack in packs]
    if len(ids) != len(set(ids)):
        raise ValueError('Categorias duplicadas no catalog.json.')
    for pack in packs:
        pid = pack['id']
        if not pid.replace('-', '').replace('_', '').isalnum() or pid in ('words', 'manifest'):
            raise ValueError(f'ID de categoria inválido: {pid}')
        source = root / pack['file']
        if not source.is_file():
            raise FileNotFoundError(f'Histórias não encontradas: {source}')
        if not source.resolve().is_relative_to((root / 'packs').resolve()):
            raise ValueError(f'Pack fora de packs/: {source}')
        data = json.loads(source.read_text(encoding='utf-8'))
        if data.get('id') != pid or not isinstance(data.get('stories'), list):
            raise ValueError(f'Pack inválido: {source}')
    return packs


def build(root: Path, out: Path, voices: list[str] | str | None = None,
          strict: bool = False) -> dict:
    """Discover available voices from validated MP3s, publish complete ZIPs only.

    Other voices may cover only selected categories: they appear only on those
    categories. One voice needs one words-<voice>.zip for its published packs.
    """
    packs = _catalog(root)
    if voices is None:
        voices = list(VOICES)
    elif isinstance(voices, str):
        voices = [voices]
    for short in voices:
        if short not in VOICES:
            raise ValueError(f'Voz não cadastrada: {short}')

    hashes = load_metadata()
    complete = {}
    skipped = {}
    for short in voices:
        voice, slug = VOICES[short]
        available = {}
        for pack in packs:
            tasks, missing = _verified_tasks(root, pack['id'], voice, slug, hashes)
            if tasks:
                available[pack['id']] = tasks
            else:
                skipped[(short, pack['id'])] = len(missing)
        if available:
            complete[short] = available

    if strict and skipped:
        details = ', '.join(f'{voice}/{pack}: {count}' for (voice, pack), count in skipped.items())
        raise ValueError('Faltam MP3 para as vozes solicitadas: ' + details)
    if not complete:
        detail = ', '.join(f'{v}/{p}: {n} ausentes' for (v, p), n in list(skipped.items())[:8])
        raise ValueError('Nenhuma combinação de voz + coleção tem todos os MP3 validados. '
                         f'{detail}. Gere os áudios com scripts/gerar_tudo.py.')

    # No user files modified if validation fails. Index must reflect current fingerprints.
    index = rebuild_index()
    for short in complete:
        voice = VOICES[short][0]
        if voice not in index['voices']:
            raise ValueError(f'Índice de áudio não contém a voz {voice}.')

    target = out.resolve()
    base = root.resolve()
    if target in (base, base.parent) or (
        target.is_relative_to(base) and target.relative_to(base).parts[0] != 'dist'
    ):
        raise ValueError('Use dist/ para saída, sem sobrescrever os fontes.')
    if out.exists() and not out.is_dir():
        raise ValueError(f'Saída não é uma pasta: {out}')
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.storyspeak-build-', dir=out.parent))
    previous = None
    try:
        output_archives = staging / 'archives'
        output_archives.mkdir(parents=True)
        for name in PUBLIC_FILES:
            source = root / name
            if not source.is_file():
                raise FileNotFoundError(f'Arquivo do site ausente: {name}')
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        # One small phonetic glossary per build; shared by the American voice ZIPs.
        # British voices do not receive American-specific pronunciation hints.
        hints = None
        if any(VOICES[short][0].startswith('en-US-') for short in complete):
            hints = staging / '_build' / 'pronunciations-en-US.json'
            write_json(hints, build_pronunciations(root))
        manifest = {'version': 2, 'defaultVoice': '', 'voices': {}}
        for short, available in complete.items():
            voice, slug = VOICES[short]
            # Dedupe word MP3 across all published collections for this voice.
            words = {}
            for tasks in available.values():
                for kind, file, _ in tasks:
                    if kind == 'palavras':
                        rel = file.relative_to(root).as_posix()
                        words[rel] = (file, rel, False)
            word_files = [words[key] for key in sorted(words)]
            if hints is not None and voice.startswith('en-US-'):
                word_files.append((hints, 'pronunciations-en-US.json', True))
            entry = {
                'name': short.title(), 'locale': '-'.join(voice.split('-')[:2]),
                'short': short, 'packs': {},
                'words': archive(output_archives / f'words-{short}.zip', word_files),
            }
            for pack in packs:
                pid = pack['id']
                if pid not in available:
                    continue
                source = root / pack['file']
                files = [(file, file.relative_to(root).as_posix(), False)
                         for kind, file, _ in available[pid] if kind != 'palavras']
                meta = archive(output_archives / f'{pid}-{short}.zip',
                               [(source, pack['file'], True)] + files)
                meta['json'] = pack['file']
                meta['stories'] = len(json.loads(source.read_text(encoding='utf-8'))['stories'])
                entry['packs'][pid] = meta
            manifest['voices'][voice] = entry
        manifest['defaultVoice'] = (VOICE_DEFAULT if VOICE_DEFAULT in manifest['voices']
                                    else next(iter(manifest['voices'])))
        write_json(output_archives / 'manifest.json', manifest)
        if hints is not None:
            shutil.rmtree(hints.parent)  # Arquivo auxiliar não é publicado solto.
        if out.exists():
            previous = Path(tempfile.mkdtemp(prefix='.storyspeak-old-', dir=out.parent))
            previous.rmdir()
            out.replace(previous)
        try:
            staging.replace(out)
        except OSError:
            if previous is not None and not out.exists():
                previous.replace(out)
            raise
        if previous is not None:
            shutil.rmtree(previous)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


VOICE_DEFAULT = VOICES['andrew'][0]


def main() -> int:
    parser = argparse.ArgumentParser(description='Cria ZIPs de voz + categoria com descoberta automática.')
    parser.add_argument('--voice', '--voz', action='append', choices=VOICES, default=None,
                        help='Limita às vozes selecionadas. Repita para mais vozes. Omitir = detectar todas.')
    parser.add_argument('--strict', action='store_true',
                        help='Exige todas as categorias de cada voz selecionada (padrão: publicar apenas completas).')
    parser.add_argument('--output', default='dist', help='Pasta de publicação, padrão: dist/.')
    args = parser.parse_args()
    try:
        result = build(ROOT, ROOT / args.output, args.voice, strict=args.strict)
    except (ValueError, FileNotFoundError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        return 1
    print(f'\nStorySpeak v29 pronto em {args.output}/ — {len(result["voices"])} vozes publicadas')
    for voice, item in result['voices'].items():
        print(f'  {item["name"]} ({voice}): words-{item["short"]}.zip '
              f'({item["words"]["files"]} palavras)')
        for pack, details in item['packs'].items():
            print(f'    {pack}-{item["short"]}.zip: {details["stories"]} histórias, '
                  f'{details["bytes"] / (1024 * 1024):.1f} MiB')
    print(f'\nPublicar: surge {args.output}/ story-speak.surge.sh')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
