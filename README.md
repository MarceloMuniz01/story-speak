# StorySpeak v17 — Leitor de inglês simples

Site/PWA estático: histórias em inglês, tradução por palavra, voz por frase,
voz para o texto inteiro, escolha de voz e modo escuro.

## Iniciar

Publique os arquivos na raiz do GitHub Pages ou teste com um servidor local:

```sh
python -m http.server 8000
```

Abra `http://localhost:8000` no navegador. Para instalar a PWA no celular,
use HTTPS (por exemplo, GitHub Pages).

## Gerar todos os áudios com **um só comando**

No Termux, dentro do projeto:

```sh
python -m pip install -r requirements-tts.txt
python scripts/gerar_tudo.py
```

O comando padrão usa a voz **Andrew (en-US)** e percorre os 4 packs, gerando:

- `tts/andrew_en-us/*.mp3`: palavras únicas das histórias.
- `tts/andrew_en-us/packs/<pack>/<historia>/s0001.mp3` etc.: frases.
- `tts/andrew_en-us/packs/<pack>/<historia>/full.mp3`: histórias completas.

O mesmo comando pode ser repetido: ignora os MP3 já validados, retoma falhas,
e atualiza `tts/generated.json` e `tts/index.json` automaticamente.

Para gerar apenas uma coleção ou usar outra voz:

```sh
python scripts/gerar_tudo.py --pack everyday
python scripts/gerar_tudo.py --voice sonia
```

Para ver os MP3 pendentes **sem usar a internet**:

```sh
python scripts/gerar_tudo.py --status
```

Se você **já tinha MP3 gerados pelas versões anteriores**, mas sem registro
em `tts/generated.json`, pode aproveitá-los sem gerar novamente:

```sh
python scripts/gerar_tudo.py --aproveitar-existentes
```

Esse comando não confirma pelo ouvido qual voz está gravada; utilize-o somente
para MP3 cuja origem você conhece. Áudios com hash divergente são preservados
para geração ou revisão, não adotados automaticamente.

Se o serviço online estiver instável, use uma geração mais tranquila:

```sh
python scripts/gerar_tudo.py --workers 1 --delay 2
```

O gerador precisa de internet, respeita limitações do provedor, grava arquivos
parciais de maneira segura e pode ser interrompido com Ctrl+C. Antes de
redistribuir publicamente os áudios da Microsoft, verifique os termos aplicáveis.

## Baixar uma coleção no celular

Entre em **Downloads**, selecione a voz e toque em **Baixar coleção**.
A PWA guarda o texto e **todos os áudios disponíveis da voz** (história inteira,
frases e palavras) para uso offline. Isso não chama a API neural externa.
Se faltarem MP3 publicados, o app informa quantos foram salvos e permite
completar depois.

A publicação deve incluir **toda a pasta `tts/`**, especialmente os MP3 e
`tts/index.json`. Arquivos do Termux não ficam visíveis no GitHub Pages até você
publicá-los. O cache do navegador pode ser limpo pelo sistema.

Ao clicar para ouvir um áudio ausente, o app tenta a API neural online; se
ela falhar, usa o TTS do aparelho. Nenhuma geração online é executada ao abrir,
pesquisar ou baixar uma coleção.

## Verificações

```sh
python tests/test_gerar_tudo.py
node --check app.js
node --check sw.js
node tests/test_frontend.cjs
```

Mantidos: 12 histórias, níveis A1–C1, busca e filtro por categoria. Todo o
front-end usa JavaScript puro, sem dependências ou backend.
