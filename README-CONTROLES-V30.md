# StorySpeak v30 — Controles de áudio sem deslocamento

## Ajuste visual

- Move **▶ Ouvir história inteira** para dentro da área de controles do leitor, onde antes aparecia **■ Parar áudio**.
- Deixa **■ Parar áudio** imediatamente à direita de **▶ Ouvir história inteira** durante a reprodução de palavra, frase, teste de voz ou história inteira.
- Quando nenhum áudio está tocando, **Parar áudio** fica invisível e desativado, mas seu espaço permanece reservado. Isso evita que o surgimento e o desaparecimento do botão provoquem deslocamentos no texto.
- Mantém os controles lado a lado mesmo em telas pequenas, sem adicionar botões nem alterar o comportamento de reprodução.
- Atualiza o cache do Service Worker para `storyspeak-reader-v30`, sem alterar as chaves dos ZIPs offline ou do `localStorage`.

## Atualização segura pelo Termux

Baixe o ZIP e execute:

```sh
cd ~/story-speak
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v30-controles-audio.zip
python scripts/empacotar_offline.py
surge dist/ story-speak.surge.sh
```

Somente `index.html`, `styles.css`, `app.js` e `sw.js` são alterados. A atualização **não** contém arquivos MP3, histórias, `catalog.json`, `dictionary.js`, arquivos de pronúncia nem scripts de geração.

Não há necessidade de regenerar MP3 ou de baixar novamente os pacotes das categorias, desde que seu conteúdo não tenha mudado. Basta a PWA receber o novo código.

## Verificações

Testado com o leitor simulado em Chromium nas larguras de 320, 360, 390, 768 e 1040 px: botão Parar à direita, ausência de rolagem horizontal, nenhuma mudança de posição do texto ao iniciar ou parar áudio. Os testes de downloads, múltiplas vozes, preferências e pronúncia da versão anterior também passaram.
