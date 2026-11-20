STORYSPEAK v25 — ANDREW INGLÊS AMERICANO (NÃO MULTILÍNGUE)

Voz anterior: en-US-AndrewMultilingualNeural
Nova voz:     en-US-AndrewNeural

Áudios anteriores permanecem em: tts/andrew_en-us/
Áudios novos serão criados em:   tts/andrew_neural_en-us/

Não copie os MP3 antigos para a pasta nova: eles continuariam multilíngues.

ATUALIZAR (dentro de ~/story-speak):
  python scripts/atualizar_projeto.py /sdcard/Download/storyspeak-v25-andrew-us-atualizacao.zip

GERAR TODAS AS PALAVRAS, FRASES E HISTÓRIAS NA NOVA VOZ:
  python scripts/gerar_tudo.py --status
  python scripts/gerar_tudo.py

ATUALIZAR INDEX E PUBLICAR:
  python scripts/gerar_tudo.py --reindex
  git add .
  git commit -m "Switch Andrew TTS to en-US-AndrewNeural"
  git push

O site não utilizará MP3 da voz antiga para esta nova voz. Se a API de
terceiros não tiver AndrewNeural, o fallback será TTS nativo do Android.
