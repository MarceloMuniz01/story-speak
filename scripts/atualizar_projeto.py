#!/usr/bin/env python3
"""Atualiza o StorySpeak com um ZIP baixado no Android sem tocar em tts/.

Uso: python scripts/atualizar_projeto.py [arquivo.zip]
     python scripts/atualizar_projeto.py --dry-run

Por padrão também protege histórias e dicionário: catalog.json, packs/ e dictionary.js.
Use --sobrescrever-historias para atualizar esses arquivos pelo ZIP.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def localizar_zip(arquivo: str | None, downloads: Path | None = None) -> Path:
    if arquivo:
        result = Path(arquivo).expanduser()
        if not result.is_file():
            raise FileNotFoundError(f'ZIP não encontrado: {result}')
        return result.resolve()
    if downloads:
        dirs = [downloads]
    else:
        dirs = [Path('/sdcard/Download'), Path.home() / 'storage' / 'downloads']
    candidates = [f for d in dirs if d.is_dir() for f in d.glob('*.zip') if f.is_file()]
    # Se houver mais de um arquivo, preferir versões do StorySpeak.
    project_zips = [f for f in candidates if 'storyspeak' in f.name.lower() or 'story-speak' in f.name.lower()]
    selection = project_zips or candidates
    if not selection:
        raise FileNotFoundError('Não encontrei ZIP em /sdcard/Download. Execute termux-setup-storage ou informe o arquivo.')
    return max(selection, key=lambda f: f.stat().st_mtime).resolve()


def caminho_seguro(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename
    if ('\\' in name or name.startswith('/') or name.startswith('~') or
            not name or '\x00' in name):
        raise ValueError(f'Caminho inseguro no ZIP: {name!r}')
    parts = PurePosixPath(name).parts
    if any(p in ('..', '.') or ':' in p for p in parts):
        raise ValueError(f'Caminho inseguro no ZIP: {name!r}')
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f'Link simbólico no ZIP não permitido: {name!r}')
    return PurePosixPath(*parts)


def arquivos_do_zip(zf: zipfile.ZipFile, sobrescrever_historias: bool):
    entries = [(caminho_seguro(info), info) for info in zf.infolist() if not info.is_dir()]
    if not entries:
        raise ValueError('O ZIP não contém arquivos.')
    # Aceita um ZIP criado com pasta contêiner ou arquivos na raiz.
    first = {path.parts[0] for path, _ in entries}
    prefix = next(iter(first)) if len(first) == 1 and all(len(path.parts) > 1 for path, _ in entries) else None
    selected = []
    ignored = []
    seen = set()
    for path, info in entries:
        if prefix:
            path = PurePosixPath(*path.parts[1:])
        parts = path.parts
        if (parts[0] in {'tts', '.git', '.venv', 'venv', '__pycache__', 'node_modules'}
                or any(p.startswith('.') or p == '__pycache__' for p in parts)
                or (not sobrescrever_historias and
                    (parts[0] == 'packs' or path.as_posix() in {'catalog.json', 'dictionary.js'}))):
            ignored.append(path.as_posix())
            continue
        if path.as_posix() in seen:
            raise ValueError(f'Arquivo duplicado no ZIP: {path}')
        seen.add(path.as_posix())
        if info.file_size > 30 * 1024 * 1024:
            raise ValueError(f'Arquivo individual grande demais: {path}')
        selected.append((path, info))
    if sum(i.file_size for _, i in selected) > 150 * 1024 * 1024:
        raise ValueError('O ZIP ultrapassa o limite seguro de extração (150 MB, sem tts/).')
    return selected, ignored


def atualizar(arquivo: Path, destino: Path, *, dry_run=False, sobrescrever_historias=False) -> dict:
    destino = destino.resolve()
    if not (destino / 'index.html').is_file():
        raise ValueError(f'A pasta atual não parece ser o StorySpeak: {destino}')
    with zipfile.ZipFile(arquivo) as zf:
        selected, ignored = arquivos_do_zip(zf, sobrescrever_historias)
        if not any(str(name) == 'app.js' for name, _ in selected):
            raise ValueError('O ZIP não contém app.js; confirme que é o ZIP completo do projeto.')
        if not dry_run:
            with tempfile.TemporaryDirectory(prefix='.storyspeak-update-', dir=destino) as temp:
                staging = Path(temp)
                for path, info in selected:
                    target = staging.joinpath(*path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output)
                for path, _ in selected:
                    target = destino.joinpath(*path.parts)
                    if target.is_symlink():
                        raise ValueError(f'Destino contém link simbólico: {target}')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staging.joinpath(*path.parts), target)
    return {'copiados': len(selected), 'ignorados': len(ignored), 'nomes': [str(p) for p, _ in selected]}


def main():
    parser = argparse.ArgumentParser(description='Atualiza o site a partir de ZIP sem modificar tts/.')
    parser.add_argument('zip', nargs='?', help='Arquivo ZIP opcional (padrão: o StorySpeak mais recente em /sdcard/Download)')
    parser.add_argument('--dry-run', action='store_true', help='Mostra os arquivos que seriam copiados.')
    parser.add_argument('--sobrescrever-historias', action='store_true',
                        help='Também substitui catalog.json e packs/. Cuidado: pode apagar histórias criadas localmente.')
    args = parser.parse_args()
    try:
        filename = localizar_zip(args.zip)
        result = atualizar(filename, Path.cwd(), dry_run=args.dry_run,
                            sobrescrever_historias=args.sobrescrever_historias)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Erro: {exc}\n')
    print(f"ZIP: {filename}")
    print(f"{'Simulação' if args.dry_run else 'Atualização concluída'}: "
          f"{result['copiados']} arquivo(s) selecionados; {result['ignorados']} ignorados.")
    if args.dry_run:
        for name in result['nomes']:
            print('  ', name)
    print('A pasta tts/ foi preservada. Histórias e dictionary.js também foram preservados'
          if not args.sobrescrever_historias else 'A pasta tts/ foi preservada.')


if __name__ == '__main__':
    main()
