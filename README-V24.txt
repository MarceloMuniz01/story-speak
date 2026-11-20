StorySpeak v24 — dicionário aberto, sem contas e sem chaves de API

ESTA É UMA ATUALIZAÇÃO SEGURA. NÃO CONTÉM tts/, dictionary.js,
packs/ NEM catalog.json. Mantém seus MP3 e suas histórias.

1) No Termux, dentro de ~/story-speak, extraia o ZIP:
   unzip -o /sdcard/Download/storyspeak-v24-wikdict-offline.zip -d .

2) Atualize o dicionário a partir das histórias que você já tem:
   python scripts/atualizar_dicionario.py

   Na primeira execução, o script baixa UM ZIP do WikDict (~3 MB) para
   data/wikdict-en-pt.zip; nas seguintes, usa esse arquivo local.
   Não há necessidade de token, login, Gemini, MyMemory ou pip install.

3) Para atualizar traduções automáticas ruins (sem tocar nas manuais):
   python scripts/atualizar_dicionario.py --revisar

   OBS: --revisar pode substituir TODOS os significados do bloco automático
   pelos significados do WikDict. Faça backup de dictionary.js antes de usar.

4) Para adicionar uma história (a tradução de palavras novas é automática):
   python scripts/adicionar_historia.py --arquivo s1.json

5) Para gerar os áudios das novas histórias:
   python scripts/gerar_tudo.py

6) Para publicar:
   git add scripts/ app.js index.html sw.js dictionary.js packs/ catalog.json \
     ATTRIBUTION-WIKDICT.md
   git commit -m 'Use offline WikDict for translations'
   git push

SE QUISER TRADUZIR SEM INTERNET LOGO NA PRIMEIRA EXECUÇÃO:
- Baixe pelo navegador do Android, em qualquer momento, a URL oficial:
  https://download.wikdict.com/dictionaries/stardict/wikdict-en-pt.zip
- Em seguida, use:
  python scripts/atualizar_dicionario.py \
    --wikdict /sdcard/Download/wikdict-en-pt.zip --sem-download

NOTAS:
- O script só acrescenta palavras novas. `--revisar` reavalia a parte
  automática; nunca altera traduções manuais/base.
- Algumas palavras não estão no WikDict; ficam pendentes sem tradução
  inventada. Conjugações, nomes de personagens e contrações podem faltar.
- Esta versão desativa a API MyMemory também na interface do navegador;
  o site mostra "Tradução ainda não disponível" quando o vocábulo não está
  no dictionary.js. Não muda o uso das vozes neurais.
- A fonte é en-pt geral e pode ter alguns usos de português europeu.
- Atribuição/licença em ATTRIBUTION-WIKDICT.md.
- Não foi possível validar o download real do ZIP WikDict neste ambiente;
  os testes de estrutura StarDict foram feitos com um arquivo simulado.
