# StorySpeak v28 — várias vozes, ZIPs offline e DRY/KISS

## Mudanças

- O empacotador **descobre** vozes com MP3 completos, usando `VOICES` em `scripts/audio_common.py`. Não precisa editar o JavaScript para adicionar um pack a uma voz já cadastrada.
- `archives/manifest.json` versão 2: para cada voz há um `words-<voz>.zip` e um `<categoria>-<voz>.zip` por categoria completa.
- MP3s usam `ZIP_STORED`, porque já são comprimidos; JSONs usam DEFLATE. Todos os arquivos ZIP são verificados (CRC, tamanho e SHA-256).
- Uma voz **parcialmente gerada** aparece apenas nas categorias em que todas as palavras, frases e histórias estão disponíveis com hash correto; categorias incompletas são ignoradas com segurança.
- Em Downloads, escolha a voz por categoria. É possível baixar várias vozes, mudar entre as instaladas no leitor e excluir somente o ZIP de uma voz. Palavras permanecem compartilhadas entre categorias, separadas por voz.
- A biblioteca só abre histórias de categorias que possuam ao menos uma voz baixada. A reprodução usa os MP3 dentro dos ZIPs, sem requisitar arquivos soltos à internet. A voz nativa do aparelho continua opcional.
- Preferências ficam em `localStorage` na chave estável `storyspeak-preferences-v1`: voz, velocidade, tema, nível e categoria.
- Quando o SHA-256 dos ZIPs antigos coincide com os novos, downloads de Andrew da v27 são aproveitados, sem baixar de novo. Arquivos com conteúdo diferente exigem atualização.
- Atualização preserva `tts/`, `dictionary.js`, `catalog.json` e `packs/` do usuário.

## Atualizar no Termux

Coloque o ZIP de atualização na pasta Download do Android:

```sh
cd ~/story-speak
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v28-multivozes.zip
```

**Não apague `tts/`**: outras vozes usam caminhos diferentes, e o índice mantém hashes separados.

## Gerar mais vozes

As vozes cadastradas por padrão são `andrew` (Andrew en-US), `ava` (Ava en-US), `sonia` (Sonia en-GB) e `ryan` (Ryan en-GB).

Por exemplo, para adicionar Ava **somente em Animes**:

```sh
python scripts/gerar_tudo.py --voice ava --pack animes --teste-voz
python scripts/gerar_tudo.py --voice ava --pack animes
```

As opções `--voice`, `--pack` e `--status` já fazem parte do gerador anterior. Para saber o que falta:

```sh
python scripts/gerar_tudo.py --voice ava --pack animes --status
```

Para gerar Ava em **todas** as categorias:

```sh
python scripts/gerar_tudo.py --voice ava
```

É necessário que o serviço de TTS aceite a voz escolhida. Erros como `NoAudioReceived` podem impedir a conclusão, mas os MP3 já válidos são reaproveitados nas próximas execuções.

## Empacotar e publicar

```sh
python scripts/empacotar_offline.py
surge dist/ story-speak.surge.sh
```

`empacotar_offline.py` procura todas as vozes automaticamente. Só publica pares **voz + categoria** completos. Se nenhuma voz estiver completa para nenhuma categoria, a publicação é interrompida e a versão anterior de `dist/` permanece intacta.

Para empacotar apenas algumas vozes:

```sh
python scripts/empacotar_offline.py --voice andrew --voice ava
```

Para exigir que cada voz selecionada tenha **todas** as categorias, ative `--strict`:

```sh
python scripts/empacotar_offline.py --voice ava --strict
```

Saída exemplo (se Andrew tiver todas as categorias e Ava apenas Animes):

```text
dist/
  archives/
    manifest.json
    words-andrew.zip
    everyday-andrew.zip
    animes-andrew.zip
    ...
    words-ava.zip
    animes-ava.zip
  index.html
  app.js
  ...
```

A publicação deve ser feita **somente de `dist/`**, nunca da pasta principal (`surge .`). Isso evita publicar os MP3 soltos, scripts de manutenção e arquivos auxiliares.

## Migração e armazenamento

- v28 usa nova versão do manifesto (`version: 2`) e novo espaço em Cache Storage, para separar downloads por voz.
- Downloads antigos do Andrew podem ser migrados automaticamente **somente quando o hash dos ZIPs coincidir**.
- O site mantém as preferências com a chave estável `storyspeak-preferences-v1`.
- A remoção de uma voz de uma coleção **não apaga o ZIP de palavras** daquela voz nem as outras vozes instaladas.
- A troca de domínio (GitHub Pages → Surge) **não transfere** `localStorage` nem Cache Storage do navegador entre domínios.
- O navegador pode limpar armazenamento sob pressão de espaço; instalar a PWA não garante permanência absoluta.

## Testes incluídos

Os testes de pacote são locais, sem API:

```sh
python -m unittest discover -s tests -p 'test_multivoice_archives.py' -v
```

Para testar a PWA com Chromium + Playwright, em um ambiente que tenha essas ferramentas:

```sh
python -m unittest discover -s tests -p 'test_multivoice_pwa.py' -v
```
