# StorySpeak v29 — pronúncia intuitiva para brasileiros (offline)

## O que mudou

- **Primeiro toque em uma palavra:** ouve o MP3 normal e vê a tradução, exatamente como antes.
- **Segundo toque na mesma palavra:** ouve em velocidade lenta e vê uma pequena dica escrita, por exemplo `value → VÉL-iu`.
- **Terceiro toque:** esconde a dica e repete a pronúncia normal. Ao selecionar outra palavra, a dica anterior desaparece.
- Dicas baseadas no **CMU Pronouncing Dictionary** (inglês americano), convertidas por um algoritmo próprio para uma **aproximação de leitura para falantes de português**.
- O dicionário de pronúncias é pré-processado **no Termux**, não no navegador; entra dentro de cada `words-<voz>.zip` de vozes americanas.
- Andrew e Ava (en-US) usam as dicas. Sonia e Ryan (en-GB) não recebem transcrição americana, para evitar confusão de sotaques.
- **Nenhuma API, conta, internet durante a leitura, biblioteca Python ou novo MP3 é necessário.** O CMUdict já acompanha o ZIP da atualização em `scripts/data/cmudict.dict.gz` (~0,9 MB).
- A velocidade, voz e tema continuam no `localStorage`, sem mudar a chave `storyspeak-preferences-v1`.

## Como instalar

Transfira o ZIP da atualização para Downloads do Android e execute:

```sh
cd ~/story-speak
python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v29-pronuncia-br.zip
```

Opcionalmente, consulte um exemplo sem alterar os arquivos:

```sh
python scripts/gerar_pronuncias.py --palavra value
python scripts/gerar_pronuncias.py --palavra intention
python scripts/gerar_pronuncias.py
```

**Não execute `rm -rf tts` nem regenere MP3 para usar a função.** O empacotador adiciona automaticamente `pronunciations-en-US.json` aos ZIPs de palavras:

```sh
python scripts/empacotar_offline.py
surge dist/ story-speak.surge.sh
```

O empacotador precisa que pelo menos uma combinação **voz + categoria** tenha MP3 completos e validados. Se não tiver, gere somente os áudios faltantes com `python scripts/gerar_tudo.py` e tente novamente.

### Atualizações dos pacotes no navegador

A primeira atualização v29 muda o SHA-256 de `words-andrew.zip` e `words-ava.zip`; o usuário deverá atualizar os ZIPs de palavras dessas vozes.

**Não é necessário baixar o ZIP de histórias novamente quando não mudou:** a v29 verifica separadamente o ZIP de cada categoria e reaproveita os que já estão instalados.

O navegador guarda as preferências antigas e os ZIPs baixados (Cache Storage) no mesmo domínio. Usar outro domínio exige novos downloads.

## Observações sobre qualidade

A escrita é **uma aproximação didática**, nunca uma notação fonética precisa. Sons que não existem em português (como *th*, *r* americano e algumas vogais) só podem ser aproximados. **Escute sempre o MP3** para a pronúncia real. Evitamos representar algumas palavras com múltiplas leituras relevantes (`read`, `live`, `wind` etc.) sem conhecer seu contexto. Nomes próprios podem não existir no dicionário; nesses casos não aparece uma dica inventada.

A conversão utiliza regras próprias de ARPABET para português com poucas exceções revisadas (`value`, `decide`, `intention` etc.). Não incorpora nem redistribui código do repositório `ArthurGaspar/ipa-translator`, cuja licença de reutilização não foi identificada.

## Licença / atribuição

Fonte de pronúncias: **CMU Pronouncing Dictionary**, © 1993–2015 Carnegie Mellon University, sob condições BSD. Veja `scripts/data/LICENSE-CMUDICT.txt`.

- https://github.com/cmusphinx/cmudict
- https://github.com/ArthurGaspar/ipa-translator (referência conceitual, nenhum código copiado)

## Testes

```sh
python -m unittest discover -s tests -p 'test_pronunciation_hints.py' -v
python -m unittest discover -s tests -p 'test_multivoice_archives.py' -v
```

Os testes de navegador exigem Chromium e Playwright e são opcionais no Termux:

```sh
python -m unittest discover -s tests -p 'test_multivoice_pwa.py' -v
```
