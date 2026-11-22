"""Chromium integration: downloaded voices, offline read, ZIP count and settings."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for path, content in entries.items():
            archive.writestr(path, content, compress_type=zipfile.ZIP_DEFLATED if path.endswith('.json') else zipfile.ZIP_STORED)
    return stream.getvalue()


def meta(data, name):
    return {'url': f'archives/{name}', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


class OfflineMultiVoicePWA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'])
        cls.html = (ROOT / 'index.html').read_text().replace('<head>', '<head><base href="https://storyspeak.test/">', 1)
        cls.html = re.sub(r'<script[^>]+src="[^"]+"[^>]*></script>', '', cls.html)
        cls.html = re.sub(r'<link[^>]+rel="stylesheet"[^>]*>', '', cls.html)
        cls.scripts = [(ROOT / name).read_text() for name in ('dictionary.js', 'vendor/jszip.min.js', 'app.js')]
        story = {'id': 'test', 'title': 'Test Story', 'summary': 'Practise English',
                 'level': 'B1', 'genre': 'Animes', 'text': 'Hello world.'}
        catalog = {'version': 1, 'packs': [
            {'id':'animes','title':'Animes','description':'Anime','emoji':'🎬',
             'count': 1,'file':'packs/animes.json'}],
            'stories': [dict(story, packId='animes', words=2, terms=[], tags=[])]}
        mp3 = b'ID3' + b'\x00' * 600
        voices = {}
        zips = {}
        index = {'version': 1, 'voices': {}}
        for voice, short, slug in [('en-US-AndrewNeural', 'andrew', 'andrew_neural_en-us'),
                                    ('en-US-AvaNeural', 'ava', 'ava_en-us')]:
            base = 'tts/' + slug + '/'
            words = zip_bytes({base+'hello.mp3':mp3, base+'world.mp3':mp3,
                'pronunciations-en-US.json':json.dumps({'locale':'en-US',
                    'words':{'hello':'ha-LÔU','world':'UÂRLD'}}).encode()})
            path1 = base+'packs/animes/test/s0001.mp3'
            path2 = base+'packs/animes/test/full.mp3'
            pack = zip_bytes({'packs/animes.json':json.dumps({'id':'animes','stories':[story]}).encode(),
                              path1:mp3,path2:mp3})
            wm, pm = meta(words,'words-'+short+'.zip'), meta(pack,'animes-'+short+'.zip')
            voices[voice] = {'name':short.title(), 'locale':'en-US','short':short,'words':wm,
                             'packs':{'animes':dict(pm,json='packs/animes.json',stories=1)}}
            zips[wm['url']] = base64.b64encode(words).decode()
            zips[pm['url']] = base64.b64encode(pack).decode()
            index['voices'][voice] = {
                'words':{'hello':base+'hello.mp3','world':base+'world.mp3'},
                'stories':{'test':{'full':{'path':path2,'text':story['text']},
                    'sentences':[{'path':path1,'text':story['text']}]}}}
        cls.jsons = {'catalog.json':catalog, 'tts/index.json':index,
            'archives/manifest.json':{'version': 2, 'defaultVoice':'en-US-AndrewNeural', 'voices':voices}}
        cls.zips = zips
        cls.hash_by_size = {str(len(base64.b64decode(data))):list(bytes.fromhex(
            next(item['sha256'] for v in voices.values() for item in [v['words'],*v['packs'].values()]
                 if item['url'] == url))) for url,data in zips.items()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def mount(self, page, *, saved=None, cached=None, legacy_cached=None, offline=False,
              jsons_override=None, zips_override=None, hashes_override=None):
        page.set_content(self.html, wait_until='domcontentloaded', timeout=9000)
        page.add_style_tag(content=(ROOT / 'styles.css').read_text())
        page.evaluate('''({jsons,zips,hashes,saved,cached,legacy_cached,offline})=>{
          window.__store = new Map(Object.entries(saved));
          Object.defineProperty(window,'localStorage',{configurable:true,value:{
            getItem:k=>window.__store.has(k)?window.__store.get(k):null,
            setItem:(k,v)=>window.__store.set(k,String(v))
          }});
          Object.defineProperty(navigator,'onLine',{configurable:true,get:()=>!offline});
          const memory = new Map(), convert = x => Uint8Array.from(atob(x),c=>c.charCodeAt(0));
          window.__requests = [];
          const key = req => req.url || req;
          for(const [url,data] of Object.entries(cached))
            memory.set('storyspeak-offline-archives-v28|https://storyspeak.test/'+url,
              new Response(convert(data),{status:200}));
          for(const [url,data] of Object.entries(legacy_cached))
            memory.set('storyspeak-offline-archives-v27|https://storyspeak.test/'+url,
              new Response(convert(data),{status:200}));
          Object.defineProperty(window,'caches',{configurable:true,value:{
            open:async name=>({
              match:async req => memory.get(name+'|'+key(req))?.clone(),
              put:async (req,res) => memory.set(name+'|'+key(req),res.clone()),
              delete:async req => memory.delete(name+'|'+key(req))
            }),
            match:async req => memory.get('storyspeak-offline-archives-v28|'+key(req))?.clone()
          }});
          window.__savedCache = async()=>{
            const result={};
            for(const [key,res] of memory){
              if(!key.includes('https://storyspeak.test/')) continue;
              const bytes=new Uint8Array(await res.clone().arrayBuffer());
              let value='';for(const b of bytes)value+=String.fromCharCode(b);
              result[key.split('https://storyspeak.test/')[1]]=btoa(value);
            }
            return result;
          };
          Object.defineProperty(crypto,'subtle',{configurable:true,value:{
            digest:async (_alg,data)=>new Uint8Array(hashes[new Uint8Array(data).length]||[]).buffer
          }});
          URL.createObjectURL = ()=>'blob:mock';
          URL.revokeObjectURL = ()=>{};
          window.__audioPlays = 0;
          window.Audio = class {play(){window.__audioPlays++;return Promise.resolve();}
            pause(){}removeAttribute(){} };
          window.fetch=async url=>{
            const path=new URL(url.url||url,document.baseURI).pathname.slice(1);
            window.__requests.push(path);
            if(jsons[path]) return new Response(JSON.stringify(jsons[path]),{status:200,
              headers:{'Content-Type':'application/json'}});
            if(offline) throw new TypeError('Network unavailable');
            if(zips[path])return new Response(convert(zips[path]),{status:200,
              headers:{'Content-Type':'application/zip'}});
            return new Response('missing',{status:404});
          };
        }''', {'jsons':jsons_override or self.jsons,'zips':zips_override or self.zips,
                'hashes':hashes_override or self.hash_by_size,
                'saved':saved or {},'cached':cached or {},'legacy_cached':legacy_cached or {},'offline':offline})
        for script in self.scripts: page.add_script_tag(content=script)
        page.locator('.story-card').first.wait_for(timeout=9000)

    def test_two_voice_download_and_offline_prefs(self):
        context = self.browser.new_context(viewport={'width':390,'height':844})
        self.addCleanup(context.close)
        page = context.new_page()
        errors=[]
        page.on('pageerror', lambda e:errors.append(str(e)))
        self.mount(page)
        page.locator('#levelFilter').select_option('B1')
        page.locator('#themeBtn').click()
        page.locator('#rateInput').evaluate('e=>{e.value="1.2";e.dispatchEvent(new Event("input",{bubbles:true}))}')
        page.evaluate("location.hash='#packs'")
        page.locator('#packsView').wait_for(state='visible')
        select = page.locator('.pack-voice-select')
        self.assertEqual(select.locator('option').count(), 2)
        page.evaluate("document.querySelector('.pack-card .download-primary').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('pronta')",timeout=15000)
        page.evaluate("e=>{const n=document.querySelector('.pack-voice-select');n.value=e;n.dispatchEvent(new Event('change',{bubbles:true}))}", 'en-US-AvaNeural')
        page.evaluate("document.querySelector('.pack-card .download-primary').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('Ava')",timeout=15000)
        self.assertEqual(page.evaluate('window.__requests.filter(x=>x.endsWith(".zip"))'), [
            'archives/words-andrew.zip','archives/animes-andrew.zip',
            'archives/words-ava.zip','archives/animes-ava.zip'])
        saved = page.evaluate('Object.fromEntries(window.__store)')
        cached = page.evaluate('window.__savedCache()')
        self.assertEqual(json.loads(saved['storyspeak-preferences-v1'])['rate'], 1.2)
        self.assertEqual(json.loads(saved['storyspeak-preferences-v1'])['voice'], 'cloud:en-US-AvaNeural')
        page.evaluate("location.hash='#read/test'")
        page.locator('.word-button').first.wait_for(timeout=8000)
        self.assertEqual(page.locator('#voiceSelect').input_value(), 'cloud:en-US-AvaNeural')
        page.locator('.word-button').first.click()
        page.wait_for_function('window.__audioPlays===1',timeout=8000)
        self.assertFalse(any(x.endswith('.mp3') for x in page.evaluate('window.__requests')))
        self.assertEqual(errors,[],errors)
        second = context.new_page();second_err=[]
        second.on('pageerror',lambda e:second_err.append(str(e)))
        self.mount(second, saved=saved, cached=cached, offline=True)
        self.assertEqual(second.locator('#rateInput').input_value(),'1.2')
        self.assertEqual(second.locator('#levelFilter').input_value(),'B1')
        self.assertEqual(second.locator('html').get_attribute('data-theme'),'dark')
        second.locator('.story-card').first.click()
        second.locator('.word-button').first.wait_for(timeout=8000)
        self.assertEqual(second.locator('#voiceSelect').input_value(),'cloud:en-US-AvaNeural')
        second.locator('#voiceSelect').select_option('cloud:en-US-AndrewNeural')
        self.assertEqual(json.loads(second.evaluate('window.__store.get("storyspeak-preferences-v1")'))['voice'],
            'cloud:en-US-AndrewNeural')
        second.locator('.word-button').first.click()
        second.wait_for_function('window.__audioPlays===1',timeout=8000)
        self.assertFalse(any(x.endswith('.mp3') or x.endswith('.zip') for x in second.evaluate('window.__requests')))
        self.assertEqual(second_err,[],second_err)

    def test_second_touch_shows_only_offline_pronunciation_and_third_hides(self):
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        self.mount(page)
        page.evaluate("location.hash='#packs'")
        page.evaluate("document.querySelector('.download-primary').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('pronta')")
        cached = page.evaluate('window.__savedCache()')
        saved = page.evaluate('Object.fromEntries(window.__store)')
        offline_page = context.new_page()
        offline_page.on('pageerror', lambda err: errors.append(str(err)))
        self.mount(offline_page, saved=saved, cached=cached, offline=True)
        offline_page.locator('.story-card').first.click()
        word = offline_page.locator('.word-button').first
        word.wait_for()
        word.click()
        self.assertEqual(offline_page.locator('.pronunciation-hint').count(), 0)
        word.click()
        offline_page.locator('.pronunciation-hint').wait_for(timeout=8000)
        self.assertEqual(offline_page.locator('.pronunciation-hint').inner_text(), 'ha-LÔU')
        self.assertEqual(offline_page.locator('.translation').count(), 1)
        word.click()
        self.assertEqual(offline_page.locator('.pronunciation-hint').count(), 0)
        word.click()
        offline_page.locator('.pronunciation-hint').wait_for(timeout=8000)
        offline_page.locator('.word-button').nth(1).click()
        self.assertEqual(offline_page.locator('.pronunciation-hint').count(), 0)
        self.assertFalse(any('.zip' in path or '.mp3' in path for path in offline_page.evaluate('window.__requests')))
        self.assertFalse(errors, errors)

    def test_new_words_zip_reuses_unchanged_pack_zip(self):
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        self.mount(page)
        page.evaluate("location.hash='#packs'")
        page.evaluate("document.querySelector('.download-primary').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('pronta')")
        saved = page.evaluate('Object.fromEntries(window.__store)')
        cached = page.evaluate('window.__savedCache()')
        # Release a changed phonetic dictionary, WITHOUT changing pack/animes.zip.
        import copy
        updated_manifest = copy.deepcopy(self.jsons['archives/manifest.json'])
        voice = updated_manifest['voices']['en-US-AndrewNeural']
        old_pack = voice['packs']['animes']['sha256']
        base = 'tts/andrew_neural_en-us/'
        mp3 = b'ID3'+b'\x00'*600
        newest = zip_bytes({base+'hello.mp3':mp3, base+'world.mp3':mp3,
            'pronunciations-en-US.json':json.dumps({'locale':'en-US',
                'words':{'hello':'ha-LÔU','world':'UÂRLD','value':'VÉL-iu'}}).encode()})
        voice['words'] = meta(newest, 'words-andrew.zip')
        self.assertEqual(voice['packs']['animes']['sha256'], old_pack)
        zips = dict(self.zips)
        zips['archives/words-andrew.zip'] = base64.b64encode(newest).decode()
        hashes = dict(self.hash_by_size)
        hashes[str(len(newest))] = list(hashlib.sha256(newest).digest())
        jsons = dict(self.jsons)
        jsons['archives/manifest.json'] = updated_manifest
        next_page = context.new_page()
        self.mount(next_page, saved=saved, cached=cached,
                   jsons_override=jsons, zips_override=zips, hashes_override=hashes)
        next_page.evaluate("location.hash='#packs'")
        next_page.locator('#packsView').wait_for(state='visible')
        next_page.evaluate("document.querySelector('.download-primary').click()")
        next_page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('pronta')")
        self.assertEqual(next_page.evaluate("window.__requests.filter(x=>x.endsWith('.zip'))"),
                         ['archives/words-andrew.zip'])

    def test_remove_one_voice_keeps_other(self):
        context=self.browser.new_context();self.addCleanup(context.close)
        page=context.new_page()
        self.mount(page)
        page.evaluate("location.hash='#packs'")
        page.locator('#packsView').wait_for(state='visible')
        page.evaluate("document.querySelector('.download-primary').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('pronta')")
        page.evaluate("e=>{const n=document.querySelector('.pack-voice-select');n.value=e;n.dispatchEvent(new Event('change',{bubbles:true}))}", 'en-US-AvaNeural')
        page.evaluate("document.querySelector('.download-primary').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('Ava')")
        page.evaluate("document.querySelector('.pack-card .delete').click()")
        page.wait_for_function("document.querySelector('.pack-download-status')?.textContent?.includes('voz(es) baixada(s)')")
        page.evaluate("location.hash='#library'")
        self.assertIn('Disponível offline',page.locator('.story-card').first.inner_text())
        page.locator('.story-card').first.click()
        page.locator('.word-button').first.wait_for()
        self.assertEqual(page.locator('#voiceSelect').input_value(),'cloud:en-US-AndrewNeural')

    def test_old_andrew_cache_is_migrated_when_checksums_match(self):
        context = self.browser.new_context();self.addCleanup(context.close)
        page=context.new_page()
        v=self.jsons['archives/manifest.json']['voices']['en-US-AndrewNeural']
        saved={'storyspeak-offline-installed-v27':json.dumps({
            'words':v['words']['sha256'], 'packs':{'animes':v['packs']['animes']['sha256']}})}
        legacy={'archives/words.zip':self.zips['archives/words-andrew.zip'],
                'archives/animes.zip':self.zips['archives/animes-andrew.zip']}
        self.mount(page, saved=saved, legacy_cached=legacy, offline=True)
        self.assertIn('Disponível offline',page.locator('.story-card').first.inner_text())
        page.evaluate("location.hash='#read/test'")
        page.locator('.word-button').first.wait_for(timeout=8000)
        self.assertEqual(page.locator('#voiceSelect').input_value(),'cloud:en-US-AndrewNeural')
        self.assertFalse(any(x.endswith('.zip') for x in page.evaluate('window.__requests')))


if __name__=='__main__':unittest.main()
