"""Shared helpers for StorySpeak static audio generation.

Generation uses small, bounded concurrency; files are written atomically and
can be resumed safely after disconnection or Ctrl+C.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TTS = ROOT / 'tts'
VOICES = {
    'andrew': ('en-US-AndrewMultilingualNeural', 'andrew_en-us'),
    'ava': ('en-US-AvaNeural', 'ava_en-us'),
    'sonia': ('en-GB-SoniaNeural', 'sonia_en-gb'),
    'ryan': ('en-GB-RyanNeural', 'ryan_en-gb'),
}
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:[’'][A-Za-z]+)*")


def norm(text: str) -> str:
    value = ' '.join(text.strip().split())
    return value.lower() if WORD_PATTERN.fullmatch(value) else value


def sentences(text: str) -> list[str]:
    """Use the same sentence boundaries as the reader's ▶ buttons."""
    out = []
    for part in re.split(r'(?<=[.!?])\s+', text.strip()):
        part = part.strip()
        if not part:
            continue
        if out and re.search(r'\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr)\.$', out[-1], re.I):
            out[-1] += ' ' + part
        else:
            out.append(part)
    return out


def load_packs(pack_ids: set[str] | None = None):
    catalog = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
    for pack in catalog['packs']:
        if pack_ids is None or pack['id'] in pack_ids:
            contents = json.loads((ROOT / pack['file']).read_text(encoding='utf-8'))
            for story in contents['stories']:
                yield pack['id'], story


def sha(text: str, voice: str) -> str:
    return hashlib.sha256((voice + '\0' + text).encode('utf-8')).hexdigest()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Arquivo JSON inválido: {path}: {exc}') from exc
    raise RuntimeError(f'Esperado objeto JSON em {path}')


def load_metadata() -> dict:
    return read_json(TTS / 'generated.json')


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def mp3_valid(path: Path) -> bool:
    """Quick sanity check; not a full audio decoder."""
    if not path.is_file() or path.stat().st_size <= 256:
        return False
    with path.open('rb') as file:
        first = file.read(3)
    return first == b'ID3' or (len(first) >= 2 and first[0] == 0xff and first[1] & 0xe0 == 0xe0)


def rebuild_index():
    """Publish only files matching the current text+voice fingerprint."""
    saved = load_metadata()
    result = {'version': 1, 'voices': {}}
    for _short, (voice, slug) in VOICES.items():
        root = TTS / slug
        word_paths = {}
        for path in sorted(root.glob('*.mp3')):
            word = path.stem
            if (WORD_PATTERN.fullmatch(word) and mp3_valid(path)
                    and saved.get(path.relative_to(ROOT).as_posix()) == sha(word, voice)):
                word_paths[word] = path.relative_to(ROOT).as_posix()
        stories = {}
        for pack_id, story in load_packs():
            base = root / 'packs' / pack_id / story['id']
            entry = {'sentences': []}
            full_path = base / 'full.mp3'
            full_text = story['text'].strip()
            if mp3_valid(full_path) and saved.get(full_path.relative_to(ROOT).as_posix()) == sha(full_text, voice):
                entry['full'] = {'text': full_text, 'path': full_path.relative_to(ROOT).as_posix()}
            parts = [s for paragraph in re.split(r'\n\s*\n', full_text) for s in sentences(paragraph)]
            for i, sentence in enumerate(parts, 1):
                path = base / f's{i:04d}.mp3'
                if mp3_valid(path) and saved.get(path.relative_to(ROOT).as_posix()) == sha(sentence, voice):
                    entry['sentences'].append({'text': sentence, 'path': path.relative_to(ROOT).as_posix()})
            if entry['sentences'] or 'full' in entry:
                stories[story['id']] = entry
        if word_paths or stories:
            result['voices'][voice] = {'dir': f'tts/{slug}', 'words': word_paths, 'stories': stories}
    write_json(TTS / 'index.json', result)
    return result


def stop_error(error: Exception) -> bool:
    """Don't attempt to circumvent provider denial or throttling."""
    msg = str(error).lower()
    return any(x in msg for x in ('429', 'rate limit', 'too many requests',
                                  '403', 'forbidden', 'unauthorized', '401'))


