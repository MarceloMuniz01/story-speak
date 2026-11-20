# StorySpeak v19 — Leitor de inglês offline

PWA estática com textos em inglês, leitura por frase, pronúncia, tradução por palavra, modo escuro e pesquisa por nível/categoria. **Não há backend**.

## Download no celular

Em **Downloads**, escolha a coleção e a voz e toque em **Baixar coleção**.
O StorySpeak salva o texto, os MP3 publicados para aquela voz e as traduções das palavras.
Áudios e traduções são compartilhados entre todas as coleções: uma palavra já salva é reutilizada.

- As **624 palavras diferentes das 12 histórias originais** estão traduzidas no glossário do próprio projeto (`dictionary.js`). Depois de instalar/atualizar a PWA, essas traduções funcionam sem internet. O significado isolado pode variar conforme o contexto.
- Para **histórias novas** adicionadas pelo usuário, o download usa traduções locais existentes e, para palavras ausentes, consulta a API pública MyMemory somente após o toque em Baixar. Salva o resultado no navegador para uso offline; não faz geração automática de áudio pela API.
- Se o provedor limitar o uso ou estiver offline, o aplicativo informa quantas traduções e quantos áudios faltaram. Um novo toque em **Completar download** tenta apenas os pendentes.
- Não é possível garantir que o navegador mantenha os dados para sempre: limpar dados ou liberar espaço pode remover os downloads.

A tradução por palavra também funciona ao tocar na palavra enquanto há conexão; essa tradução é armazenada para a próxima vez.

## Um único comando para gerar todos os áudios

```sh
python -m pip install -r requirements-tts.txt
python scripts/gerar_tudo.py
```

O gerador usa Andrew (`en-US-AndrewMultilingualNeural`) por padrão e percorre todas as histórias, frases e palavras. Não repete arquivos válidos. Outros exemplos:

```sh
python scripts/gerar_tudo.py --status
python scripts/gerar_tudo.py --pack everyday
python scripts/gerar_tudo.py --voice sonia
python scripts/gerar_tudo.py --aproveitar-existentes
```

Os arquivos ficam em `tts/<voz>/`, as frases em `tts/<voz>/packs/<categoria>/<historia>/` e o índice em `tts/index.json`. Somente publique MP3 caso tenha os direitos de redistribuição aplicáveis.

## Atualizar pelo Termux sem perder MP3 nem histórias

Na raiz do seu projeto (`~/story-speak`), após ter o script instalado:

```sh
python scripts/atualizar_projeto.py
```

O atualizador escolhe o ZIP StorySpeak mais recente de `/sdcard/Download` (ou `~/storage/downloads`), copia os arquivos da aplicação e **não toca em `tts/`, `catalog.json` e `packs/`**, por padrão.

Para indicar um ZIP específico:

```sh
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v19-atualizacao-segura.zip
```

Para instalar esta versão pela primeira vez, extraia o ZIP de **atualização segura** na pasta do projeto: ele já vem sem `tts/`, `catalog.json` e `packs/`.

```sh
unzip -o /sdcard/Download/storyspeak-v19-atualizacao-segura.zip -d .
```

## Adicionar histórias e categorias

```sh
python scripts/adicionar_historia.py
```

Escolha uma categoria existente ou crie outra. Cole uma história em inglês e digite `:fim` em linha própria; o assistente pergunta título, nível, gênero, resumo e tags.

Também aceita JSON colado (digite `:fim` depois) ou arquivos:

```sh
python scripts/adicionar_historia.py --arquivo /sdcard/Download/historia.json
python scripts/adicionar_historia.py --arquivo /sdcard/Download/historia.txt
```

JSON mínimo:

```json
{"title":"A Rainy Evening","level":"B1","genre":"Mystery","summary":"A surprise after the rain","tags":["rain","mystery"],"text":"It was a quiet evening. The door opened."}
```

Após adicionar novas histórias, gere os MP3 faltantes com `python scripts/gerar_tudo.py`, publique `catalog.json`, `packs/` e `tts/` no GitHub Pages. O app detecta as palavras novas durante o download e busca apenas as traduções ainda não salvas.

## Hospedagem

Tudo funciona com arquivos estáticos: GitHub Pages ou outro host HTTPS. Publique `index.html`, `app.js`, `styles.css`, `dictionary.js`, `sw.js`, `catalog.json`, `packs/`, `assets/` e `tts/`. A voz neural online não é necessária para áudios MP3 já baixados; falhas da API de voz têm fallback nativo.

## Verificações

```sh
node --check app.js
node --check sw.js
node tests/test_frontend.cjs
python tests/test_gerar_tudo.py
python tests/test_browser.py   # se houver Playwright e Chromium
```
