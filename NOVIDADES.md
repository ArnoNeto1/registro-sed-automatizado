# Novidades

Este arquivo é a fonte das notas que cada professor lê quando o programa
avisa que saiu versão nova. O texto da seção da versão publicada vai
inteiro para dentro daquela caixinha — então escreva pensando em quem vai
ler ali, e não em quem programa.

Para publicar: aumente o número em `VERSAO.txt` e acrescente aqui uma
seção `## <número>` com o que mudou. O resto acontece sozinho.

---

## 1.4.3

- Passou a existir um instalador (`Registro-SED-Instalador.exe`), além do
  `.exe` de sempre: baixa, executa uma vez (pede a senha de administrador
  do computador) e o programa já fica instalado em "Arquivos de
  Programas", com ícone próprio, atalho na área de trabalho e no Menu
  Iniciar — sem precisar copiar arquivo nenhum manualmente.
- O programa ganhou um ícone próprio (o logo do NTE Blumenau) em vez do
  ícone genérico, tanto na barra de tarefas quanto nos atalhos do Windows.
- Desinstalar também ficou normal: aparece em "Adicionar ou remover
  programas" do Windows, e remove junto a configuração, o login salvo e o
  histórico de envios.
- Quem já usa o .exe portátil de antes não precisa trocar nada: ele
  continua existindo e se atualizando sozinho, do jeito que já era.
  
## 1.4.2

- Corrigido o "não consegui reabrir o programa sozinho" que aparecia
  depois de atualizar. A troca da versão dava certo — o erro era só na
  hora de abrir a versão nova, e bastava abrir pelo atalho. Agora ele
  reabre sozinho de verdade.
- Se algum dia isso falhar de novo, a mensagem passa a dizer o motivo
  técnico junto, em vez de só "não consegui".

## 1.4.1

- Os "Recursos utilizados" voltaram a aparecer com o nome completo, igual
  ao do formulário da SED: "Computadores/notebooks (pesquisa) no
  laboratório" em vez de "Notebooks — pesquisa". Encurtar o texto tinha
  escondido justamente o que distingue um recurso do outro na hora de
  marcar — se é no laboratório ou se é o notebook levado para a sala.
- Os nove recursos continuam todos visíveis sem precisar rolar a tela.
- Com o programa aberto, ele passa a procurar versão nova uma vez por dia
  — antes só procurava na abertura, e quem deixa o computador do
  laboratório ligado a semana inteira nunca recebia correção nenhuma. Se
  houver formulário preenchido esperando envio, a procura espera: aceitar
  a atualização reabre o programa e jogaria o preenchimento fora.
- O rodapé passa a mostrar a que horas a agenda foi lida pela última vez.
  Ela é relida sozinha a cada 30 minutos (já era assim), mas isso
  acontecia sem deixar rastro — e "será que ele já viu a aula que acabei
  de agendar?" era motivo para fechar e abrir o programa à toa.

## 1.4.0

- O navegador passa a preencher o formulário EM SEGUNDO PLANO. A janela
  do Chrome não aparece mais no meio do seu trabalho a cada registro.
- Em troca, o resumo ficou mais forte: além do que o programa pretendia
  escrever, ele agora mostra "CONFERIDO NA PÁGINA" — cada resposta lida
  de volta do próprio formulário depois de escrita. É a prova de que o
  preenchimento aconteceu, e não uma promessa.
- Quem quiser assistir, marca "Ver o formulário sendo preenchido" ao lado
  dos botões e o navegador aparece, como antes.
- A conta Google da escola continua abrindo em janela visível, sempre —
  não existe como entrar numa janela que não aparece.
- Botão "Conta Google da escola" no rodapé: confere na hora se a conta
  institucional está conectada e, se não estiver, abre a janela certa
  para você entrar. O login continua sendo uma vez por computador.
- Quando a sessão do Google cai, o programa diz isso com todas as letras
  em vez de ficar parado esperando um campo que não existe na página.
- Corrigido o motivo de ninguém receber as atualizações: o endereço de
  onde elas vêm dependia de uma linha escrita no arquivo .env, e quem não
  tinha essa linha nunca era avisado de versão nova — sem erro, sem
  aviso, sem nada. Agora o endereço já vem no programa.
- Botão "Procurar atualização" no rodapé, para conferir na hora.

## 1.3.0

- O aviso de versão nova passa a explicar o que mudou, em vez de só
  mostrar o número.
- Configuração pela tela: na primeira vez, o programa pergunta escola,
  nome, CPF e turnos. Acabou a edição do arquivo .env no Bloco de Notas.
- A escola agora é escolhida numa lista com os 46 nomes da CRE Blumenau,
  escritos exatamente como a SED os escreve — antes, um nome digitado
  diferente fazia o registro ir para a escola errada.
- Login por professor: quem divide o computador com um colega de outro
  turno entra com o próprio nome e a própria senha, e sai da conta ao
  terminar. A senha não fica guardada em lugar nenhum.
- Os "Recursos utilizados" cabem inteiros na tela, sem precisar rolar.
- Se o programa não abrir, ele deixa um arquivo erro.txt ao lado
  explicando o motivo, em vez de simplesmente não fazer nada.

## 1.2.0

- O programa virou um arquivo único (.exe): não precisa mais instalar
  Python nem baixar navegador.
- Usa o Chrome ou o Edge que já estão na máquina.
- Passa a se atualizar sozinho: baixa a versão nova, se troca e reabre.

## 1.1.5

- Corrigido o erro "não encontrei o recurso Computadores/notebooks": o
  clique numa opção do formulário às vezes não registrava e o programa
  seguia adiante numa página que não era a esperada. Agora ele confere
  cada clique e cada troca de página.
- As mensagens de erro passaram a dizer em que página o programa parou e
  o que existe nela.

## 1.1.4

- Suporte às etapas que têm página própria no formulário: Educação
  Especial (AEE), Ensino Profissional e EJA.
- Corrigido o caso em que uma turma de "EJA - Ensino Médio" era tratada
  como Ensino Médio comum.

## 1.1.3

- O resumo do que foi preenchido não sai mais da tela em monitores
  menores, e a janela se ajusta ao tamanho da tela.
- A versão instalada aparece no rodapé.
