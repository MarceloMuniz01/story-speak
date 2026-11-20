# StorySpeak v20 — Leitor de inglês offline

PWA estática com textos em inglês, leitura por frase, pronúncia, tradução por palavra, modo escuro e pesquisa por nível/categoria. **Não há backend**.

## Download no celular

Em **Downloads**, escolha a coleção e a voz e toque em **Baixar coleção**.
O StorySpeak salva o texto, os MP3 publicados para aquela voz e as traduções das palavras.
Áudios e traduções são compartilhados entre todas as coleções: uma palavra já salva é reutilizada.

- As **624 palavras diferentes das 12 histórias originais** estão traduzidas no glossário do próprio projeto (`dictionary.js`). Depois de instalar/atualizar a PWA, essas traduções funcionam sem internet. O significado isolado pode variar conforme o contexto.
- Para **histórias novas**, o assistente Python acrescenta automaticamente ao `dictionary.js` as palavras inéditas, com até três sentidos separados por `;` quando a fonte oferece alternativas. Sem internet ou com limite da API, o aplicativo ainda pode buscar e guardar traduções faltantes quando o usuário baixar a coleção.
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

O atualizador escolhe o ZIP StorySpeak mais recente de `/sdcard/Download` (ou `~/storage/downloads`), copia os arquivos da aplicação e **não toca em `tts/`, `catalog.json`, `packs/` nem em `dictionary.js`**, por padrão.

Para indicar um ZIP específico:

```sh
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v20-atualizacao-segura.zip
```

Para instalar esta versão pela primeira vez, extraia o ZIP de **atualização segura** na pasta do projeto: ele já vem sem `tts/`, `catalog.json`, `packs/` e `dictionary.js`.

```sh
unzip -o /sdcard/Download/storyspeak-v20-atualizacao-segura.zip -d .
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

Ao confirmar o cadastro, o assistente **atualiza o dicionário automaticamente** usando a API pública MyMemory. Quando a API fornece traduções distintas para a mesma palavra, elas são separadas por `;` (até três por padrão):

```js
"right": "certo; direita"
```

Se já existir uma tradução no glossário, ela é preservada. Os novos pares são adicionados em um bloco gerado no final de `dictionary.js`, sem reformatar o dicionário original. O script faz uma consulta por palavra nova, sem gerar falsos sentidos para preencher o limite. Nem todos os significados possíveis estarão sempre disponíveis; as sugestões dependem da fonte e podem ser imprecisas.

Se faltar internet ou atingir o limite da API, a história permanece salva. Para continuar depois:

```sh
python scripts/atualizar_dicionario.py
python scripts/atualizar_dicionario.py --limite 20   # traduzi apenas as próximas 20 palavras
```

Para cadastrar sem consultar a API naquele momento:

```sh
python scripts/adicionar_historia.py --sem-traducao
```

Após adicionar histórias, gere os MP3 faltantes com `python scripts/gerar_tudo.py`. Publique `catalog.json`, `packs/`, **`dictionary.js`** e `tts/` no GitHub Pages. A PWA busca a versão mais recente do dicionário online e mantém a última versão em cache para uso offline.

## Hospedagem

Tudo funciona com arquivos estáticos: GitHub Pages ou outro host HTTPS. Publique `index.html`, `app.js`, `styles.css`, `dictionary.js`, `sw.js`, `catalog.json`, `packs/`, `assets/` e `tts/`. A voz neural online não é necessária para áudios MP3 já baixados; falhas da API de voz têm fallback nativo.

## Verificações

```sh
node --check app.js
node --check sw.js
node tests/test_frontend.cjs
python tests/test_gerar_tudo.py
python tests/test_dictionary.py
python tests/test_maintenance.py
python tests/test_browser.py   # se houver Playwright e Chromium
```
