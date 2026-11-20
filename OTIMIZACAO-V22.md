# StorySpeak v22 — Scripts otimizados (Termux)

Esta atualização modifica somente os scripts Python. **Não apaga MP3, `tts/`, histórias, `packs/`, `catalog.json` ou `dictionary.js`.** O ZIP de scripts não contém esses arquivos.

## Usar normalmente

```bash
cd ~/story-speak
python -m pip install -U -r requirements-tts.txt
python scripts/atualizar_dicionario.py
python scripts/gerar_tudo.py
```

- Tradução: até **3 consultas paralelas** com intervalo global de **0,4 s** entre inícios (antes: serial, 0,8 s); os resultados são salvos em checkpoints.
- Áudio: até **3 gerações paralelas** com intervalo global de **0,5 s** (antes: 2 e 0,8 s); MP3 válidos são preservados, sem regeneração.
- O importador de histórias usa o mesmo tradutor acelerado.
- O índice de áudio agora carrega os packs uma vez por execução, em vez de uma vez por voz.
- Falhas temporárias na tradução recebem uma tentativa adicional; HTTP 401/403/429 ou quota interrompem o envio de novas requisições. No áudio, os retries e a interrupção por bloqueio continuam ativos.

## Ajustar velocidade (com cuidado)

Mais conservador em caso de instabilidade:

```bash
python scripts/gerar_tudo.py --workers 1 --delay 2
python scripts/atualizar_dicionario.py --workers 1 --pausa 1
```

Mais rápido, **somente se o serviço estiver respondendo normalmente**:

```bash
python scripts/gerar_tudo.py --workers 4 --delay 0.4
python scripts/atualizar_dicionario.py --workers 4 --pausa 0.25
```

Esses são limites de concorrência do script, **não garantias de que o serviço aceitará essa frequência**. Se houver limitação, diminua a concorrência e aguarde; não use a configuração rápida para contornar bloqueios.

Atualização de palavras novas ao importar histórias:

```bash
python scripts/adicionar_historia.py --arquivo minha-historia.json
```

Para importar sem consultar tradução imediatamente:

```bash
python scripts/adicionar_historia.py --arquivo minha-historia.json --sem-traducao
```

Para retomar em qualquer momento, execute o mesmo comando; itens já salvos são ignorados. Não use `--force` em áudio a menos que queira substituir MP3s válidos. Você pode ver os pendentes sem usar a rede:

```bash
python scripts/gerar_tudo.py --status
```

**Instalação:** descompacte `storyspeak-v22-scripts-rapidos.zip` diretamente em `~/story-speak`, preservando a estrutura `scripts/`. Seu diretório `tts/` não está dentro do ZIP.

**Limites:** o processamento local é menor, mas latência, indisponibilidade, quota e política de uso dos serviços remotos continuam sendo os principais gargalos. Verifique as condições de uso/licença dos áudios antes de publicar.
