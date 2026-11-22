# StorySpeak v27 — leitura offline em coleções ZIP

Leitor PWA estático para estudar inglês com tradução por palavra, pronúncia normal e lenta, áudio por frase e história, filtros, busca e tema claro/escuro.

O usuário **baixa uma coleção antes de lê-la**. Não há modo de leitura online. Cada coleção chega em um ZIP próprio (`archives/animes.zip`, `archives/everyday.zip`, etc.), enquanto `archives/words.zip` fornece o áudio compartilhado de palavras uma única vez. Os arquivos são armazenados na Cache Storage do navegador. As preferências de tema, voz, velocidade, nível e categoria ficam no `localStorage` e são restauradas ao reabrir a PWA.

A voz padrão é **`en-US-AndrewNeural`**, não a variante multilíngue. O frontend não usa API de TTS nem faz requisições individuais de MP3. Ele lê os áudios diretamente dos ZIPs por JSZip. A tradução usa `dictionary.js`, atualizado localmente pelo WikDict sem chave de API.

## Termux

```sh
cd ~/story-speak
python scripts/gerar_tudo.py --status      # conferir MP3 pendentes
python scripts/gerar_tudo.py               # completar MP3 que faltam
python scripts/empacotar_offline.py        # montar dist/ com words.zip + <pack>.zip
surge dist/ story-speak.surge.sh           # publicar somente dist/
```

O empacotador exige todos os MP3 validados; se a síntese falhar com `NoAudioReceived`, ele recusará gerar uma publicação incompleta. `dist/` é reconstruído sem publicar MP3 isolados, scripts Python, metadados de geração ou arquivos desnecessários.

O código aplica **DRY/KISS**: o script de áudio existente é a fonte de verdade para os caminhos e a segmentação, há um único empacotador, um gerenciador de downloads no frontend e um único objeto para preferências do usuário. Os ZIPs preservam os arquivos originais em `tts/`.

**Instalação da atualização:** `python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v27-leitura-offline-zip.zip`. O atualizador não substitui `catalog.json`, `packs/`, `dictionary.js` nem `tts/`.

Documentação completa e observações sobre armazenamento: [README-OFFLINE-V27.md](README-OFFLINE-V27.md).
