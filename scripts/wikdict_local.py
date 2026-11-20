#!/usr/bin/env python3
"""Leitor local do WikDict en-pt (StarDict), sem contas e sem API.

Download oficial único: https://download.wikdict.com/dictionaries/stardict/wikdict-en-pt.zip
Dados: WikDict / Wiktionary / DBnary, CC BY-SA. Confira ATTRIBUTION-WIKDICT.md.
"""
from __future__ import annotations

import gzip
import html
import re
import struct
import unicodedata
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile, BadZipFile

URL = 'https://download.wikdict.com/dictionaries/stardict/wikdict-en-pt.zip'
BLOCK = {'div', 'p', 'li', 'br', 'ol', 'ul', 'dd', 'dt', 'h1', 'h2', 'h3', 'tr', 'td', 'hr'}
LABELS = {'noun', 'verb', 'adjective', 'adverb', 'pronoun', 'preposition', 'conjunction',
          'article', 'interjection', 'n', 'v', 'adj', 'adv', 'f', 'm', 'pl', 'sing',
          'substantivo', 'verbo', 'adjetivo', 'advérbio', 'masculino', 'feminino',
          'transitive', 'intransitive', 'plural', 'singular', 'english', 'portuguese'}


class _TextLines(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.disabled = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.disabled += 1
        elif tag in BLOCK and not self.disabled:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.disabled = max(0, self.disabled - 1)
        elif tag in BLOCK and not self.disabled:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.disabled:
            self.parts.append(data)


def _valid_pt(text: str, source: str) -> bool:
    text = text.strip()
    if not (1 <= len(text) <= 65 and len(text.split()) <= 7):
        return False
    if text.casefold().strip('.:') in LABELS or text.startswith(('http', 'www.')):
        return False
    if re.search(r'[<>\[\]{}=\\/0-9]', text):
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    if any(ch.isalpha() and not unicodedata.name(ch, '').startswith('LATIN') for ch in text):
        return False
    if text.casefold() in {'...', 'see also', 'see', 'cf'}:
        return False
    return True


def parse_meanings(raw: bytes, source: str, *, max_meanings: int = 3, fmt: str = 'h') -> list[str]:
    """Extrai candidatos curtos sem presumir que qualquer linha longa é tradução.

    StarDict WikDict fornece HTML (h), outros conjuntos podem usar texto (m).
    Não tenta traduzir exemplos: evita guardar definições em inglês por acidente.
    """
    if not raw:
        return []
    if not fmt and raw[:1] in (b'h', b'm'):
        fmt, raw = raw[:1].decode(), raw[1:]
    text = raw.decode('utf-8', errors='replace').strip('\x00')
    parser = _TextLines()
    if fmt == 'h' or '<' in text:
        parser.feed(text)
        text = ''.join(parser.parts)
    text = html.unescape(text).replace('\xa0', ' ').replace('\x00', '\n')
    results = []
    used = set()
    for line in text.splitlines():
        line = re.sub(r'\s+', ' ', line).strip(' \t\r•·:\u2014')
        # Uma linha frequentemente contém sinônimos separados por vírgulas ou ;
        for token in re.split(r'\s*[,;]\s*', line):
            candidate = re.sub(r'\([^()]{1,45}\)', '', token).strip(' .;,:\t\r–—')
            candidate = re.sub(r'^\s*(?:\d+\.?|[-•])\s+', '', candidate).strip()
            if not _valid_pt(candidate, source):
                continue
            key = candidate.casefold()
            if key not in used:
                used.add(key)
                results.append(candidate.lower())
            if len(results) >= max_meanings + 2:
                break
        if len(results) >= max_meanings + 2:
            break
    non_same = [value for value in results if value.casefold() != source.casefold()]
    return (non_same or results)[:max_meanings]


def download_once(path: Path, *, timeout: int = 45) -> None:
    """Baixa arquivo somente se ausente; grava de maneira atômica e valida ZIP."""
    if path.exists() and path.stat().st_size > 100_000:
        try:
            with ZipFile(path) as archive:
                if any(x.endswith('.idx') for x in archive.namelist()):
                    return
        except BadZipFile:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    try:
        print('Baixando dicionário WikDict en-pt (uma única vez, cerca de 3 MB)...', flush=True)
        request = urllib.request.Request(URL, headers={'User-Agent': 'StorySpeak/1.0'})
        with urllib.request.urlopen(request, timeout=timeout) as stream, temp.open('wb') as output:
            total = 0
            while chunk := stream.read(64 * 1024):
                total += len(chunk)
                if total > 35_000_000:
                    raise ValueError('Arquivo inesperadamente grande')
                output.write(chunk)
        with ZipFile(temp) as archive:
            if not any(x.endswith('.idx') for x in archive.namelist()):
                raise ValueError('ZIP sem índice StarDict (.idx)')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _members(archive: ZipFile) -> tuple[bytes, bytes, dict]:
    names = archive.namelist()
    ifos = [name for name in names if name.lower().endswith('.ifo')]
    for ifo in ifos:
        stem = ifo[:-4]
        idx = next((x for x in (stem + '.idx', stem + '.idx.gz') if x in names), None)
        data = next((x for x in (stem + '.dict', stem + '.dict.dz') if x in names), None)
        if not idx or not data:
            continue
        attrs = {}
        for row in archive.read(ifo).decode('utf-8', errors='replace').splitlines():
            if '=' in row:
                key, value = row.split('=', 1)
                attrs[key.strip()] = value.strip()
        index = archive.read(idx)
        dictionary = archive.read(data)
        if idx.endswith('.gz'):
            index = gzip.decompress(index)
        if data.endswith('.dz'):
            dictionary = gzip.decompress(dictionary)
        return index, dictionary, attrs
    raise ValueError('ZIP inválido: .ifo, .idx e .dict/.dict.dz devem pertencer ao mesmo dicionário')


def lookup(path: Path, words: set[str], max_meanings: int = 3) -> dict[str, str]:
    """Consulta múltiplas palavras de uma vez, sem conexão, sem bibliotecas externas."""
    if not path.exists():
        raise FileNotFoundError(f'Dicionário não encontrado: {path}')
    target = {w.casefold().replace('’', "'") for w in words}
    if not target:
        return {}
    with ZipFile(path) as archive:
        idx, payload, attrs = _members(archive)
    offsetbits = int(attrs.get('idxoffsetbits', '32'))
    if offsetbits not in (32, 64):
        raise ValueError('Índice StarDict não suportado')
    rec_size = 8 if offsetbits == 32 else 12
    fmt = '>II' if offsetbits == 32 else '>QI'
    typ = attrs.get('sametypesequence', '')
    output: dict[str, list[str]] = {}
    i = 0
    while i < len(idx):
        end = idx.find(b'\x00', i)
        if end < 0 or end + 1 + rec_size > len(idx):
            raise ValueError('Índice StarDict incompleto ou corrompido')
        word = idx[i:end].decode('utf-8', errors='replace').casefold().replace('’', "'")
        pos, length = struct.unpack_from(fmt, idx, end + 1)
        i = end + 1 + rec_size
        if word not in target or length <= 0 or pos + length > len(payload):
            continue
        meanings = parse_meanings(payload[pos:pos + length], word,
                                  max_meanings=max_meanings, fmt=typ)
        if meanings:
            values = output.setdefault(word, [])
            for meaning in meanings:
                if meaning not in values and len(values) < max_meanings:
                    values.append(meaning)
    return {word: '; '.join(values) for word, values in output.items() if values}
