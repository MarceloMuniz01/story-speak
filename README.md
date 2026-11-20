# StorySpeak v25 — Andrew americano (não multilíngue)

O StorySpeak é uma PWA estática de leitura em inglês: áudios por palavra/frase/história, tradução offline (WikDict), categorias, pesquisa, modo escuro e coleções para baixar no Android.

## A mudança de voz

- **Padrão:** `en-US-AndrewNeural` (em vez de `en-US-AndrewMultilingualNeural`).
- **Nova pasta:** `tts/andrew_neural_en-us/`.
- **Antiga pasta:** `tts/andrew_en-us/`, com seus MP3 multilíngues, permanece intacta e não é usada como fonte da nova voz.
- A voz padrão é identificada pelo *nome exato da voz*, não pelo ID da API (`voice-107` era a voz antiga). O índice e cache do navegador também distinguem as variantes.
- Outras vozes en-US/en-GB podem continuar disponíveis, mas a variante **Andrew Multilingual** não é exibida nem usada.

## Atualizar no Termux (sem perder arquivos)

Coloque o ZIP `storyspeak-v25-andrew-us-atualizacao.zip` em `/sdcard/Download` e rode na raiz do repositório:

```sh
cd ~/story-speak
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v25-andrew-us-atualizacao.zip
```

O atualizador preserva `tts/`, `dictionary.js`, `packs/` e `catalog.json`. Alternativamente, use `unzip -o <arquivo.zip> -d .` porque este ZIP de atualização **não contém** essas pastas ou arquivos protegidos.

## Gerar a nova voz (histórias + frases + palavras)

```sh
python -m pip install -r requirements-tts.txt
python scripts/gerar_tudo.py --voice andrew --status
python scripts/gerar_tudo.py --voice andrew
```

O gerador percorre **todas as coleções cadastradas** (incluindo `animes` se já estiver no seu catálogo), cria somente os arquivos ausentes e atualiza `tts/index.json`. Também mantém os registros antigos em `tts/generated.json` sem confundir as duas vozes.

Para gerar uma coleção apenas:

```sh
python scripts/gerar_tudo.py --voice andrew --pack animes
```

Se houver falhas do serviço, rode o mesmo comando novamente; não é preciso apagar os MP3 válidos. Não use `--adopt-existing` com arquivos de origem/voz desconhecida. **Não mova os MP3 da pasta antiga para a nova:** isso só trocaria o nome do arquivo, não a pronúncia.

## Publicar as mudanças

```sh
git add app.js index.html sw.js scripts/audio_common.py README.md README-ANDREW-US.txt tts/index.json tts/generated.json tts/andrew_neural_en-us/
git commit -m "Use Andrew Neural en-US instead of Multilingual"
git push
```

O `index.json` lista só áudios que correspondam ao texto e à voz declarados. Antes da nova geração, áudios Andrew em inglês não aparecerão offline. Depois de publicar, recarregue a PWA para receber o Service Worker v25; se necessário, feche e reabra o aplicativo.

### API online e fallback

Se faltar MP3 e você tocar para ouvir, o leitor procura se o provedor online suporta `en-US-AndrewNeural`. **Não substitui silenciosamente por Andrew Multilingual.** Se esse provedor não oferecer a variante correta, usa a voz nativa do Android como fallback. A síntese e redistribuição dos arquivos devem respeitar os termos do serviço usado.

## Tradução offline

A versão v24 usa o dicionário WikDict para atualizar `dictionary.js` sem chave de API:

```sh
python scripts/atualizar_dicionario.py
```

Os scripts de tradução, as histórias e os MP3 antigos não são modificados pela atualização v25.
