"""Chromium UI integration test in a synthetic document (no real network)."""
from pathlib import Path
import json
import sys
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text().replace('<head>','<head><base href="https://storyspeak.test/">',1)
css=(ROOT/'styles.css').read_text()
app=(ROOT/'app.js').read_text()
dictionary=(ROOT/'dictionary.js').read_text()
catalog=json.loads((ROOT/'catalog.json').read_text())
packs={pack['file']:json.loads((ROOT/pack['file']).read_text()) for pack in catalog['packs']}
sys.path.insert(0,str(ROOT/'scripts'))
from gerar_tudo import collect
from audio_common import VOICES
_voice,_slug=VOICES['andrew']
tasks=collect({'everyday', 'technology'},_slug)
record={'dir':'tts/andrew_en-us','words':{},'stories':{}}
mp3paths=[]
for typ,path,spoken in tasks:
    relative=path.relative_to(ROOT).as_posix()
    mp3paths.append(relative)
    if typ=='palavras': record['words'][spoken]=relative
    else:
        story_id=path.parent.name
        detail=record['stories'].setdefault(story_id,{'sentences':[]})
        item={'text':spoken,'path':relative}
        if typ=='histórias':detail['full']=item
        else:detail['sentences'].append(item)
index={'version':1,'voices':{_voice:record}}
with sync_playwright() as p:
    b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=b.new_page(viewport={'width':390,'height':844})
    errs=[]
    page.on('pageerror',lambda e:errs.append(str(e)))
    page.set_content(html)
    page.add_style_tag(content=css)
    page.evaluate('''({catalog,packs})=>{
      const memory=new Map();
      window.__tts_index={version:1,voices:{}};
      window.__mp3_paths=new Set();
      window.__mp3_requests=[];
      Object.defineProperty(crypto,'subtle',{configurable:true,value:{digest:async (_alg,data)=>{
         const bytes=new Uint8Array(data),out=new Uint8Array(32);
         for(let i=0;i<bytes.length;i++)out[i%32]=(out[i%32]*31+bytes[i])%256;
         return out.buffer;
      }}});

      window.caches={open:async name=>({
        match:async key=>memory.get(name+'|'+(key?.url||key))?.clone()||undefined,
        put:async(key,value)=>{memory.set(name+'|'+(key?.url||key),value.clone())},
        delete:async key=>memory.delete(name+'|'+(key?.url||key))
      }),delete:async name=>{for(const key of memory.keys()) if(key.startsWith(name+'|')) memory.delete(key);return true},keys:async()=>[]};
      window.fetch=async (request)=>{
         const url=new URL(request?.url||request,document.baseURI),path=url.pathname.slice(1);
         let data=path==='catalog.json'?catalog:path==='tts/index.json'?window.__tts_index:packs[path];
         if(window.__mp3_paths.has(path)) {window.__mp3_requests.push(path);return new Response(new Uint8Array(600).fill(77),{status:200,headers:{'content-type':'audio/mpeg'}});}
         if(data) return new Response(JSON.stringify(data),{status:200,headers:{'content-type':'application/json'}});
         return new Response('missing',{status:404});
      };
    }''', {'catalog':catalog,'packs':packs})
    page.add_script_tag(content=dictionary)
    page.add_script_tag(content=app)
    page.locator('#storyList .story-card').first.wait_for(timeout=20000)
    assert page.locator('.story-card').count()==12
    page.evaluate("location.hash = '#packs'")
    first=page.locator('.pack-card').first
    assert first.locator('.download-primary').count()==1
    assert first.locator('.download-voice').count()==1
    assert first.locator('.download-mode').count()==0
    first.locator('.download-primary').click()
    page.wait_for_function("document.querySelector('.pack-card .pack-download-status')?.textContent?.includes('Traduções:')",timeout=15000)
    # No MP3 published in fixture: app should report partial, not call remote TTS
    assert '0/215' in first.locator('.pack-download-status').inner_text(), first.locator('.pack-download-status').inner_text()
    assert '183/183' in first.locator('.pack-download-status').inner_text(), first.locator('.pack-download-status').inner_text()
    # Publish all 215 items into the mocked static site and retry the incomplete pack.
    page.evaluate('''({index,paths})=>{window.__tts_index=index;window.__mp3_paths=new Set(paths)}''', {'index':index,'paths':mp3paths})
    first.locator('.download-primary').click()
    page.wait_for_function("document.querySelector('.pack-card .pack-download-status')?.textContent?.includes('tradução disponíveis offline')",timeout=35000)
    assert first.locator('.pack-download-status').inner_text().startswith('✓ Texto, áudio e tradução')
    # 'the' aparece em mais de uma coleção e deve fazer uma única requisição.
    assert page.evaluate("window.__mp3_requests.filter(x=>x==='tts/andrew_en-us/the.mp3').length") == 1
    second=page.locator('.pack-card').nth(1)
    second.locator('.download-primary').click()
    page.wait_for_function("document.querySelectorAll('.pack-card .pack-download-status')[1]?.textContent?.includes('tradução disponíveis offline')", timeout=35000)
    assert page.evaluate("window.__mp3_requests.filter(x=>x==='tts/andrew_en-us/the.mp3').length") == 1
    first.get_by_role('button',name='Excluir download').click()
    assert 'Inclui texto, áudios e tradução' in first.locator('.pack-download-status').inner_text()
    page.evaluate("location.hash = '#library'")
    page.locator('.story-card').first.click()
    page.locator('.sentence-play').first.wait_for()
    assert page.locator('.sentence-play').count()>=2
    assert page.locator('.word-button').count()>10
    page.screenshot(path=str(ROOT.parent/'storyspeak-v17-mobile.png'),full_page=True)
    assert not errs,errs
    print('OK: browser offline 183 translations, shared audio, 215 audio files, delete, reader')
    b.close()
