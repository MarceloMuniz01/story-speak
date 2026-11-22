(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const DEFAULT_VOICE = 'en-US-AndrewNeural';
  const CACHE_NAME = 'storyspeak-offline-archives-v28';
  const INSTALLED_KEY = 'storyspeak-offline-installed-v28';
  // Preferences are intentionally not versioned: updates must not reset learning settings.
  const PREFS_KEY = 'storyspeak-preferences-v1';
  const MANIFEST_URL = './archives/manifest.json';
  const dictionary = window.STORYSPEAK_DICTIONARY || {};
  const WORD_RE = /[A-Za-z]+(?:[’'][A-Za-z]+)*/g;
  const state = {
    catalog: null, manifest: null, cache: null, installed: readJson(INSTALLED_KEY, { words: {}, packs: {} }),
    downloaded: new Map(), jobs: new Map(), archiveCache: new Map(), wordArchives: new Map(), pronunciations: new Map(),
    packVoice: new Map(),
    selected: null, currentMeta: null, routeId: 0, ttsIndex: { voices: {} },
    voices: [], deferredInstall: null, lastWordTap: null, pendingSlowWord: null,
    utterance: null, audio: null, audioUrl: null, speechId: 0,
    speakingButton: null, speakingWord: null, audioLoading: false, toastTimer: null
  };

  function readJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (error) { console.warn('Preferências não salvas:', error); }
  }
  const PREF_DEFAULT_VOICE = 'cloud:' + DEFAULT_VOICE;
  function readPreferences() {
    const saved = readJson(PREFS_KEY, {});
    const old = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
    // Migrate settings from the former reader; leave ZIP download bookkeeping separate.
    const legacyRate = readJson('storyspeak-rate', 1);
    const rawRate = Number(old.rate ?? legacyRate);
    const rate = Number.isFinite(rawRate)
      ? Math.round(Math.min(1.3, Math.max(0.7, rawRate)) * 10) / 10 : 1;
    const theme = old.theme ?? readJson('storyspeak-theme', null);
    const voice = old.voice ?? readJson('storyspeak-voice-v27',
      readJson('storyspeak-voice-v25', PREF_DEFAULT_VOICE));
    return {
      theme: theme === 'light' || theme === 'dark' ? theme : null,
      voice: (typeof voice === 'string' && voice.startsWith('native:')) || (/^cloud:en-(US|GB)-[\w-]+Neural$/.test(voice))
        ? voice : PREF_DEFAULT_VOICE,
      rate,
      level: typeof old.level === 'string' ? old.level : 'all',
      category: typeof old.category === 'string' ? old.category : 'all'
    };
  }
  const preferences = readPreferences();
  function setPreference(key, value) {
    preferences[key] = value;
    save(PREFS_KEY, preferences);
  }
  function node(tag, className = '', content) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== undefined) el.textContent = content;
    return el;
  }
  const normalize = text => String(text || '').toLocaleLowerCase('en-US')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const normAudio = text => {
    const value = String(text).trim().replace(/\s+/g, ' ');
    return /^[A-Za-z]+(?:[’'][A-Za-z]+)*$/.test(value) ? value.toLowerCase() : value;
  };
  const archiveUrl = entry => new URL('./' + entry.url, document.baseURI).href;
  const archiveRequest = entry => new Request(archiveUrl(entry));

  function toast(message) {
    $('toast').textContent = message;
    $('toast').classList.remove('hidden');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 4200);
  }
  function theme(value) {
    document.documentElement.dataset.theme = value;
    document.querySelector('meta[name="theme-color"]').content = value === 'dark' ? '#101722' : '#f7f9fd';
    $('themeBtn').textContent = value === 'dark' ? '☀' : '☾';
    $('themeBtn').setAttribute('aria-label', value === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro');
    setPreference('theme', value);
  }
  function networkStatus() {
    $('connection').textContent = navigator.onLine ? 'Online' : 'Offline';
    $('connection').classList.toggle('offline', !navigator.onLine);
  }

  function rankStory(story, words) {
    if (!words.length) return 1;
    let score = 0;
    const fields = [
      [normalize(story.title), 12], [normalize((story.tags || []).join(' ')), 9],
      [normalize(story.genre), 7], [normalize(story.summary), 4],
      [normalize((story.terms || []).join(' ')), 2]
    ];
    for (const word of words) {
      const result = fields.find(([text]) => text.includes(word));
      if (!result) return 0;
      score += result[1];
    }
    return score;
  }

  function voicesForPack(packId) {
    return Object.entries(state.manifest?.voices || {}).filter(([, item]) => item.packs?.[packId]);
  }
  function voiceLabel(voiceId) {
    const voice = state.manifest?.voices?.[voiceId];
    return voice ? `${voice.locale === 'en-GB' ? '🇬🇧' : '🇺🇸'} ${voice.name} · ${voice.locale}` : voiceId;
  }
  function installedVoices(packId) {
    return state.downloaded.get(packId) || new Set();
  }
  function preferredVoice(packId) {
    const saved = preferences.voice.startsWith('cloud:') ? preferences.voice.slice(6) : null;
    const installed = installedVoices(packId);
    if (saved && installed.has(saved)) return saved;
    return [...installed][0] || null;
  }
  function packageSelection(packId) {
    const available = voicesForPack(packId).map(([id]) => id);
    const wanted = state.packVoice.get(packId) ||
      (preferences.voice.startsWith('cloud:') ? preferences.voice.slice(6) : null);
    if (available.includes(wanted)) return wanted;
    const installed = [...installedVoices(packId)].find(id => available.includes(id));
    return installed || (available.includes(state.manifest?.defaultVoice)
      ? state.manifest.defaultVoice : available[0] || null);
  }

  function renderStories() {
    if (!state.catalog) return;
    const terms = normalize($('searchInput').value).split(/\s+/).filter(Boolean);
    const level = $('levelFilter').value, category = $('categoryFilter').value;
    const results = state.catalog.stories
      .filter(story => (level === 'all' || level === story.level) &&
        (category === 'all' || category === story.packId))
      .map(story => ({ story, score: rankStory(story, terms) }))
      .filter(result => result.score > 0)
      .sort((a, b) => b.score - a.score || a.story.title.localeCompare(b.story.title));
    $('resultCount').textContent = `${results.length} ${results.length === 1 ? 'texto' : 'textos'}`;
    $('emptySearch').classList.toggle('hidden', results.length > 0);
    const root = $('storyList'); root.replaceChildren();
    for (const { story } of results) {
      const ready = installedVoices(story.packId).size > 0;
      const card = node('button', 'story-card'); card.type = 'button';
      const meta = node('div', 'card-meta');
      meta.append(node('span', 'pill', story.level), node('span', '', story.genre));
      const footer = node('div', 'card-footer');
      footer.append(node('span', '', `${story.words} palavras`),
        node('span', ready ? 'offline' : '', ready ? '✓ Disponível offline' : '↓ Baixar para ler'));
      card.append(meta, node('h3', '', story.title), node('p', '', story.summary), footer);
      card.addEventListener('click', () => {
        if (!ready) { location.hash = '#packs'; toast('Baixe a categoria antes de abrir esta história.'); }
        else location.hash = `#read/${encodeURIComponent(story.id)}`;
      });
      root.append(card);
    }
  }

  function fillCategories() {
    const select = $('categoryFilter');
    select.replaceChildren(new Option('Todas as categorias', 'all'));
    for (const pack of state.catalog.packs) select.add(new Option(pack.title, pack.id));
  }

  async function cachedAndVerified(entry, hash) {
    return Boolean(entry && hash === entry.sha256 &&
      await state.cache.match(archiveRequest(entry)));
  }

  async function migrateV27() {
    // Preserve installed Andrew ZIPs where their contents/hash are unchanged.
    const old = readJson('storyspeak-offline-installed-v27', null);
    const current = state.manifest?.voices?.[DEFAULT_VOICE];
    if (!old || !current || !('caches' in window)) return;
    const legacy = await caches.open('storyspeak-offline-archives-v27');
    state.installed.words ||= {};
    state.installed.packs ||= {};
    async function copy(oldUrl, entry) {
      if (!entry) return;
      if (await state.cache.match(archiveRequest(entry))) return;
      const source = await legacy.match(new Request(new URL('./archives/' + oldUrl, document.baseURI)));
      if (source) await state.cache.put(archiveRequest(entry), source.clone());
    }
    if (old.words === current.words.sha256) {
      await copy('words.zip', current.words);
      state.installed.words[DEFAULT_VOICE] = current.words.sha256;
    }
    for (const [packId, entry] of Object.entries(current.packs)) {
      if (old.packs?.[packId] !== entry.sha256) continue;
      await copy(packId + '.zip', entry);
      state.installed.packs[packId] ||= {};
      state.installed.packs[packId][DEFAULT_VOICE] = entry.sha256;
    }
    save(INSTALLED_KEY, state.installed);
  }

  async function refreshDownloads() {
    state.downloaded.clear();
    if (!state.cache || !state.manifest) return;
    for (const [voiceId, voice] of Object.entries(state.manifest.voices)) {
      if (!(await cachedAndVerified(voice.words, state.installed.words?.[voiceId]))) continue;
      for (const [packId, entry] of Object.entries(voice.packs)) {
        if (!(await cachedAndVerified(entry, state.installed.packs?.[packId]?.[voiceId]))) continue;
        if (!state.downloaded.has(packId)) state.downloaded.set(packId, new Set());
        state.downloaded.get(packId).add(voiceId);
      }
    }
  }

  // Each ZIP is fetched exactly once and stays intact inside Cache Storage.
  // Individual MP3s are never requested over the network.
  async function downloadArchive(entry, signal, progress) {
    if (!navigator.onLine) throw new Error('Conecte-se à internet para baixar esta coleção.');
    const response = await fetch(archiveUrl(entry), { cache: 'no-store', signal });
    if (!response.ok) throw new Error(`Arquivo ZIP indisponível (HTTP ${response.status})`);
    const length = entry.bytes;
    const reader = response.body?.getReader();
    const chunks = [];
    let size = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value); size += value.length;
        progress(size, length);
      }
    } else {
      const bytes = new Uint8Array(await response.arrayBuffer());
      chunks.push(bytes); size = bytes.length; progress(size, length);
    }
    if (signal.aborted) throw new DOMException('Cancelado', 'AbortError');
    if (size !== length) throw new Error('Download incompleto; tente novamente.');
    const blob = new Blob(chunks, { type: 'application/zip' });
    const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
    const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    if (hash !== entry.sha256) throw new Error('Falha na integridade do ZIP; arquivo não salvo.');
    await state.cache.put(archiveRequest(entry), new Response(blob, {
      headers: { 'Content-Type': 'application/zip' }
    }));
  }

  function updateProgress(packId, done, total, message) {
    const bar = [...document.querySelectorAll('[data-pack-progress]')]
      .find(item => item.dataset.packProgress === packId);
    if (bar) { bar.max = Math.max(total, 1); bar.value = done; }
    const label = [...document.querySelectorAll('[data-pack-status]')]
      .find(item => item.dataset.packStatus === packId);
    if (label) label.textContent = `${message} · ${Math.min(100, Math.round(done / Math.max(1, total) * 100))}%`;
  }

  async function downloadPack(pack, voiceId) {
    const voice = state.manifest?.voices?.[voiceId];
    const entry = voice?.packs?.[pack.id];
    if (!state.cache || !entry) { toast('Esta voz ainda não está disponível nesta coleção.'); return; }
    if (state.jobs.size) { toast('Conclua ou cancele o download atual.'); return; }
    const controller = new AbortController();
    state.jobs.set(pack.id, controller); renderPacks();
    try {
      try { await navigator.storage?.persist?.(); } catch {}
      const words = voice.words;
      const wordsReady = await cachedAndVerified(words, state.installed.words?.[voiceId]);
      const packReady = await cachedAndVerified(entry, state.installed.packs?.[pack.id]?.[voiceId]);
      // A revised words.zip must not force re-downloading an unchanged story ZIP.
      const packBytes = packReady ? 0 : entry.bytes;
      const total = packBytes + (wordsReady ? 0 : words.bytes);
      if (!wordsReady) {
        updateProgress(pack.id, 0, total, 'Baixando palavras da voz');
        await downloadArchive(words, controller.signal, current =>
          updateProgress(pack.id, current, total, 'Baixando palavras da voz'));
        state.installed.words ||= {};
        state.installed.words[voiceId] = words.sha256;
        state.wordArchives.delete(voiceId);
        state.pronunciations.delete(voiceId);
        save(INSTALLED_KEY, state.installed);
      }
      if (!packReady) {
        updateProgress(pack.id, total - entry.bytes, total, 'Baixando histórias e áudios');
        await downloadArchive(entry, controller.signal, current =>
          updateProgress(pack.id, total - entry.bytes + current, total, 'Baixando histórias e áudios'));
      }
      state.installed.packs ||= {};
      state.installed.packs[pack.id] ||= {};
      state.installed.packs[pack.id][voiceId] = entry.sha256;
      state.archiveCache.delete(pack.id + '|' + voiceId);
      setPreference('voice', 'cloud:' + voiceId);
      save(INSTALLED_KEY, state.installed);
      await refreshDownloads();
      renderStories();
      toast(`✓ ${pack.title} pronta para leitura com ${voice.name}!`);
    } catch (error) {
      toast(controller.signal.aborted ? 'Download cancelado. Tente novamente.' : `Erro no download: ${error.message}`);
      console.warn('Download da coleção:', error);
    } finally {
      state.jobs.delete(pack.id); renderPacks();
    }
  }

  async function removeCollection(pack, voiceId) {
    if (state.jobs.size || !state.cache) return;
    const item = state.manifest?.voices?.[voiceId]?.packs?.[pack.id];
    if (item) await state.cache.delete(archiveRequest(item));
    state.archiveCache.delete(pack.id + '|' + voiceId);
    if (state.installed.packs?.[pack.id]) {
      delete state.installed.packs[pack.id][voiceId];
      if (!Object.keys(state.installed.packs[pack.id]).length) delete state.installed.packs[pack.id];
    }
    save(INSTALLED_KEY, state.installed);
    await refreshDownloads();
    renderPacks(); renderStories();
    if (state.currentMeta?.packId === pack.id && !installedVoices(pack.id).size) location.hash = '#packs';
    toast('Áudio desta voz excluído. Outras vozes e palavras compartilhadas preservadas.');
  }

  function renderPacks() {
    if (!state.catalog) return;
    const root = $('packList'); root.replaceChildren();
    const size = entry => `${(entry.bytes / 1024 / 1024).toFixed(1)} MB`;
    $('storageInfo').textContent = state.manifest
      ? 'Escolha uma voz por coleção. As vozes disponíveis aparecem automaticamente; cada voz usa um ZIP de palavras compartilhadas.'
      : 'Nenhum pacote ZIP publicado. Gere os MP3 e execute o empacotador no Termux.';
    for (const pack of state.catalog.packs) {
      const voiceId = packageSelection(pack.id);
      const voice = state.manifest?.voices?.[voiceId];
      const current = voice?.packs?.[pack.id];
      const installed = installedVoices(pack.id);
      const ready = installed.has(voiceId);
      const controller = state.jobs.get(pack.id);
      const card = node('div', 'pack-card'), top = node('div', 'pack-top'), copy = node('div', 'pack-copy');
      copy.append(node('h3', '', pack.title), node('p', '', pack.description),
        node('small', '', `${pack.count} histórias${current ? ' · ' + size(current) : ''}`));
      top.append(node('div', 'pack-icon', pack.emoji), copy);
      const controls = node('div', 'pack-audio');
      const label = node('label', 'pack-voice-label', 'Voz para download');
      const select = node('select', 'pack-voice-select');
      select.setAttribute('aria-label', `Selecionar voz para ${pack.title}`);
      const available = voicesForPack(pack.id);
      for (const [id] of available) select.add(new Option(
        `${voiceLabel(id)}${installed.has(id) ? ' ✓ baixada' : ''}`, id));
      if (!available.length) select.add(new Option('Nenhuma voz publicada', ''));
      select.value = voiceId || '';
      select.disabled = Boolean(controller) || Boolean(state.jobs.size) || !available.length;
      select.addEventListener('change', event => {
        state.packVoice.set(pack.id, event.target.value);
        setPreference('voice', 'cloud:' + event.target.value);
        renderPacks();
      });
      label.append(select);
      const actions = node('div', 'pack-audio-actions');
      const download = node('button', 'action-button download-primary', controller ? 'Baixando…' :
        ready ? '✓ Voz baixada' : '↓ Baixar esta voz');
      download.type = 'button';
      download.disabled = Boolean(controller) || ready || !current || Boolean(state.jobs.size);
      download.addEventListener('click', () => downloadPack(pack, voiceId));
      actions.append(download);
      if (controller) {
        const cancel = node('button', 'action-button delete', 'Cancelar');
        cancel.type = 'button'; cancel.addEventListener('click', () => controller.abort());
        actions.append(cancel);
      }
      if (ready) {
        const remove = node('button', 'action-button delete', 'Excluir esta voz');
        remove.type = 'button'; remove.addEventListener('click', () => removeCollection(pack, voiceId));
        actions.append(remove);
      }
      const status = node('small', 'pack-download-status', controller ? 'Preparando…' :
        ready ? `✓ ${voiceLabel(voiceId)} pronta para leitura offline.` :
        installed.size ? `${installed.size} voz(es) baixada(s). Selecione outra para baixar ou excluir.` :
        current ? 'Inclui histórias, frases e áudios. Palavras baixadas uma vez por voz.' :
        'Nenhum áudio completo publicado para esta categoria.');
      status.dataset.packStatus = pack.id;
      const progress = node('progress', 'pack-progress');
      progress.max = 1; progress.value = 0; progress.dataset.packProgress = pack.id;
      progress.classList.toggle('hidden', !controller);
      controls.append(label, actions, status, progress);
      card.append(top, controls); root.append(card);
    }
  }

  async function openZip(entry) {
    const response = await state.cache.match(archiveRequest(entry));
    if (!response) throw new Error('Download não encontrado. Baixe a voz novamente.');
    return JSZip.loadAsync(await response.arrayBuffer());
  }
  async function getWordZip(voiceId) {
    if (!state.wordArchives.has(voiceId)) {
      state.wordArchives.set(voiceId, await openZip(state.manifest.voices[voiceId].words));
    }
    return state.wordArchives.get(voiceId);
  }
  async function pronunciationFor(word, voiceId) {
    // Never show American respellings for a British voice.
    if (!voiceId?.startsWith('en-US-')) return null;
    if (!state.pronunciations.has(voiceId)) {
      const zip = await getWordZip(voiceId);
      const file = zip.file('pronunciations-en-US.json');
      const data = file ? JSON.parse(await file.async('string')) : {};
      state.pronunciations.set(voiceId, data.locale === 'en-US' ? (data.words || {}) : {});
    }
    return state.pronunciations.get(voiceId)[normalize(word.replace(/[’]/g, "'"))] || null;
  }

  async function revealPronunciation(word, holder) {
    const selected = $('voiceSelect').value;
    const voiceId = selected.startsWith('cloud:') ? selected.slice(6) :
      (state.voices.find(v => selected === 'native:' + v.voiceURI)?.lang === 'en-US'
        ? preferredVoice(state.currentMeta?.packId) : null);
    if (!voiceId) return;
    try {
      const hint = await pronunciationFor(word, voiceId);
      if (!hint || expanded !== holder || holder.dataset.phonetic !== 'yes' ||
          $('voiceSelect').value !== selected || !holder.isConnected) return;
      const label = node('span', 'pronunciation-hint', hint);
      label.title = 'Pronúncia aproximada para falantes de português. Confirme pelo áudio.';
      holder.append(label);
    } catch (error) {
      console.info('Ajuda fonética indisponível:', error);
    }
  }

  async function getPackZip(packId, voiceId) {
    if (!installedVoices(packId).has(voiceId))
      throw new Error('Baixe esta voz para ouvir e ler offline.');
    const key = packId + '|' + voiceId;
    if (!state.archiveCache.has(key)) {
      // Avoid holding multiple large ZIPs in memory.
      state.archiveCache.clear();
      state.archiveCache.set(key, await openZip(state.manifest.voices[voiceId].packs[packId]));
    }
    return state.archiveCache.get(key);
  }
  async function loadStory(meta) {
    const voiceId = preferredVoice(meta.packId);
    if (!voiceId) throw new Error('Nenhuma voz baixada para esta categoria.');
    const zip = await getPackZip(meta.packId, voiceId);
    const path = state.manifest.voices[voiceId].packs[meta.packId].json;
    const entry = zip.file(path);
    if (!entry) throw new Error('Histórias ausentes no ZIP.');
    const pack = JSON.parse(await entry.async('string'));
    const story = pack.stories?.find(item => item.id === meta.id);
    if (!story) throw new Error('História não encontrada nesta edição. Atualize o download.');
    return story;
  }

  function projectAudioPath(text) {
    const voiceId = $('voiceSelect').value.slice(6);
    const record = state.ttsIndex.voices?.[voiceId];
    if (!record || !state.currentMeta) return null;
    const normalized = normAudio(text);
    if (/^[a-z]+(?:[’'][a-z]+)*$/.test(normalized)) {
      const path = record.words?.[normalized];
      return path ? { path, word: true } : null;
    }
    const story = record.stories?.[state.currentMeta.id];
    const pieces = [story?.full, ...(story?.sentences || [])];
    const found = pieces.find(item => item && normAudio(item.text) === normalized);
    if (found) return { path: found.path, word: false };
    // Same sentence may appear in more than one story of the active pack.
    for (const meta of state.catalog.stories.filter(s => s.packId === state.currentMeta.packId)) {
      const other = record.stories?.[meta.id];
      const match = [other?.full, ...(other?.sentences || [])]
        .find(item => item && normAudio(item.text) === normalized);
      if (match) return { path: match.path, word: false };
    }
    return null;
  }
  async function audioBlob(text) {
    const ref = projectAudioPath(text);
    if (!ref) throw new Error('Áudio não gerado para esta palavra ou frase.');
    const voiceId = $('voiceSelect').value.slice(6);
    if (!installedVoices(state.currentMeta.packId).has(voiceId))
      throw new Error('Esta voz não foi baixada.');
    const zip = ref.word ? await getWordZip(voiceId) : await getPackZip(state.currentMeta.packId, voiceId);
    const file = zip.file(ref.path);
    if (!file) throw new Error(`Áudio faltando no ZIP: ${ref.path}`);
    return new Blob([await file.async('uint8array')], { type: 'audio/mpeg' });
  }

  function fillVoices() {
    const select = $('voiceSelect');
    const requested = preferences.voice;
    select.replaceChildren();
    const offline = node('optgroup'); offline.label = 'Vozes baixadas para esta coleção';
    const installed = state.currentMeta ? installedVoices(state.currentMeta.packId) : new Set();
    for (const voiceId of installed) {
      offline.append(new Option(`${voiceLabel(voiceId)} (offline)`, 'cloud:' + voiceId));
    }
    if (offline.children.length) select.append(offline);
    const native = node('optgroup'); native.label = 'Vozes do aparelho (opcional)';
    native.append(new Option('Automática · Android', 'native:'));
    const voices = 'speechSynthesis' in window ? speechSynthesis.getVoices() : [];
    state.voices = ['en-US', 'en-GB'].map(lang => voices
      .filter(voice => voice.lang.toLowerCase() === lang.toLowerCase())
      .sort((a, b) => Number(Boolean(b.localService)) - Number(Boolean(a.localService)))[0])
      .filter(Boolean);
    for (const voice of state.voices) native.append(new Option(`${voice.name} · ${voice.lang}`, 'native:' + voice.voiceURI));
    select.append(native);
    const available = [...select.options].map(option => option.value);
    select.value = available.includes(requested) ? requested :
      (state.currentMeta && preferredVoice(state.currentMeta.packId)
        ? 'cloud:' + preferredVoice(state.currentMeta.packId) : 'native:');
  }

  function stopAudio() { clearAudio(true); }
  function clearAudio(cancel = false) {
    state.speechId++;
    if (cancel && 'speechSynthesis' in window) speechSynthesis.cancel();
    if (state.audio) {
      state.audio.onended = null; state.audio.onerror = null;
      state.audio.pause(); state.audio.removeAttribute('src'); state.audio = null;
    }
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioUrl = null;
    if (state.speakingButton) {
      const button = state.speakingButton;
      button.classList.remove('playing'); button.textContent = '▶';
      button.setAttribute('aria-label', `Ouvir frase ${button.dataset.sentence}`);
    }
    state.utterance = null; state.speakingButton = null; state.audioLoading = false;
    state.speakingWord = null; state.pendingSlowWord = null;
    $('stopBtn').classList.add('is-idle');
    $('stopBtn').disabled = true;
  }
  function finishSpeech(id, success) {
    if (id !== state.speechId) return;
    const next = success ? state.pendingSlowWord : null;
    clearAudio();
    if (next) speak(next.word, null, true, next.holder);
  }
  function isAudioActive() { return Boolean(state.audio || state.utterance || state.audioLoading); }

  function speakNative(text, slow, id) {
    if (id !== state.speechId) return;
    if (!('speechSynthesis' in window)) { toast('Áudio indisponível.'); finishSpeech(id, false); return; }
    const utterance = new SpeechSynthesisUtterance(text), selected = $('voiceSelect').value;
    const voice = state.voices.find(v => selected === 'native:' + v.voiceURI) ||
      state.voices.find(v => v.lang === 'en-US') || state.voices[0];
    utterance.lang = voice?.lang || 'en-US';
    if (voice) utterance.voice = voice;
    const rate = Number($('rateInput').value);
    utterance.rate = slow ? Math.max(0.55, Math.min(0.75, rate * 0.75)) : rate;
    state.utterance = utterance;
    utterance.onend = () => finishSpeech(id, true);
    utterance.onerror = () => finishSpeech(id, false);
    speechSynthesis.speak(utterance);
  }

  async function speakNatural(text, slow, id) {
    state.audioLoading = true;
    try {
      const blob = await audioBlob(text);
      if (id !== state.speechId) return;
      state.audioLoading = false;
      const url = URL.createObjectURL(blob);
      state.audioUrl = url;
      const audio = new Audio(url);
      state.audio = audio;
      audio.playbackRate = Math.max(0.55, Math.min(1.3, Number($('rateInput').value) * (slow ? 0.72 : 1)));
      audio.onended = () => finishSpeech(id, true);
      audio.onerror = () => {
        if (id !== state.speechId) return;
        toast('MP3 indisponível. Tentando a voz do aparelho.');
        speakNative(text, slow, id);
      };
      await audio.play();
    } catch (error) {
      if (id !== state.speechId) return;
      state.audioLoading = false;
      console.warn('Falha ao abrir MP3 no ZIP:', error);
      toast('Áudio do pacote indisponível; usando a voz do aparelho.');
      speakNative(text, slow, id);
    }
  }

  function speak(text, button = null, slow = false, holder = null) {
    if (button && state.speakingButton === button && isAudioActive()) { stopAudio(); return; }
    stopAudio();
    const id = state.speechId;
    state.speakingButton = button; state.speakingWord = holder; state.playbackSlow = slow;
    if (button) {
      button.textContent = '■'; button.classList.add('playing');
      button.setAttribute('aria-label', `Parar frase ${button.dataset.sentence}`);
    }
    $('stopBtn').classList.remove('is-idle');
    $('stopBtn').disabled = false;
    if ($('voiceSelect').value.startsWith('cloud:')) void speakNatural(text, slow, id);
    else speakNative(text, slow, id);
  }

  let expanded = null;
  function closeGloss() {
    if (!expanded) return;
    expanded.querySelector('button')?.setAttribute('aria-expanded', 'false');
    expanded.querySelector('.translation')?.remove();
    expanded.querySelector('.pronunciation-hint')?.remove();
    delete expanded.dataset.phonetic;
    expanded = null;
  }
  function clickWord(word, button, holder) {
    const slow = state.lastWordTap === holder;
    state.lastWordTap = slow ? null : holder;
    if (slow && state.speakingWord === holder && isAudioActive()) {
      state.pendingSlowWord = { word, holder };
      $('readerStatus').textContent = 'A próxima pronúncia será mais lenta.';
    } else {
      speak(word, null, slow, holder);
      $('readerStatus').textContent = slow ? 'Pronúncia lenta.' : 'Toque novamente para ouvir devagar.';
    }
    // The second tap reveals a phonetic cue, without adding a new control.
    holder.querySelector('.pronunciation-hint')?.remove();
    holder.dataset.phonetic = slow ? 'yes' : 'no';
    if (expanded === holder) {
      if (slow) void revealPronunciation(word, holder);
      return;
    }
    closeGloss(); expanded = holder;
    button.setAttribute('aria-expanded', 'true');
    const key = normalize(word.replace(/[’]/g, "'"));
    holder.append(node('span', 'translation', dictionary[key] || 'Tradução não cadastrada'));
    if (slow) void revealPronunciation(word, holder);
  }

  // Exact same segmentation as scripts/audio_common.py: keep the ZIP's sentence paths in sync.
  function splitSentences(text) {
    return text.trim().split(/(?<=[.!?])\s+/).filter(Boolean).reduce((out, part) => {
      if (out.length && /\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr)\.$/i.test(out[out.length - 1]))
        out[out.length - 1] += ' ' + part;
      else out.push(part);
      return out;
    }, []);
  }
  function sentenceRow(text, number) {
    const row = node('section', 'sentence-row'), button = node('button', 'sentence-play', '▶');
    button.type = 'button'; button.title = 'Ouvir esta frase'; button.dataset.sentence = String(number);
    button.setAttribute('aria-label', `Ouvir frase ${number}`);
    button.addEventListener('click', () => { state.lastWordTap = null; speak(text, button); });
    const p = node('p', 'sentence-text'); let previous = 0;
    for (const match of text.matchAll(WORD_RE)) {
      if (match.index > previous) p.append(document.createTextNode(text.slice(previous, match.index)));
      const word = match[0], holder = node('span', 'word-token');
      const wordButton = node('button', 'word-button', word);
      wordButton.type = 'button'; wordButton.setAttribute('aria-label', `Ouvir e traduzir ${word}`);
      wordButton.setAttribute('aria-expanded', 'false');
      wordButton.addEventListener('click', () => clickWord(word, wordButton, holder));
      holder.append(wordButton); p.append(holder);
      previous = match.index + word.length;
    }
    if (previous < text.length) p.append(document.createTextNode(text.slice(previous)));
    row.append(button, p); return row;
  }
  function openStory(meta, story) {
    stopAudio(); closeGloss(); state.lastWordTap = null;
    state.selected = story; state.currentMeta = meta;
    $('readFullBtn').onclick = () => { state.lastWordTap = null; speak(story.text.trim()); };
    $('readerMeta').replaceChildren(node('span', 'pill', meta.level),
      node('span', '', `${meta.genre} · ${meta.words} palavras`));
    $('readerTitle').textContent = story.title;
    $('readerSummary').textContent = story.summary;
    const root = $('paragraphs'); root.replaceChildren(); let number = 0;
    for (const text of story.text.trim().split(/\n\s*\n/)) {
      const block = node('div', 'paragraph-block');
      for (const sentence of splitSentences(text.trim())) block.append(sentenceRow(sentence, ++number));
      root.append(block);
    }
    fillVoices();
    $('readerStatus').textContent = 'Tradução e áudio baixados. Toque nas palavras para praticar.';
  }

  function showView(view) {
    for (const name of ['library', 'packs', 'reader']) $(name + 'View').classList.toggle('hidden', view !== name);
    $('libraryTab').classList.toggle('active', view !== 'packs');
    $('packsTab').classList.toggle('active', view === 'packs');
    window.scrollTo(0, 0);
  }
  async function route() {
    if (!state.catalog) return;
    const id = ++state.routeId;
    stopAudio(); closeGloss();
    const hash = decodeURIComponent(location.hash || '#library');
    if (hash === '#packs') { renderPacks(); showView('packs'); return; }
    if (!hash.startsWith('#read/')) { showView('library'); return; }
    const meta = state.catalog.stories.find(story => story.id === hash.slice(6));
    if (!meta) { location.hash = '#library'; return; }
    if (!installedVoices(meta.packId).size) {
      location.hash = '#packs'; toast('Baixe a categoria antes de ler.'); return;
    }
    try {
      const story = await loadStory(meta);
      if (state.routeId !== id) return;
      openStory(meta, story); showView('reader');
    } catch (error) {
      console.warn('Falha ao abrir história offline:', error);
      if (state.routeId !== id) return;
      location.hash = '#packs'; toast(error.message);
    }
  }

  async function loadJson(url, fallback = null) {
    try {
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    } catch (error) {
      if (!fallback || !('caches' in window)) throw error;
      const cached = await caches.match(new URL(url, document.baseURI).href);
      if (!cached) throw error;
      return cached.json();
    }
  }

  async function init() {
    theme(preferences.theme ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
    $('themeBtn').addEventListener('click', () => theme(
      document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    networkStatus();
    window.addEventListener('online', networkStatus);
    window.addEventListener('offline', networkStatus);
    window.addEventListener('hashchange', route);
    $('searchInput').addEventListener('input', renderStories);
    $('levelFilter').addEventListener('change', event => {
      setPreference('level', event.target.value); renderStories();
    });
    $('categoryFilter').addEventListener('change', event => {
      setPreference('category', event.target.value); renderStories();
    });
    $('backBtn').addEventListener('click', () => { location.hash = '#library'; });
    $('stopBtn').addEventListener('click', stopAudio);
    $('rateInput').value = String(preferences.rate);
    $('rateValue').textContent = `${Number($('rateInput').value).toFixed(1)}×`;
    $('rateInput').addEventListener('input', event => {
      $('rateValue').textContent = `${Number(event.target.value).toFixed(1)}×`;
      setPreference('rate', Number(event.target.value));
      if (state.audio) state.audio.playbackRate = Number(event.target.value) * (state.playbackSlow ? 0.72 : 1);
    });
    $('voiceSelect').addEventListener('change', event => {
      document.querySelectorAll('.pronunciation-hint').forEach(hint => hint.remove());
      document.querySelectorAll('.word-token[data-phonetic]').forEach(el => delete el.dataset.phonetic);
      setPreference('voice', event.target.value); stopAudio();
    });
    $('previewVoiceBtn').addEventListener('click', () => {
      if (state.selected) speak(splitSentences(state.selected.text.trim())[0]);
    });
    fillVoices();
    if ('speechSynthesis' in window) speechSynthesis.addEventListener?.('voiceschanged', fillVoices);
    window.addEventListener('pagehide', stopAudio);
    window.addEventListener('beforeinstallprompt', event => {
      event.preventDefault(); state.deferredInstall = event;
    });
    $('installBtn').addEventListener('click', async () => {
      if (!state.deferredInstall) { toast('Chrome Android: menu ⋮ → Instalar aplicativo.'); return; }
      const prompt = state.deferredInstall; state.deferredInstall = null; await prompt.prompt();
    });
    if ('serviceWorker' in navigator && location.protocol !== 'file:')
      navigator.serviceWorker.register('./sw.js').catch(console.warn);
    try {
      if (!('caches' in window) || !('JSZip' in window))
        throw new Error('Navegador sem suporte a downloads offline.');
      state.cache = await caches.open(CACHE_NAME);
      state.catalog = await loadJson('./catalog.json', true);
      if (!Array.isArray(state.catalog.packs) || !Array.isArray(state.catalog.stories))
        throw new Error('Catálogo inválido.');
      state.ttsIndex = await loadJson('./tts/index.json', true);
      try {
        const manifest = await loadJson(MANIFEST_URL, true);
        if (manifest.version !== 2 || !manifest.defaultVoice || !manifest.voices ||
            !Object.keys(manifest.voices).length)
          throw new Error('Manifesto de pacotes incompatível.');
        state.manifest = manifest;
        await migrateV27();
      } catch (error) {
        console.info('Pacotes ZIP ainda não publicados:', error);
      }
      fillCategories();
      if ([...$('levelFilter').options].some(option => option.value === preferences.level))
        $('levelFilter').value = preferences.level;
      if ([...$('categoryFilter').options].some(option => option.value === preferences.category))
        $('categoryFilter').value = preferences.category;
      await refreshDownloads();
      renderStories(); renderPacks(); route();
    } catch (error) {
      console.error(error);
      $('storyList').append(node('p', 'empty', 'Não foi possível iniciar a biblioteca. Use HTTPS ou localhost.'));
      toast(error.message);
    }
  }
  init();
})();
