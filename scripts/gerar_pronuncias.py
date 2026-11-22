#!/usr/bin/env python3
"""Gera dicas de pronúncia americanas para leitores brasileiros, sem rede/API.

Fonte: CMU Pronouncing Dictionary (ARPABET, licença BSD; ver data/LICENSE-CMUDICT.txt).
As dicas são APROXIMAÇÕES, não fonética exata. Casos ambíguos e não cadastrados
não são inventados; os MP3 americanos continuam sendo a fonte principal.

Uso:
    python scripts/gerar_pronuncias.py
    python scripts/gerar_pronuncias.py --palavra value

O empacotador usa build_data() diretamente, sem manter cópias desnecessárias.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CMU = Path(__file__).resolve().parent / 'data' / 'cmudict.dict.gz'
TOKEN = re.compile(r"[a-z]+(?:['’][a-z]+)*", re.I)
VOWELS = frozenset(('AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER', 'EY', 'IH', 'IY', 'OW', 'OY', 'UH', 'UW'))

# Independently written Brazilian learner respelling, not copied from IPA Translator.
VOWEL_SPELLING = {
    'AA': ('a', 'Á'), 'AE': ('é', 'É'), 'AH': ('â', 'Â'),
    'AO': ('ó', 'Ó'), 'AW': ('au', 'ÁU'), 'AY': ('ai', 'ÁI'),
    'EH': ('é', 'É'), 'ER': ('âr', 'ÂR'), 'EY': ('ei', 'ÊI'),
    'IH': ('i', 'Í'), 'IY': ('i', 'Í'), 'OW': ('ou', 'ÔU'),
    'OY': ('oi', 'ÓI'), 'UH': ('u', 'Ú'), 'UW': ('u', 'Ú'),
}
CONSONANTS = {
    'B': 'b', 'CH': 'tch', 'D': 'd', 'DH': 'd', 'F': 'f',
    'G': 'g', 'HH': 'h', 'JH': 'dj', 'K': 'k', 'L': 'l',
    'M': 'm', 'N': 'n', 'NG': 'ng', 'P': 'p', 'R': 'r',
    'S': 's', 'SH': 'sh', 'T': 't', 'TH': 's', 'V': 'v',
    'W': 'u', 'Y': 'i', 'Z': 'z', 'ZH': 'j',
}
# Common legal English syllable onsets (ARPABET phones, not spelling).
ONSETS = {
    ('P','R'), ('P','L'), ('B','R'), ('B','L'), ('T','R'), ('D','R'),
    ('K','R'), ('K','L'), ('G','R'), ('G','L'), ('F','R'), ('F','L'),
    ('S','P'), ('S','T'), ('S','K'), ('S','L'), ('S','M'), ('S','N'),
    ('S','W'), ('TH','R'), ('SH','R'), ('CH','R'), ('S','T','R'),
    ('S','K','R'), ('S','P','R'), ('S','P','L'), ('K','W'), ('G','W'),
}
# Lexemes whose distinct readings can change the meaning or grammar; we need
# sentence-level analysis to disambiguate them, so do not guess.
HETERONYMS = frozenset({
    'read', 'reads', 'reading', 'lead', 'leads', 'live', 'lives',
    'wind', 'winds', 'wound', 'tear', 'tears', 'bow', 'bows',
    'bass', 'close', 'closer', 'minute', 'object', 'objects',
    'record', 'records', 'present', 'presents', 'project',
    'produce', 'refuse', 'desert', 'content', 'contract',
    'conduct', 'conflict', 'address', 'subject', 'permit',
    'suspect', 'digest', 'resume', 'separate', 'use', 'used',
})
# Small, human-reviewed overrides for unintuitive reduction/assimilation.
OVERRIDES = {
    'value': 'VÉL-iu',
    'decide': 'di-SÁID',
    'intention': 'in-TÉN-shãn',
    'beautiful': 'BIÚ-ti-fâl',
    'computer': 'câm-PIÚ-ter',
}


def word_tokens(root: Path) -> set[str]:
    catalog = json.loads((root / 'catalog.json').read_text(encoding='utf-8'))
    result: set[str] = set()
    for pack in catalog['packs']:
        data = json.loads((root / pack['file']).read_text(encoding='utf-8'))
        for story in data['stories']:
            result.update(token.group(0).lower().replace('’', "'")
                          for token in TOKEN.finditer(story['text']))
    return result


def cmu_lookup(wanted: set[str], dictionary_file: Path = CMU) -> dict[str, list[list[str]]]:
    """Scans one gzip file, retaining only vocabulary used in current stories."""
    if not dictionary_file.is_file():
        raise FileNotFoundError(f'CMUdict não encontrado: {dictionary_file}')
    result: dict[str, list[list[str]]] = {}
    with gzip.open(dictionary_file, 'rt', encoding='utf-8') as file:
        for line in file:
            text = line.strip()
            if not text or text.startswith(';;;') or ' ' not in text:
                continue
            word, phones = text.split(None, 1)
            # CMU variants use word(2), word(3), etc. The distributed dictionary
            # also contains accent-variant pronunciations without parenthesized names.
            normalized = re.sub(r'\(\d+\)$', '', word.lower())
            if normalized in wanted:
                result.setdefault(normalized, []).append(phones.split())
    return result


def ambiguous(readings: list[list[str]]) -> bool:
    """Do not pick arbitrary dictionary entries with distinct vowel readings."""
    distinct = set()
    for pron in readings:
        distinct.add(tuple(re.sub(r'\d', '', phone) for phone in pron))
    # Mere stress variants of the same sequence are fine; different phonemes aren't.
    return len(distinct) > 1


def syllabify(phones: list[str]) -> list[list[str]]:
    """Split on vowel nuclei with a conservative English maximal-onset rule."""
    bases = [re.sub(r'\d', '', p) for p in phones]
    nuclei = [i for i, p in enumerate(bases) if p in VOWELS]
    if not nuclei:
        return []
    groups = []
    start = 0
    for i, current in enumerate(nuclei):
        if i == len(nuclei) - 1:
            groups.append(phones[start:])
            break
        next_vowel = nuclei[i + 1]
        between = bases[current + 1: next_vowel]
        # Between vowels, use the longest plausible onset at the next vowel.
        move = 0
        for take in range(min(len(between), 3), 0, -1):
            onset = tuple(between[-take:])
            if take == 1 or onset in ONSETS:
                move = take
                break
        boundary = next_vowel - move
        if boundary <= current:
            boundary = current + 1
        groups.append(phones[start:boundary]); start = boundary
    return groups


def respell(phones: list[str]) -> str | None:
    syllables = syllabify(phones)
    if not syllables:
        return None
    has_primary = any(p.endswith('1') for p in phones)
    output = []
    for syl in syllables:
        major = any(p.endswith('1') for p in syl)
        # Some names only have a secondary stress; represent it if there's no 1.
        if not has_primary:
            major = any(p.endswith('2') for p in syl)
        rendered = []
        for item in syl:
            plain = re.sub(r'\d', '', item)
            if plain in VOWELS:
                written = VOWEL_SPELLING[plain][int(major)]
            else:
                written = CONSONANTS.get(plain)
                if written is None:
                    return None
            rendered.append(written)
        text = ''.join(rendered)
        if major:
            text = text.upper()
        output.append(text)
    return '-'.join(output)


def build_data(root: Path = ROOT, dictionary_file: Path = CMU) -> dict:
    wanted = word_tokens(root)
    found = cmu_lookup(wanted, dictionary_file)
    available = {}
    uncertain = []
    for word in sorted(wanted):
        pronunciations = found.get(word, [])
        if not pronunciations:
            uncertain.append(word)
            continue
        # Do not override genuinely different dictionary readings: context required.
        if word in HETERONYMS and ambiguous(pronunciations):
            uncertain.append(word)
            continue
        value = OVERRIDES.get(word) or respell(pronunciations[0])
        if value:
            available[word] = value
        else:
            uncertain.append(word)
    return {
        'version': 1, 'locale': 'en-US', 'method': 'cmudict-approx-pt-BR',
        'words': available, 'uncertain': uncertain,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Dicas de pronúncia aproximadas em português (100% offline).')
    parser.add_argument('--palavra', '--word', type=str, default='', help='Testa uma palavra do CMUdict.')
    args = parser.parse_args()
    if args.palavra:
        wanted = {args.palavra.lower()}
        readings = cmu_lookup(wanted).get(args.palavra.lower(), [])
        print(args.palavra, '→', ('pronúncia dependente de contexto' if args.palavra.lower() in HETERONYMS and ambiguous(readings)
              else OVERRIDES.get(args.palavra.lower()) or (respell(readings[0]) if readings else 'não encontrada')))
        return 0
    data = build_data()
    print(f'Pronúncias en-US: {len(data["words"])} palavras; '
          f'{len(data["uncertain"])} sem representação segura.')
    print('As dicas são aproximações; o áudio deve ser a referência principal.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
