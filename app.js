(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const PACK_CACHE = 'storyspeak-packs-v18';
  const NATURAL_API = 'https://freeapi.pro';
  const LOCAL_TTS_INDEX = './tts/index.json';
  const VOICE_KEY = 'storyspeak-voice-v25';
  const VOICE_META_KEY = 'storyspeak-natural-voices-v13';
  const OFFLINE_META_KEY = 'storyspeak-offline-voice-packs-v13';
  const GLOBAL_AUDIO_CACHE = 'storyspeak-audio-global-v18';
  const OLD_PLAYBACK_CACHE = 'storyspeak-audio-on-demand-v13';
  const OLD_PACK_AUDIO_PREFIX = 'storyspeak-audio-pack-v13-';
  let audioMigration = null;
  // Keep Andrew Neural separate from Andrew Multilingual. Audio cache keys are voice-specific.
  const ANDREW_US = 'en-US-AndrewNeural';
  const ENGLISH_VOICES = new Set([
    ANDREW_US, 'en-US-AvaNeural', 'en-GB-SoniaNeural', 'en-GB-RyanNeural'
  ]);
  const DEFAULT_VOICE = `cloud:${ANDREW_US}`;
  const AUDIO_CACHE_LIMIT = 35;
  const dictionary = window.STORYSPEAK_DICTIONARY || {};
  const state = {
    catalog: null, cache: null, downloaded: new Set(), busy: new Set(),
    route: 0, selected: null, speechId: 0, speakingButton: null,
    deferredInstall: null, voices: [], toastTimer: null,
    lastWordTap: null, utterance: null, speakingWord: null, pendingSlowWord: null,
    cloudVoices: readJson(VOICE_META_KEY, readJson('storyspeak-natural-voices-v12', [])), cloudDisabled: false,
    audio: null, audioUrl: null, fetchController: null,
    offlineJobs: new Map(), offlineVoices: {},
    offlineSaved: readJson(OFFLINE_META_KEY, {}), currentMeta: null,
    ttsIndex: { version: 1, voices: {} }, staticAudioMaps: new Map(),
    audioCache: new Map(),
  };

  function readJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch { return false; }
  }
  function element(tag, className = '', content) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== undefined) el.textContent = content;
    return el;
  }
  const normalize = text => String(text || '').toLocaleLowerCase('en-US').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const packUrl = pack => new URL(pack.file, document.baseURI).href;

  function toast(text) {
    $('toast').textContent = text;
    $('toast').classList.remove('hidden');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 3300);
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#101722' : '#f7f9fd';
    $('themeBtn').textContent = theme === 'dark' ? '☀' : '☾';
    $('themeBtn').setAttribute('aria-label', theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro');
    save('storyspeak-theme', theme);
  }

  function networkStatus() {
    $('connection').textContent = navigator.onLine ? 'Online' : 'Offline';
    $('connection').classList.toggle('offline', !navigator.onLine);
  }

  function rankStory(story, words) {
    let score = 0;
    const fields = [
      [normalize(story.title), 12], [normalize((story.tags || []).join(' ')), 9],
      [normalize(story.genre), 7], [normalize(story.summary), 4],
      [normalize((story.terms || []).join(' ')), 2]
    ];
    for (const term of words) {
      const match = fields.find(([text]) => text.includes(term));
      if (!match) return 0;
      score += match[1];
    }
    return score || 1;
  }

  function renderStories() {
    if (!state.catalog) return;
    const words = normalize($('searchInput').value).split(/\s+/).filter(Boolean);
    const level = $('levelFilter').value;
    const category = $('categoryFilter').value;
    const matches = state.catalog.stories
      .filter(s => (level === 'all' || s.level === level) &&
        (category === 'all' || s.packId === category))
      .map(story => ({ story, score: rankStory(story, words) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score || a.story.title.localeCompare(b.story.title));
    $('resultCount').textContent = `${matches.length} ${matches.length === 1 ? 'texto' : 'textos'}`;
    $('emptySearch').classList.toggle('hidden', matches.length > 0);
    const root = $('storyList'); root.replaceChildren();
    for (const { story } of matches) {
      const card = element('button', 'story-card'); card.type = 'button';
      const meta = element('div', 'card-meta');
      meta.append(element('span', 'pill', story.level), element('span', '', story.genre));
      const footer = element('div', 'card-footer');
      footer.append(element('span', '', `${story.words} palavras`),
        element('span', state.downloaded.has(story.packId) ? 'offline' : '', state.downloaded.has(story.packId) ? '✓ Offline' : 'Ler agora →'));
      card.append(meta, element('h3', '', story.title), element('p', '', story.summary), footer);
      card.addEventListener('click', () => { location.hash = `#read/${encodeURIComponent(story.id)}`; });
      root.append(card);
    }
  }

  function fillCategories() {
    const select = $('categoryFilter');
    const selected = select.value;
    select.replaceChildren(new Option('Todas as categorias', 'all'));
    for (const pack of state.catalog.packs) select.add(new Option(pack.title, pack.id));
    select.value = [...select.options].some(option => option.value === selected) ? selected : 'all';
  }

  async function refreshDownloads() {
    state.downloaded.clear();
    if (!state.cache) return;
    for (const pack of state.catalog.packs) {
      if (await state.cache.match(packUrl(pack))) state.downloaded.add(pack.id);
    }
  }

  async function ensurePack(pack, signal, refresh = false) {
    const url = packUrl(pack);
    let response = null;
    let fromNetwork = false;
    // Durante o download de áudio, garantir que as frases sejam da edição
    // publicada, não de um pack antigo ainda armazenado no navegador.
    if (refresh && navigator.onLine) {
      try {
        const fresh = await fetch(url, { signal, cache: 'no-store' });
        if (!fresh.ok) throw new Error('Pack remoto indisponível');
        response = fresh;
        fromNetwork = true;
      } catch (error) {
        if (signal?.aborted) throw error;
        console.warn('Pack remoto indisponível, tentando cache:', error);
      }
    }
    if (!response) {
      response = await state.cache?.match(url);
      if (!response) {
        response = await fetch(url, { signal });
        fromNetwork = true;
      }
    }
    if (!response.ok) throw new Error('Pacote indisponível');
    const data = await response.clone().json();
    if (data.id !== pack.id || !Array.isArray(data.stories)) throw new Error('Pacote inválido');
    if (fromNetwork) await state.cache?.put(url, response.clone());
    state.downloaded.add(pack.id);
    return data;
  }

  function naturalVoiceOptions() {
    // Use the actual Edge voice name as a permanent ID, not the API's mutable ID.
    // That keeps old Andrew Multilingual files and browser caches isolated.
    const available = new Map((state.cloudVoices || [])
      .filter(v => ENGLISH_VOICES.has(v.edgeVoice))
      .map(v => [v.edgeVoice, v]));
    const local = new Set(Object.keys(state.ttsIndex?.voices || {}));
    const names = {
      [ANDREW_US]: 'Andrew (inglês americano)',
      'en-US-AvaNeural': 'Ava',
      'en-GB-SoniaNeural': 'Sonia',
      'en-GB-RyanNeural': 'Ryan'
    };
    return [...ENGLISH_VOICES]
      .filter(edge => edge === ANDREW_US || available.has(edge) || local.has(edge))
      .map(edge => ({
        id: edge, edgeVoice: edge, name: names[edge],
        apiId: available.get(edge)?.id || null
      }));
  }
  const stableVoiceId = voice => voiceCode(voice) || voice;
  const offlinePackKey = (packId, voice) => `${packId}:${stableVoiceId(voice)}`;

  // Sem opção técnica de formato: sempre baixa história, frases e palavras distintas.
  function audioItems(stories) {
    const unique = new Map();
    const add = text => {
      const normalized = normalizeTts(text);
      if (normalized && !unique.has(normalized)) unique.set(normalized, normalized);
    };
    for (const story of stories) {
      add(story.text.trim()); // botão "Ouvir texto inteiro"
      for (const paragraph of story.text.trim().split(/\n\s*\n/)) {
        for (const sentence of splitSentences(paragraph.trim())) add(sentence);
      }
    }
    for (const story of stories) {
      for (const [word] of story.text.matchAll(/[A-Za-z]+(?:[’'][A-Za-z]+)*/g)) add(word);
    }
    return [...unique.values()];
  }

  // Palavras únicas dos textos; compartilhadas entre todos os packs.
  function storyWords(stories) {
    const words = new Set();
    for (const story of stories) {
      for (const [word] of story.text.matchAll(/[A-Za-z]+(?:[’'][A-Za-z]+)*/g))
        words.add(normalize(word.replace(/’/g, "'")));
    }
    return [...words];
  }

  // Ao baixar uma coleção, garante tradução em português para cada palavra.
  // As traduções já conhecidas são locais e o restante é salvo globalmente.
  // A consulta online é feita SOMENTE após o clique em "Baixar coleção".
  async function downloadTranslations(stories, signal, progress) {
    if (signal.aborted) throw new DOMException('Cancelado', 'AbortError');
    const words = storyWords(stories);
    const available = words.filter(word => Boolean(dictionary[word])).length;
    progress(words.length, words.length);
    return { available, total: words.length };
  }

  function jobProgress(packId, done, total, message) {
    const progress = document.querySelector(`[data-pack-progress="${packId}"]`);
    if (progress) { progress.max = Math.max(1, total); progress.value = done; }
    const label = document.querySelector(`[data-pack-status="${packId}"]`);
    if (label) label.textContent = `${message} (${done}/${total})`;
  }

  // Os MP3 vêm do projeto ou cache. Traduções novas consultam API somente pelo clique.
  async function downloadVoicePack(pack, voice) {
    if (!state.cache || state.offlineJobs.has(pack.id)) return;
    if (state.offlineJobs.size) {
      toast('Conclua o download atual antes de iniciar outro.');
      return;
    }
    const controller = new AbortController();
    state.offlineJobs.set(pack.id, { controller, voice });
    renderPacks();
    let done = 0, missingAudio = 0, audioTotal = 0, translationTotal = 0;
    let translated = 0;
    const recordKey = offlinePackKey(pack.id, voice);
    try {
      if (navigator.onLine) await loadLocalTtsIndex();
      const data = await ensurePack(pack, controller.signal, true);
      const items = audioItems(data.stories);
      audioTotal = items.length;
      translationTotal = storyWords(data.stories).length;
      const total = audioTotal + translationTotal;
      state.offlineSaved[recordKey] = {
        status: 'partial', audioCount: 0, audioTotal, translationCount: 0, translationTotal
      };
      save(OFFLINE_META_KEY, state.offlineSaved);
      try { await navigator.storage?.persist?.(); } catch {}
      const cache = await sharedAudioCache();
      jobProgress(pack.id, 0, total, 'Baixando áudios');
      for (const text of items) {
        if (controller.signal.aborted) throw new DOMException('Cancelado', 'AbortError');
        const key = await audioRequestKey(voice, text);
        if (!(await cache.match(key))) {
          const path = projectAudioPath(voice, text);
          if (!path) {
            missingAudio++;
          } else {
            try {
              const response = await fetch(new URL(path, document.baseURI), { signal: controller.signal });
              if (!response.ok) throw new Error(`Arquivo ausente (${response.status})`);
              const blob = await response.blob();
              if (blob.size < 256) throw new Error('MP3 inválido');
              await cache.put(key, new Response(blob, { headers: { 'Content-Type': 'audio/mpeg' } }));
            } catch (error) {
              if (controller.signal.aborted) throw error;
              console.warn('MP3 estático indisponível:', path, error);
              missingAudio++;
            }
          }
        }
        done++;
        jobProgress(pack.id, done, total, 'Salvando áudios');
      }
      const translations = await downloadTranslations(data.stories, controller.signal,
        (current, count) => jobProgress(pack.id, audioTotal + current, total, 'Salvando traduções'));
      translated = translations.available;
      const savedAudio = audioTotal - missingAudio;
      const complete = !missingAudio && translated === translationTotal;
      state.offlineSaved[recordKey] = {
        mode: 'all', status: complete ? 'complete' : 'partial',
        count: savedAudio, total: audioTotal, audioCount: savedAudio, audioTotal,
        translationCount: translated, translationTotal, downloadedAt: Date.now()
      };
      save(OFFLINE_META_KEY, state.offlineSaved);
      toast(complete ? 'Coleção completa: histórias, voz e tradução offline!'
        : `Salvos ${savedAudio}/${audioTotal} áudios e ${translated}/${translationTotal} traduções. Pode completar depois.`);
    } catch (error) {
      if (controller.signal.aborted) toast('Download interrompido. Toque novamente para completar.');
      else toast(`Não foi possível concluir: ${error.message || 'verifique sua conexão'}`);
      console.warn('Download da coleção:', error);
    } finally {
      state.offlineJobs.delete(pack.id);
      renderPacks(); renderStories();
    }
  }

  // Uma ação por coleção. O usuário só escolhe a voz e toca em baixar.
  function renderPacks() {
    if (!state.catalog) return;
    const root = $('packList'); root.replaceChildren();
    $('storageInfo').textContent = 'Baixe uma vez para ler, ouvir e traduzir palavras sem internet.';
    const voices = naturalVoiceOptions();
    for (const pack of state.catalog.packs) {
      const job = state.offlineJobs.get(pack.id);
      const busy = state.busy.has(pack.id) || !!job;
      const voiceId = state.offlineVoices[pack.id] ||
        voices.find(v => v.edgeVoice === ANDREW_US)?.id || voices[0]?.id;
      if (!voiceId) continue;
      state.offlineVoices[pack.id] = voiceId;
      const saved = state.offlineSaved[offlinePackKey(pack.id, voiceId)];
      const complete = saved?.status === 'complete' &&
        Number.isInteger(saved.translationTotal) &&
        saved.translationCount === saved.translationTotal;
      const card = element('div', 'pack-card');
      const top = element('div', 'pack-top');
      const copy = element('div', 'pack-copy');
      copy.append(element('h3', '', pack.title),
        element('p', '', pack.description),
        element('small', '', `${pack.count} histórias`));
      top.append(element('div', 'pack-icon', pack.emoji), copy);
      const controls = element('div', 'pack-audio');
      const voiceLabel = element('label', '', 'Voz');
      const select = element('select', 'download-voice');
      select.setAttribute('aria-label', `Voz para ${pack.title}`);
      for (const voice of voices) select.add(new Option(
        `${voice.edgeVoice.startsWith('en-GB-') ? '🇬🇧' : '🇺🇸'} ${voice.name.replace(/ Multilingual| Neural| \(arquivos locais\)/gi,'')}`, voice.id));
      select.value = voiceId;
      select.disabled = busy;
      select.addEventListener('change', () => {
        state.offlineVoices[pack.id] = select.value;
        renderPacks();
      });
      voiceLabel.append(select);
      const button = element('button', 'action-button download-primary', job ? 'Baixando...' :
        complete ? '↻ Verificar download' : saved ? '↻ Completar download' : '↓ Baixar coleção');
      button.type = 'button'; button.disabled = busy;
      button.addEventListener('click', () => downloadVoicePack(pack, voiceId));
      const cancel = element('button', 'action-button delete', 'Cancelar');
      cancel.type = 'button'; cancel.classList.toggle('hidden', !job);
      cancel.addEventListener('click', () => job?.controller.abort());
      const remove = element('button', 'action-button delete', 'Excluir download');
      remove.type = 'button'; remove.disabled = busy || (!saved && !state.downloaded.has(pack.id));
      remove.addEventListener('click', () => removeCollection(pack));
      const actions = element('div', 'pack-audio-actions'); actions.append(button, cancel, remove);
      const status = element('small', 'pack-download-status');
      status.dataset.packStatus = pack.id;
      status.textContent = job ? 'Preparando seu download...' : saved
        ? complete ? '✓ Texto, áudio e tradução disponíveis offline.'
          : Number.isInteger(saved.translationTotal)
            ? `Áudios: ${saved.audioCount}/${saved.audioTotal} · Traduções: ${saved.translationCount}/${saved.translationTotal}. Toque para completar.`
            : 'Áudios já salvos. Toque para adicionar as traduções offline.'
        : state.downloaded.has(pack.id) ? '✓ Texto salvo. Baixe áudio e traduções.'
          : 'Inclui texto, áudios e tradução de cada palavra.';
      const progress = element('progress', 'pack-progress');
      progress.max = 1; progress.value = 0;
      progress.dataset.packProgress = pack.id;
      progress.classList.toggle('hidden', !job);
      controls.append(voiceLabel, actions, status, progress);
      card.append(top, controls); root.append(card);
    }
  }

  async function removeCollection(pack) {
    if (state.offlineJobs.has(pack.id) || state.busy.has(pack.id)) return;
    state.busy.add(pack.id);
    renderPacks();
    try {
      await state.cache?.delete(packUrl(pack));
      state.downloaded.delete(pack.id);
      for (const key of Object.keys(state.offlineSaved)) {
        if (!key.startsWith(`${pack.id}:`)) continue;
        const voice = key.slice(pack.id.length + 1);
        delete state.offlineSaved[key];
      }
      save(OFFLINE_META_KEY, state.offlineSaved);
      toast('Coleção removida. Os áudios compartilhados continuam no dispositivo.');
    } catch (error) {
      console.warn('Não foi possível apagar a coleção:', error);
      toast('Não foi possível remover os downloads.');
    } finally {
      state.busy.delete(pack.id);
      renderPacks(); renderStories();
    }
  }

  async function loadStory(meta) {
    const pack = state.catalog.packs.find(p => p.id === meta.packId);
    if (!pack) throw new Error('Pacote não encontrado');
    const url = packUrl(pack);
    const cached = await state.cache?.match(url);
    if (cached) {
      const local = await cached.json();
      const story = local.stories?.find(s => s.id === meta.id);
      if (story) return story;
    }
    // Uma história adicionada após o download pode não existir no pack antigo.
    // Nesse caso, atualiza o texto da coleção somente quando houver internet.
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error('Texto indisponível');
    const data = await response.clone().json();
    const story = data.stories?.find(s => s.id === meta.id);
    if (!story) throw new Error('História não encontrada');
    if (cached) await state.cache?.put(url, response.clone());
    return story;
  }

  // Apenas vozes en-US e en-GB, com uma seleção curta e sem duplicatas.
  function fillVoices() {
    const select = $('voiceSelect');
    const selected = select.value || readJson(VOICE_KEY, DEFAULT_VOICE);
    select.replaceChildren();
    const natural = document.createElement('optgroup');
    natural.label = 'Vozes naturais';
    for (const voice of naturalVoiceOptions()) {
      natural.append(new Option(`${voice.edgeVoice.startsWith('en-GB-') ? '🇬🇧' : '🇺🇸'} ${voice.name.replace(/ Multilingual| Neural| \(arquivos locais\)/gi, '')}`, `cloud:${voice.id}`));
    }
    select.append(natural);
    const availableVoices = 'speechSynthesis' in window ? speechSynthesis.getVoices() : [];
    // Apenas a melhor opção local de cada sotaque, evitando dezenas de vozes duplicadas.
    state.voices = ['en-US', 'en-GB'].map(lang => availableVoices
      .filter(v => v.lang.toLowerCase() === lang.toLowerCase())
      .sort((a, b) => Number(Boolean(b.localService)) - Number(Boolean(a.localService)) ||
        Number(/google/i.test(b.name)) - Number(/google/i.test(a.name)))[0]
    ).filter(Boolean);
    const local = document.createElement('optgroup');
    local.label = 'Vozes do aparelho';
    local.append(new Option('Automática · voz nativa', 'native:'));
    for (const voice of state.voices) local.append(new Option(`${voice.name} · ${voice.lang}`, `native:${voice.voiceURI}`));
    select.append(local);
    const values = [...select.options].map(option => option.value);
    select.value = values.includes(selected) ? selected :
      (values.includes(DEFAULT_VOICE) ? DEFAULT_VOICE : values[0] || 'native:');
    if (state.catalog) renderPacks();
  }

  async function refreshNaturalVoices() {
    if (!navigator.onLine) return;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 6500);
      let response;
      try { response = await fetch(`${NATURAL_API}/api/voices`, { signal: controller.signal }); }
      finally { clearTimeout(timeout); }
      if (!response.ok) throw new Error('Catálogo de vozes indisponível');
      const json = await response.json();
      if (!Array.isArray(json.voices)) throw new Error('Catálogo de vozes inválido');
      const voices = json.voices.filter(voice => typeof voice.id === 'string' &&
        ENGLISH_VOICES.has(voice.edgeVoice) && typeof voice.name === 'string');
      // IDs são obtidos da API. Em caso de falha, mantemos o último catálogo salvo.
      const dedup = new Map(voices.map(voice => [voice.edgeVoice, voice]));
      const selection = [
        ANDREW_US, 'en-US-AvaNeural',
        'en-GB-SoniaNeural', 'en-GB-RyanNeural'
      ].map(id => dedup.get(id)).filter(Boolean);
      if (!selection.length) throw new Error('Nenhuma voz US/UK');
      state.cloudVoices = selection;
      save(VOICE_META_KEY, selection);
      fillVoices();
    } catch (error) {
      console.info('Vozes naturais não atualizadas:', error.message);
    }
  }

  // Chave estável na origem do próprio site: POST remoto não é armazenado pelo Service Worker.
  const normalizeTts = text => {
    const value = String(text).trim().replace(/\s+/g, ' ');
    return /^[A-Za-z]+(?:[’'][A-Za-z]+)*$/.test(value) ? value.toLowerCase() : value;
  };
  async function audioRequestKey(voice, text) {
    const data = new TextEncoder().encode(JSON.stringify([stableVoiceId(voice), normalizeTts(text)]));
    const digest = await crypto.subtle.digest('SHA-256', data);
    const hex = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
    return new Request(new URL(`./_audio/v16/${hex}.mp3`, document.baseURI));
  }

  // Índice estático: evita um GET que retornaria 404 para cada palavra não gerada.
  // O nome da voz neural, não o ID temporário da API, identifica cada MP3 local.
  function voiceCode(voiceId) {
    if (ENGLISH_VOICES.has(voiceId)) return voiceId;
    // Legacy cloud IDs are only accepted for voices explicitly present in the new catalog.
    return naturalVoiceOptions().find(v => v.apiId && v.apiId === voiceId)?.edgeVoice || null;
  }

  function projectAudioPath(voiceId, text) {
    const voice = voiceCode(voiceId);
    const record = state.ttsIndex?.voices?.[voice];
    if (!record) return null;
    const normalized = normalizeTts(text);
    if (/^[a-z]+(?:[’'][a-z]+)*$/.test(normalized) && record.words?.[normalized])
      return record.words[normalized];
    let mapped = state.staticAudioMaps.get(voice);
    if (!mapped) {
      mapped = new Map();
      for (const story of Object.values(record.stories || {})) {
        if (story.full) mapped.set(normalizeTts(story.full.text), story.full.path);
        for (const sentence of story.sentences || [])
          mapped.set(normalizeTts(sentence.text), sentence.path);
      }
      state.staticAudioMaps.set(voice, mapped);
    }
    return mapped.get(normalized) || null;
  }

  async function loadLocalTtsIndex() {
    try {
      const response = await fetch(LOCAL_TTS_INDEX, { cache: 'reload' });
      if (!response.ok) throw new Error('Índice não encontrado');
      const index = await response.json();
      if (index.version !== 1 || !index.voices || typeof index.voices !== 'object') throw new Error('Índice inválido');
      state.ttsIndex = index;
      state.staticAudioMaps.clear();
    } catch (error) {
      // A leitura ainda funciona, mesmo antes de executar qualquer script Python.
      console.warn('Sem índice local de MP3:', error.message);
    }
  }

  // Reaproveita todos os MP3 antigos sem baixá-los outra vez.
  // Os caches legados são apagados somente após a cópia terminar.
  async function migrateAudioCaches() {
    const shared = await caches.open(GLOBAL_AUDIO_CACHE);
    const names = await caches.keys();
    const oldNames = names.filter(name => name === OLD_PLAYBACK_CACHE ||
      name.startsWith(OLD_PACK_AUDIO_PREFIX));
    for (const name of oldNames) {
      const old = await caches.open(name);
      try {
        for (const request of await old.keys()) {
          if (!(await shared.match(request))) {
            const response = await old.match(request);
            if (response?.ok) await shared.put(request, response);
          }
        }
        await caches.delete(name);
      } catch (error) {
        // Se faltar espaço, mantém o cache anterior para uma próxima tentativa.
        console.warn('Migração do áudio não concluída:', name, error);
      }
    }
    return shared;
  }

  function sharedAudioCache() {
    if (!audioMigration) audioMigration = migrateAudioCaches().catch(error => {
      audioMigration = null;
      throw error;
    });
    return audioMigration;
  }

  async function findNaturalCached(voice, text) {
    const cache = await sharedAudioCache();
    const response = await cache.match(await audioRequestKey(voice, text));
    return response ? response.blob() : null;
  }

  async function requestNaturalAudio(text, voice, signal) {
    if (text.length > 1900) throw new Error('Trecho longo demais para este provedor');
    // Timeout por requisição: um provedor travado não prende indefinidamente o download.
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, 20000);
    try {
      if (signal?.aborted) abort();
      // Never send an old Andrew Multilingual ID to the API as a fallback.
      const edgeName = voiceCode(voice);
      let providerId = state.cloudVoices.find(v => v.edgeVoice === edgeName)?.id;
      // On the first explicit playback of an uncached word, discover the API ID.
      // If the provider lacks AndrewNeural, NEVER silently substitute Multilingual.
      if (!providerId && navigator.onLine && edgeName) {
        await refreshNaturalVoices();
        providerId = state.cloudVoices.find(v => v.edgeVoice === edgeName)?.id;
      }
      if (!edgeName || !providerId) throw new Error('Esta voz não está disponível na API. Use os MP3 locais ou o TTS do Android.');
      const response = await fetch(`${NATURAL_API}/api/tts`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice: providerId, text: normalizeTts(text), rate: 0, pitch: 0 }),
        signal: controller.signal
      });
      if (!response.ok) {
        const error = new Error(`TTS remoto HTTP ${response.status}`); error.status = response.status;
        throw error;
      }
      const blob = await response.blob();
      if ((!blob.type.includes('audio') && blob.type !== 'application/octet-stream') || blob.size < 100)
        throw new Error('A API não retornou um MP3');
      return blob;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
    }
  }

  function releaseRemoteAudio() {
    if (state.audio) {
      state.audio.onended = null;
      state.audio.onerror = null;
      state.audio.pause();
      state.audio.removeAttribute('src');
      state.audio = null;
    }
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioUrl = null;
  }

  function clearAudio(cancel = false) {
    state.speechId++;
    if (cancel) {
      state.fetchController?.abort();
      if (state.utterance && 'speechSynthesis' in window) speechSynthesis.cancel();
    }
    releaseRemoteAudio();
    state.fetchController = null;
    if (state.speakingButton) {
      const button = state.speakingButton;
      button.classList.remove('playing');
      button.textContent = '▶';
      button.setAttribute('aria-label', `Ouvir frase ${button.dataset.sentence}`);
    }
    state.utterance = null;
    state.speakingButton = null;
    state.speakingWord = null;
    state.pendingSlowWord = null;
    $('stopBtn').classList.add('hidden');
  }

  function stopAudio() { clearAudio(true); }
  function isAudioActive() { return Boolean(state.utterance || state.audio || state.fetchController); }

  function finishSpeech(id, successful) {
    if (id !== state.speechId) return;
    const queued = successful ? state.pendingSlowWord : null;
    clearAudio();
    if (queued) speak(queued.word, null, true, queued.holder);
  }

  function speakNative(text, slow, id) {
    if (id !== state.speechId) return;
    if (!('speechSynthesis' in window)) {
      toast('Voz indisponível: navegador sem TTS nativo e serviço online inacessível.');
      finishSpeech(id, false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    const rate = Number($('rateInput').value);
    utterance.rate = slow ? Math.max(0.55, Math.min(0.7, rate * 0.75)) : rate;
    const uri = $('voiceSelect').value.startsWith('native:') ? $('voiceSelect').value.slice(7) : '';
    const voice = state.voices.find(v => v.voiceURI === uri) ||
      state.voices.find(v => v.lang.toLowerCase() === 'en-us') || state.voices[0];
    utterance.lang = voice?.lang || 'en-US';
    if (voice) utterance.voice = voice;
    state.utterance = utterance;
    utterance.onend = () => finishSpeech(id, true);
    utterance.onerror = event => {
      if (event.error !== 'canceled' && event.error !== 'interrupted') toast('Erro na voz nativa.');
      finishSpeech(id, false);
    };
    speechSynthesis.speak(utterance);
  }

  // Somente um clique explícito em palavra, frase, texto ou teste de voz chega aqui.
  // Primeiro cache local, depois MP3 da hospedagem, só então serviço de terceiros.
  async function fetchNaturalAudio(text, voice, controller) {
    const key = JSON.stringify([stableVoiceId(voice), normalizeTts(text)]);
    if (state.audioCache.has(key)) return state.audioCache.get(key);
    let blob = null;
    if ('caches' in window) {
      try { blob = await findNaturalCached(voice, text); }
      catch (error) { console.warn('Cache de áudio indisponível:', error); }
    }
    if (!blob) {
      const staticPath = projectAudioPath(voice, text);
      if (staticPath) {
        try {
          const response = await fetch(new URL(staticPath, document.baseURI), { signal: controller.signal });
          if (!response.ok) throw new Error(`MP3 local HTTP ${response.status}`);
          const candidate = await response.blob();
          if (candidate.size < 256) throw new Error('MP3 estático vazio');
          blob = candidate;
        } catch (error) {
          if (controller.signal.aborted) throw error;
          console.warn('MP3 do projeto não pôde ser carregado:', staticPath, error);
        }
      }
    }
    if (!blob) {
      // Nunca acionado automaticamente ao navegar, pesquisar ou baixar packs.
      if (!navigator.onLine || state.cloudDisabled || voice.startsWith('static:'))
        throw new Error('Nenhum MP3 local e API indisponível');
      blob = await requestNaturalAudio(text, voice, controller.signal);
    }
    if ('caches' in window) {
      try {
        const request = await audioRequestKey(voice, text);
        const cache = await sharedAudioCache();
        await cache.put(request, new Response(blob, { headers: { 'Content-Type': 'audio/mpeg' } }));
      } catch (error) { console.warn('Sem espaço para cachear áudio:', error); }
    }
    state.audioCache.set(key, blob);
    if (state.audioCache.size > AUDIO_CACHE_LIMIT) state.audioCache.delete(state.audioCache.keys().next().value);
    return blob;
  }

  async function speakNatural(text, slow, id, voice) {
    const controller = new AbortController();
    state.fetchController = controller;
    const timeout = setTimeout(() => controller.abort(), 8500);
    try {
      const blob = await fetchNaturalAudio(text, voice, controller);
      if (id !== state.speechId) return;
      const url = URL.createObjectURL(blob);
      state.audioUrl = url;
      const audio = new Audio(url);
      audio.playbackRate = Math.max(0.55, Math.min(1.3, Number($('rateInput').value) * (slow ? 0.72 : 1)));
      state.audio = audio;
      audio.onended = () => finishSpeech(id, true);
      audio.onerror = () => {
        if (id !== state.speechId) return;
        releaseRemoteAudio();
        state.cloudDisabled = true;
        fillVoices();
        speakNative(text, slow, id);
      };
      await audio.play();
    } catch (error) {
      if (id !== state.speechId || state.utterance) return; // Cancelado ou fallback já iniciado por audio.onerror.
      state.cloudDisabled = true;
      releaseRemoteAudio();
      fillVoices();
      toast('Voz natural indisponível. Usando a voz do Android.');
      console.warn('TTS online falhou; fallback nativo:', error);
      speakNative(text, slow, id);
    } finally {
      clearTimeout(timeout);
      if (id === state.speechId) state.fetchController = null;
    }
  }

  // Ponto único de entrada para áudio de palavras, frases e teste de voz.
  function speak(text, button = null, slow = false, holder = null) {
    if (button && state.speakingButton === button && isAudioActive()) { stopAudio(); return; }
    stopAudio();
    const id = state.speechId;
    state.speakingButton = button;
    state.speakingWord = holder;
    if (button) {
      button.textContent = '■';
      button.classList.add('playing');
      button.setAttribute('aria-label', `Parar frase ${button.dataset.sentence}`);
    }
    $('stopBtn').classList.remove('hidden');
    const selection = $('voiceSelect').value || DEFAULT_VOICE;
    if (selection.startsWith('cloud:')) {
      $('readerStatus').textContent = 'Preparando áudio…';
      void speakNatural(text, slow, id, selection.slice(6));
    } else {
      speakNative(text, slow, id);
    }
  }

  async function translate(word) {
    const key = normalize(word.replace(/[’]/g, "'"));
    if (dictionary[key]) return dictionary[key];
    throw new Error('Tradução ainda não disponível.');
  }

  // Uma única palavra pode ficar expandida; os resultados atrasados nunca reabrem outra palavra.
  let expanded = null;
  let glossId = 0;
  async function clickWord(word, button, holder) {
    // Dois toques NORMAIS na mesma palavra: normal -> lento.
    // Sem janela de 430ms e sem cortar a primeira voz: se ela estiver ativa,
    // a leitura lenta comeca somente quando a primeira terminar.
    const slow = state.lastWordTap === holder;
    state.lastWordTap = slow ? null : holder;
    if (slow && state.speakingWord === holder && isAudioActive()) {
      state.pendingSlowWord = { word, holder };
      $('readerStatus').textContent = 'Aguarde: a próxima leitura será mais lenta.';
    } else {
      speak(word, null, slow, holder);
      $('readerStatus').textContent = slow ? 'Pronúncia lenta.' : 'Toque novamente para ouvir devagar.';
    }
    if (expanded === holder) return; // Dois toques mantêm a tradução aberta.
    closeGloss();
    expanded = holder;
    const id = ++glossId;
    button.setAttribute('aria-expanded', 'true');
    const gloss = element('span', 'translation', 'Traduzindo...');
    holder.append(gloss);
    try {
      const translation = await translate(word);
      if (expanded === holder && glossId === id) gloss.textContent = translation;
    } catch {
      if (expanded === holder && glossId === id)
        gloss.textContent = navigator.onLine ? 'Tradução indisponível' : 'Tradução requer internet';
    }
  }
  function closeGloss() {
    if (!expanded) return;
    expanded.querySelector('button')?.setAttribute('aria-expanded', 'false');
    expanded.querySelector('.translation')?.remove();
    expanded = null;
    glossId++;
  }

  // Intl.Segmenter preserva pontuação e evita dividir números como 3.14.
  // O fallback mantém o leitor funcional em navegadores sem Segmenter.
  function splitSentences(text) {
    if (Intl.Segmenter) {
      const parts = [...new Intl.Segmenter('en', { granularity: 'sentence' }).segment(text)]
        .map(item => item.segment.trim()).filter(Boolean);
      // Evita criar botão isolado para títulos como "Dr." ou "Mr.".
      return parts.reduce((sentences, part) => {
        if (sentences.length && /\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr)\.$/i.test(sentences.at(-1)))
          sentences[sentences.length - 1] += ' ' + part;
        else sentences.push(part);
        return sentences;
      }, []);
    }
    return (text.match(/[^.!?]+[.!?]+(?:["'”’])?(?=\s|$)|[^.!?]+$/g) || [text])
      .map(sentence => sentence.trim()).filter(Boolean);
  }

  function makeSentence(text, number) {
    const row = element('section', 'sentence-row');
    const button = element('button', 'sentence-play', '▶');
    button.type = 'button';
    button.title = 'Ouvir esta frase';
    button.dataset.sentence = String(number);
    button.setAttribute('aria-label', `Ouvir frase ${number}`);
    button.addEventListener('click', () => { state.lastWordTap = null; speak(text, button); });
    const p = element('p', 'sentence-text');
    const pattern = /[A-Za-z]+(?:[’'][A-Za-z]+)*/g;
    let last = 0;
    for (const match of text.matchAll(pattern)) {
      if (match.index > last) p.append(document.createTextNode(text.slice(last, match.index)));
      const word = match[0];
      const holder = element('span', 'word-token');
      const wordButton = element('button', 'word-button', word);
      wordButton.type = 'button';
      wordButton.setAttribute('aria-label', `Ouvir e traduzir ${word}`);
      wordButton.setAttribute('aria-expanded', 'false');
      wordButton.addEventListener('click', () => clickWord(word, wordButton, holder));
      holder.append(wordButton); p.append(holder);
      last = match.index + word.length;
    }
    if (last < text.length) p.append(document.createTextNode(text.slice(last)));
    row.append(button, p);
    return row;
  }

  function openStory(meta, story) {
    stopAudio(); closeGloss(); state.lastWordTap = null;
    state.selected = story; state.currentMeta = meta;
    $('readFullBtn').onclick = () => { state.lastWordTap = null; speak(story.text.trim()); };
    $('readerMeta').replaceChildren(element('span', 'pill', meta.level),
      element('span', '', `${meta.genre} · ${meta.words} palavras`));
    $('readerTitle').textContent = story.title;
    $('readerSummary').textContent = story.summary;
    const root = $('paragraphs'); root.replaceChildren();
    let number = 0;
    story.text.trim().split(/\n\s*\n/).forEach(text => {
      const block = element('div', 'paragraph-block');
      for (const sentence of splitSentences(text.trim())) block.append(makeSentence(sentence, ++number));
      root.append(block);
    });
    $('readerStatus').textContent = 'Toque nas palavras para ouvir e traduzir.';
  }

  function showView(view) {
    for (const name of ['library', 'packs', 'reader']) $(name + 'View').classList.toggle('hidden', view !== name);
    $('libraryTab').classList.toggle('active', view !== 'packs');
    $('packsTab').classList.toggle('active', view === 'packs');
    window.scrollTo(0, 0);
  }

  async function route() {
    if (!state.catalog) return;
    const id = ++state.route;
    stopAudio(); closeGloss();
    const hash = decodeURIComponent(location.hash || '#library');
    if (hash === '#packs') { renderPacks(); showView('packs'); return; }
    if (!hash.startsWith('#read/')) { showView('library'); return; }
    const meta = state.catalog.stories.find(s => s.id === hash.slice(6));
    if (!meta) { location.hash = '#library'; return; }
    try {
      const story = await loadStory(meta);
      if (state.route !== id) return;
      openStory(meta, story); showView('reader');
    } catch (error) {
      if (state.route !== id) return;
      console.error(error);
      location.hash = '#library';
      toast('Não foi possível abrir. Baixe o pacote para ler offline.');
    }
  }

  async function init() {
    const theme = readJson('storyspeak-theme', null) ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    setTheme(theme);
    $('themeBtn').addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    networkStatus();
    window.addEventListener('online', networkStatus);
    window.addEventListener('offline', networkStatus);
    window.addEventListener('hashchange', route);
    $('searchInput').addEventListener('input', renderStories);
    $('levelFilter').addEventListener('change', renderStories);
    $('categoryFilter').addEventListener('change', renderStories);
    $('backBtn').addEventListener('click', () => { location.hash = '#library'; });
    $('stopBtn').addEventListener('click', stopAudio);
    $('rateInput').value = readJson('storyspeak-rate', 1.0);
    $('rateValue').textContent = `${Number($('rateInput').value).toFixed(1)}×`;
    $('rateInput').addEventListener('input', e => {
      $('rateValue').textContent = `${Number(e.target.value).toFixed(1)}×`;
      save('storyspeak-rate', Number(e.target.value));
    });
    $('voiceSelect').addEventListener('change', e => { save(VOICE_KEY, e.target.value); state.cloudDisabled = false; fillVoices(); });
    $('previewVoiceBtn').addEventListener('click', () => { state.lastWordTap = null; speak('Nobody wanted to call it a conversation.'); });
    $('refreshVoicesBtn').addEventListener('click', async () => { state.cloudDisabled = false; fillVoices(); await refreshNaturalVoices(); toast('Vozes atualizadas.'); });
    fillVoices();
    // O catálogo remoto é consultado somente quando o usuário clica em ‘Atualizar vozes’.
    // Não há chamadas à API de TTS em background.
    if ('speechSynthesis' in window) {
      speechSynthesis.addEventListener?.('voiceschanged', fillVoices);
      window.addEventListener('pageshow', fillVoices);
    }
    window.addEventListener('pagehide', stopAudio);
    window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); state.deferredInstall = e; });
    $('installBtn').addEventListener('click', async () => {
      if (!state.deferredInstall) { toast('No Chrome Android: menu ⋮ → Instalar aplicativo.'); return; }
      const prompt = state.deferredInstall; state.deferredInstall = null;
      await prompt.prompt();
    });
    if ('serviceWorker' in navigator && location.protocol !== 'file:')
      navigator.serviceWorker.register('./sw.js').catch(console.warn);
    if ('caches' in window) {
      try { state.cache = await caches.open(PACK_CACHE); } catch {}
      // Migra caches de downloads antigos em segundo plano.
      sharedAudioCache().catch(error => console.warn('Cache de áudio:', error));
    }
    try {
      const response = await fetch('./catalog.json');
      if (!response.ok) throw new Error('Catálogo não disponível');
      state.catalog = await response.json();
      if (!Array.isArray(state.catalog.stories) || !Array.isArray(state.catalog.packs)) throw new Error('Catálogo inválido');
      fillCategories();
      await loadLocalTtsIndex();
      fillVoices();
      await refreshDownloads();
      renderStories(); renderPacks(); route();
    } catch (error) {
      console.error(error);
      $('storyList').append(element('p', 'empty', 'Não foi possível carregar as histórias. Use HTTPS ou localhost.'));
      toast('Erro ao carregar a biblioteca.');
    }
  }

  init();
})();