async def synthesize(tasks, *, voice: str, delay: float = 0.8, force: bool = False,
                     dry_run: bool = False, max_items: int = 0, retries: int = 2,
                     workers: int = 2, timeout: float = 50,
                     only_failed: bool = False, group: str = 'words',
                     max_failures: int = 6):
    """Bounded async workers with atomic, resumable output.

    --delay is minimum spacing *between starting* requests across all workers.
    Retrying includes exponential backoff. Provider rate limits stop the batch.
    """
    if not dry_run:
        try:
            import edge_tts
        except ImportError as exc:
            raise SystemExit('Instale: python -m pip install -r requirements-tts.txt') from exc

    saved = load_metadata()
    slug = next((folder for name, folder in VOICES.values() if name == voice), None)
    if not slug:
        raise ValueError('Voz desconhecida')
    failed_path = TTS / f'failed-{slug}-{group}.json'
    failures = read_json(failed_path)

    entries = []
    skipped = 0
    for path, text in tasks:
        key = path.relative_to(ROOT).as_posix()
        if only_failed and key not in failures:
            continue
        fingerprint = sha(text, voice)
        if not force and mp3_valid(path) and saved.get(key) == fingerprint:
            skipped += 1
            failures.pop(key, None)
            continue
        entries.append((path, text, key, fingerprint))
    total_pending = len(entries)
    if max_items:
        entries = entries[:max_items]
    total = len(entries)
    print(f'Voz: {voice} | pendentes: {total_pending} | existentes: {skipped} | '
          f'nesta execução: {total} | workers: {workers} | intervalo: {delay:.2f}s', flush=True)
    if dry_run:
        for path, text, *_ in entries:
            print(f'[simulação] {path.relative_to(ROOT)} <- {text[:70]}')
        return
    if not entries:
        write_json(failed_path, failures)
        rebuild_index()
        print('Tudo atualizado: nenhum MP3 pendente.', flush=True)
        return

    queue = asyncio.Queue()
    for entry in entries:
        queue.put_nowait(entry)

    state_lock = asyncio.Lock()
    pace_lock = asyncio.Lock()
    next_start = 0.0
    finished = success = failed_count = consecutive_failures = 0
    halted = asyncio.Event()
    halt_reason = ''
    last_save = time.monotonic()

    async def pace():
        nonlocal next_start
        async with pace_lock:
            pause = next_start - time.monotonic()
            if pause > 0:
                await asyncio.sleep(pause)
            next_start = time.monotonic() + delay

    def save_progress():
        write_json(TTS / 'generated.json', saved)
        write_json(failed_path, failures)

    async def worker():
        nonlocal finished, success, failed_count, consecutive_failures, halt_reason, last_save
        while not halted.is_set():
            try:
                path, text, key, fingerprint = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.mp3.part')
            error_msg = None
            try:
                for attempt in range(retries + 1):
                    if halted.is_set():
                        break
                    try:
                        temp.unlink(missing_ok=True)
                        await pace()
                        # A timeout applies to the entire synthesis, not merely connection.
                        await asyncio.wait_for(
                            edge_tts.Communicate(text, voice).save(str(temp)), timeout=timeout)
                        if not mp3_valid(temp):
                            raise ValueError('MP3 vazio ou incompleto')
                        temp.replace(path)
                        error_msg = None
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        error_msg = f'{type(exc).__name__}: {exc}'
                        temp.unlink(missing_ok=True)
                        if stop_error(exc):
                            halt_reason = f'Serviço recusou/limitou requisições: {error_msg}'
                            halted.set()
                            break
                        if attempt < retries:
                            # Retry only after a real pause. This is not a rate-limit bypass.
                            await asyncio.sleep(min(12.0, max(1.5, delay * 2) * 2 ** attempt))
                async with state_lock:
                    finished += 1
                    if error_msg is None and path.exists() and mp3_valid(path):
                        saved[key] = fingerprint
                        failures.pop(key, None)
                        success += 1
                        consecutive_failures = 0
                        print(f'[{finished}/{total}] OK {key}', flush=True)
                    elif not halted.is_set():
                        failures[key] = error_msg or 'Sem áudio'
                        failed_count += 1
                        consecutive_failures += 1
                        print(f'[{finished}/{total}] FALHOU {key}: {error_msg}', flush=True)
                        if consecutive_failures >= max_failures:
                            halt_reason = f'{consecutive_failures} falhas seguidas: serviço possivelmente indisponível'
                            halted.set()
                    if finished % 5 == 0 or time.monotonic() - last_save > 4:
                        save_progress()
                        last_save = time.monotonic()
            finally:
                temp.unlink(missing_ok=True)
                queue.task_done()

    print('Ctrl+C preserva arquivos concluídos e atualiza o índice.', flush=True)
    try:
        await asyncio.gather(*(worker() for _ in range(min(workers, total))))
    finally:
        # Runs also when asyncio.run() cancels tasks on Ctrl+C.
        save_progress()
        rebuild_index()
        print(f'Resumo: {success} novos, {failed_count} falhas, {total - finished} não iniciados.'
              f' Índice: tts/index.json. Falhas: {failed_path.name}', flush=True)
        if halt_reason:
            print(f'Parado: {halt_reason}', flush=True)
