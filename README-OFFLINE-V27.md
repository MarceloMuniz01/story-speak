# StorySpeak v27 — leitor somente offline por pacotes ZIP

## O que mudou

- Não existe mais leitura online: só é possível abrir uma história quando a categoria foi baixada.
- `archives/words.zip`: pronúncias de palavras únicas, compartilhadas por todas as coleções (baixado uma vez).
- `archives/<id>.zip` (por exemplo `animes.zip`): inclui `packs/<id>.json`, áudios completos e áudios por frase. Uma única requisição HTTP para cada pacote.
- ZIP usa `ZIP_STORED` nos MP3 (que já são comprimidos) e `ZIP_DEFLATED` nos JSON. A vantagem principal é reduzir o número de conexões, não o tamanho dos MP3.
- O browser guarda cada ZIP inteiro na **Cache Storage** da PWA. Não extrai centenas de arquivos para caches individuais.
- `archives/manifest.json` guarda SHA-256 e tamanho, permitindo verificar integridade e detectar versões novas.
- O leitor abre os arquivos dos ZIPs localmente por meio do JSZip, já incluído em `vendor/`; nunca requisita MP3 soltos na internet.
- `localStorage` guarda preferências **separadas dos ZIPs**: tema, voz, velocidade, nível e categoria. A chave estável é `storyspeak-preferences-v1`; configurações antigas de tema, voz e velocidade são migradas na primeira abertura.
- O modo escuro, a pronúncia normal/lenta por toque, reprodução por frase/história, tradução por palavra, filtros, pesquisa, instalação PWA e fallback de voz nativa foram mantidos.

## Instalar com segurança no Termux

Baixe `storyspeak-v27-leitura-offline-zip.zip` na pasta Downloads e execute:

```sh
cd ~/story-speak
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v27-leitura-offline-zip.zip
```

O atualizador **preserva** suas histórias (`catalog.json`, `packs/`), `dictionary.js` e todos os MP3 em `tts/` (inclusive os áudios antigos). O ZIP também pode ser descompactado diretamente na raiz do projeto, pois só contém os arquivos de atualização.

## Produzir os ZIPs e publicar no Surge

```sh
cd ~/story-speak
python scripts/gerar_tudo.py --status
python scripts/gerar_tudo.py            # complete os MP3 ausentes
python scripts/empacotar_offline.py      # gera dist/archives/*.zip e dist/archives/manifest.json
surge dist/ story-speak.surge.sh         # publique SOMENTE dist/
```

**Não execute `surge .`**: isso publicaria os MP3 individuais, scripts e arquivos de trabalho. `dist/` contém somente o site, o índice e os ZIPs.

O empacotador exige **todos os MP3 válidos** para a voz `en-US-AndrewNeural` e um hash correspondente em `tts/generated.json`. Se faltar um, ele interrompe a publicação e lista exemplos, **sem substituir a pasta `dist/` já existente**. Se a síntese com `edge-tts` continuar retornando `NoAudioReceived`, resolva essa falha antes de criar os ZIPs. Não use MP3 de `AndrewMultilingual` disfarçados como `AndrewNeural`.

Se você adicionou a coleção `animes` ao seu catálogo, o empacotador criará `animes.zip` automaticamente. Os nomes dos arquivos vêm dos IDs reais das categorias, não de uma lista codificada no script.

## Como o usuário baixa e lê

1. Abra a aba **Downloads** da PWA.
2. Toque em **Baixar coleção** (por exemplo, Animes).
3. O primeiro download baixa `words.zip` + `animes.zip` (2 requisições). Os próximos baixam apenas o ZIP da categoria (1 requisição).
4. Depois de concluído, a categoria fica disponível na **Biblioteca**, com internet ou offline.
5. **Excluir download** remove somente aquele ZIP; o vocabulário compartilhado permanece.

Os ZIPs ficam no armazenamento do navegador (Cache Storage) e **não** na pasta Downloads do Android. Limpar os dados do navegador ou remover a PWA pode apagá-los. A PWA solicita armazenamento persistente quando possível, mas o navegador pode recusá-lo.

Atualizações de uma coleção podem exigir o download do novo ZIP; o sistema distingue versões pelo SHA-256. O tema, a voz e a velocidade continuam registrados no `localStorage` do mesmo domínio. Ao mudar de domínio (por exemplo, GitHub Pages para Surge), preferências e caches não são transferidos automaticamente.

## Diagnóstico

```sh
python scripts/gerar_tudo.py --status
python scripts/empacotar_offline.py
ls -lh dist/archives/
```

Para instalar o CLI Surge no Termux, `node` e `npm` devem funcionar primeiro. Se aparecer o erro de ICU (`libicui18n.so.79`), atualize os pacotes do Termux antes de tentar o `npm install -g surge`.
