# Novidades

Este arquivo é a fonte das notas que cada professor lê quando o programa
avisa que saiu versão nova. O texto da seção da versão publicada vai
inteiro para dentro daquela caixinha — então escreva pensando em quem vai
ler ali, e não em quem programa.

Para publicar: aumente o número em `VERSAO.txt` e acrescente aqui uma
seção `## <número>` com o que mudou. O resto acontece sozinho.

---

## 1.8.0

- **Nova opção: registrar suporte a outros espaços sem agendamento.**
  Até agora, "Suporte do professor orientador a outros espaços" (instalar
  ou configurar um equipamento levado para outra sala) só podia ser
  registrado quando isso já estava marcado na agenda do laboratório.
  Agora tem um botão próprio, "Suporte a outros espaços", ao lado de
  "Manutenção" e "Formação/Reunião" — sempre disponível, sem precisar de
  reserva nenhuma.
- Corrigido: em escolas com só um recurso (a maioria — só laboratório),
  clicar em "Manutenção" ou "Formação/Reunião" podia deixar sem nenhum
  jeito de voltar para a lista de aulas, a não ser fechando e abrindo o
  programa de novo.

## 1.7.8

- Ajuste interno para o Windows confiar mais no programa: o `.exe`
  deixou de vir comprimido de um jeito que fazia alguns antivírus
  desconfiarem à toa (a mesma técnica de compressão é usada por vírus
  para se esconder), e agora mostra corretamente o nome, a empresa e a
  versão do programa nas propriedades do arquivo do Windows. Nenhuma
  mudança visível na tela do programa.

## 1.7.7

- **Mudança: o programa não tenta mais se reabrir sozinho** depois de
  atualizar ou de salvar em "Meus dados" — agora ele pede pra você
  fechar e abrir de novo na mão. Dá um clique a mais, mas é bem mais
  confiável: reabrir rápido demais era a causa de telas de erro
  técnico ("Security validation failure", "Can't find a usable
  init.tcl", "Failed to start embedded python interpreter") que só
  sumiam reabrindo na mão mesmo — agora o programa já pede isso direto,
  sem passar pela tela de erro no meio.

## 1.7.6

- Corrigido: às vezes, depois de reabrir sozinho (atualização
  automática, ou salvar em "Meus dados"), o programa mostrava uma tela
  de erro técnico ("Can't find a usable init.tcl") e não voltava —
  precisava abrir na mão de novo. Agora, quando isso acontece, o próprio
  programa se reabre sozinho de verdade (não só tenta de novo por
  dentro) — que era exatamente o que já resolvia na mão.

## 1.7.5

- **Nova opção: registrar uma aula sem agendamento.** Às vezes o
  laboratório (ou tablet/projetor) é usado sem reserva na agenda do
  NTE — agora dá pra registrar do mesmo jeito. Um link novo aparece
  embaixo da lista de aulas: "Não achou a sua aula na lista acima?
  Registrar aula sem agendamento".
- Corrigido: as colunas da tabela de aulas ("Dia e horário",
  "Professor(a)"...) ficavam sem nenhuma linha separando uma da outra.
- Corrigido: passar o mouse sobre o campo "Conteúdo aplicado" e tentar
  rolar a tela, com pouco texto ali dentro, não fazia nada.
- Ajustes para o programa respeitar melhor a escala de tela do Windows
  (125%/150%).

## 1.7.4

- Corrigido: às vezes, depois de uma atualização automática, o programa
  mostrava uma tela de erro do navegador ("Security validation
  failure...") e não reabria sozinho — era preciso abrir na mão de novo.
  Agora o programa dá uma folga de alguns segundos antes de carregar a
  agenda pela primeira vez, logo depois de reabrir sozinho, evitando a
  corrida que causava o erro.

## 1.7.3

- Corrigido: a caixa de "Nova versão disponível" mostrava o texto desta
  lista com asteriscos duplos literais (a caixa é do Windows, não
  entende Markdown) e cortava cada item no meio da frase. Agora aparece
  como texto normal, com um espaço separando um item do outro.

## 1.7.2

- **Modo claro, escuro, ou igual ao do computador.** Em "Meus dados" tem
  agora uma opção de "Aparência" com três escolhas: Claro, Escuro, ou
  Igual ao sistema (segue o que o Windows já está usando). Vale pra tela
  principal e pras telas de entrar/cadastrar.
- Corrigido: no tema escuro, passar o mouse por cima de uma opção
  (Tecnologias Educacionais/Laboratório Maker, Aparência, "Ver o
  formulário sendo preenchido"...) deixava o texto invisível por cima de
  um fundo claro. Agora o texto continua legível com o mouse em cima.

## 1.7.1

- **Aviso de Caps Lock na tela de entrar.** Como o campo de senha vem
  escondido, não dava pra perceber que o Caps Lock estava ligado antes
  de tentar entrar e levar um "senha incorreta" sem entender por quê.
  Agora aparece um aviso na hora.
- Corrigido: depois de selecionar uma aula e trocar de aba, os dados da
  aula anterior (dia, etapa, conteúdo) ficavam aparecendo por engano em
  "Dados do registro", mesmo sem nenhuma aula selecionada na aba nova.
- A ordem das abas mudou: Tablets/Celular agora vem antes de Projetores.
- Deixamos mais confiável o reinício automático depois de baixar uma
  atualização.
- Revisão geral de texto: alguns pontos onde só aparecia a forma
  masculina ("professor") agora mostram "professor(a)", e corrigimos
  alguns erros de digitação espalhados pela tela.

## 1.7.0

- **O programa agora preenche os 4 tipos de registro do formulário da
  SED, não só "Atividade/Aula com estudantes".** Numa aula de Projetor
  ou Tablets/Celular, o programa pergunta se foi mesmo uma aula com
  estudantes ou se foi só instalar/dar suporte a um equipamento — os
  campos mudam na hora, conforme a resposta. E apareceram duas abas
  novas, sempre disponíveis do lado direito da tela: **Manutenção** (pra
  quando você conserta ou organiza algo do laboratório) e **Formação/
  Reunião** (pra quando você participa de uma formação ou reunião) —
  essas duas nem precisam de aula marcada na agenda, é só abrir a aba e
  preencher.
- Pequeno ajuste visual: as opções de múltipla escolha (os círculos e
  quadrados de marcar) ficaram com o mesmo fundo do resto da tela — antes
  aparecia um retângulo cinza atrás do texto de cada opção.

## 1.6.2

- Faxina interna: removidos arquivos que só serviam pra uma forma bem
  antiga de configurar o programa (editando um arquivo `.env` na mão,
  sem instalador nenhum) — ninguém mais usa esse caminho. Não muda nada
  pra quem já usa o instalador ou o `.exe` normalmente; o instalador
  inclusive fica um pouco menor, por empacotar menos arquivo à toa.

## 1.6.1

- **O programa passa a ler também Projetor e Tablets/Celular, não só o
  laboratório.** Ao carregar a agenda, ele descobre sozinho quais outros
  recursos a sua escola tem reserváveis no NTE (cada escola tem os
  seus) e só considera os que são de Tecnologias Educacionais de
  verdade — Projetor, Tablet, Celular, Notebook móvel. Uma reserva de
  Auditório ou Biblioteca, por exemplo, é ignorada: não é trabalho do
  orientador. Quando isso encontra aula em mais de uma categoria na
  semana, aparecem abas — **Laboratório | Projetores | Tablets/Celular**
  — ao lado de "Aulas da semana". Quem só usa o laboratório (a grande
  maioria) nem percebe: a tela continua exatamente igual, sem aba
  nenhuma aparecendo à toa.
- O aviso de "aula começando agora" (a piscada na barra de tarefas e a
  linha verde "Sugerida agora") passa a funcionar por aba: se acontecer
  aula no laboratório e em Tablets ao mesmo tempo, as duas avisam — e a
  aba que não está sendo olhada no momento fica marcada em laranja, pra
  não passar despercebida.

## 1.6.0

- **Suporte a professor que dá aula em mais de uma escola, no mesmo
  computador** (ver "Cadastro passa a aceitar até 3 escolas", mais
  abaixo). Ao abrir o programa (ou trocar de conta), se você tem mais
  de uma escola cadastrada, ele pergunta em qual delas você está hoje —
  a pergunta não fica salva, é feita de novo toda vez, igual a senha.
  Essa escolha vale tanto para a agenda lida quanto para o formulário
  enviado à SED. Quem tem uma escola só nem percebe essa pergunta — o
  programa nem chega a mostrar.
- Junto disso, corrigido o login para quem o site do NTE pede para
  escolher a escola (professores associados a mais de uma no cadastro
  do NTE) — o programa escolhe sozinho a que vale no momento, em vez de
  travar a leitura da agenda.
- **O login salvo do Google agora é por escola, não um só para o
  computador inteiro.** Quem dá aula em duas escolas tinha o login do
  Google preso na conta da PRIMEIRA escola usada — trocar de escola não
  trocava a conta, e o formulário preenchido ia para a SED com a conta
  Google errada. Agora cada escola guarda o próprio login, e trocar de
  escola pede a conta certa na hora.
- Corrigido um "não foi possível navegar até a semana desejada" que
  aparecia para quem tem mais de uma escola: a tela de escolha de
  escola do NTE tem um botão "Confirmar" separado da lista — o programa
  escolhia a escola certa mas nunca clicava em "Confirmar", então a
  tela nunca fechava de verdade.
- Corrigido um problema em que cadastrar (ou editar) um professor podia
  silenciosamente trocar a escola de OUTRO professor que ainda não tinha
  escola própria salva — cadastros antigos, de antes de existir a opção
  de mais de uma escola, "herdavam" a escola de quem tivesse sido salvo
  por último. Junto disso, corrigido "Meus dados" de quem estava nessa
  situação: o campo Escola vinha pré-preenchido com essa mesma escola
  errada, então confirmar e salvar não resolvia — agora vem em branco,
  pedindo a escolha de verdade.
- **"Sair da conta" agora também desloga a conta Google da escola.** Sair
  do programa é sinal de que o uso terminou, e o próximo a mexer no
  computador pode ser um professor de outra escola — não faz sentido a
  conta institucional continuar logada esperando por ele. Acontece em
  segundo plano, sem abrir janela, e nunca impede o programa de fechar
  (sem internet, por exemplo, o login só continua guardado até a
  próxima vez).
- Como toda sessão agora começa deslogada do Google (item acima), o
  programa passou a conferir a conta Google da escola sozinho, uma vez,
  assim que a agenda termina de carregar — em vez de esperar a pessoa
  lembrar de clicar em "Conta Google da escola" e só descobrir no meio
  de um preenchimento que precisava logar de novo.
- Depois de entrar na conta Google da escola (ou quando ela já estava
  conectada), a janela do Chrome fecha sozinha e o programa volta para
  a frente — antes ficava aberta, esperando ser fechada na mão.
- Corrigido "Cadastrar outro professor" (na tela de login, quando é a
  primeira coisa que abre) deixando uma segunda tela de cadastro em
  branco aberta e "presa" no fundo, sem responder — bug antigo, achado
  agora ao cadastrar um professor novo pela tela de login.
- Corrigido um "não consegui abrir o programa" que podia aparecer bem
  depois de cadastrar/editar um professor (o programa fecha e abre
  sozinho nesse momento) — a causa é a mesma já conhecida do reabrir
  depois de atualizar: algo passageiro (um antivírus examinando os
  arquivos recém-criados, por exemplo) podia atrapalhar bem na hora de
  a janela abrir. Agora, se isso acontecer, o programa tenta de novo
  sozinho (até 6 vezes, esperando mais a cada uma) antes de desistir e
  mostrar erro.
- Erro de **falha de internet/conexão** (site fora do ar, wifi caiu na
  hora) agora aparece numa frase clara ("Não consegui acessar o site —
  parece internet, não o programa") em vez do texto técnico cru do
  Chrome — que continua ali, só que como detalhe menor, não a mensagem
  principal.
- **Duas aulas separadas só pelo recreio agora contam como uma
  atividade só**, em vez de aparecerem soltas na lista — mesma
  professora, turma, disciplina e turno, com um intervalo curto (até
  20 min) no meio. Antes só emendava quando o horário batia direto,
  sem nenhum intervalo, e o recreio quebrava o que era uma aula
  contínua em duas.
- Novo botão **"Remover professor"** na tela de login: tira alguém da
  lista de quem usa o programa neste computador (não mexe em nada na
  SED nem no NTE — só o cadastro salvo aqui), pra quem testou/cadastrou
  errado ou trocou de professor no laboratório.
- **Turno passa a ser por escola, não um só para o professor inteiro.**
  Quem atende de manhã numa escola e só à noite noutra agora marca isso
  no cadastro, escola por escola — antes era um turno só, valendo pra
  todas. É esse turno que decide o que aparece em destaque na agenda
  daquela escola (e o que aparece em cinza, "de outro turno").
- **Cadastro passa a aceitar até 3 escolas** (o estado permite dar aula
  em até 3), com 3 campos "Escola" já visíveis na tela — antes existia
  só uma segunda escola, escondida atrás de um checkbox que podia não
  abrir corretamente. Agora é só deixar em branco quem tem menos de 3.
- Corrigido "marquei só 1 recurso e foram 4 no formulário": as 4
  opções "Computadores/notebooks (...) no laboratório" estão amarradas
  entre si dentro do próprio formulário da SED — marcar qualquer uma
  pode marcar as outras 3 junto (defeito de lá, não daqui). Desmarcar,
  ao contrário, é independente. O programa agora usa isso: marca a
  escolhida e, se alguma das outras 3 vier marcada de brinde, desmarca
  de volta sozinho — o checkbox certo (e só ele) fica marcado, sem usar
  nada fora do lugar certo do formulário.

## 1.5.0

- Nenhum "Recurso utilizado" vem mais pré-marcado — antes 3 vinham
  marcados por padrão, e a ideia é cada professor escolher, toda vez, o
  que realmente foi usado naquela aula.
- **O histórico de envios não acumula mais para sempre.** Aulas com mais
  de 1 mês somem sozinhas do `registros_enviados.json` e do
  `aulas_nao_realizadas.json` — o programa esquece na hora de abrir,
  sem precisar fazer nada. Continua funcionando exatamente igual: o
  motivo desses arquivos existirem é só evitar duplicar registro
  enquanto a aula ainda pode aparecer na tela, e depois de um mês isso
  já não é mais um risco de verdade.
- Coluna "Turma" bem mais larga na lista de aulas — nomes vindos da
  agenda do NTE são longos ("Anos Iniciais - 3º ano - Anos Iniciais") e
  ficavam cortados.
- Rodapé: tirado o aviso "agenda lida às HH:MM · relê a cada 30 min" (a
  releitura automática continua acontecendo do mesmo jeito, só não
  aparece mais escrita) e colocado "Desenvolvido por ArnoNeto1".
- **Novo botão "Ver no navegador"**, ao lado de "Enviar para a SED": abre
  o formulário já preenchido numa janela de verdade do Chrome, para
  conferir pessoalmente antes de enviar. Aparece assim que o
  preenchimento termina.
- **Corrigido o erro "Target page, context or browser has been closed"**
  que podia aparecer depois de preencher: se a janela do Chrome fosse
  fechada na mão (ou travasse) enquanto o programa ainda achava que ela
  estava aberta, a ação seguinte (enviar, cancelar) quebrava com um erro
  técnico sem explicação. Agora o programa percebe e se recupera sozinho,
  ou avisa com clareza que nada foi enviado. Isso também podia acontecer
  ao clicar em "Conta Google da escola" com um formulário preenchido
  esperando envio — esse botão agora avisa antes de descartar o
  preenchimento (e sugere o "Ver no navegador" no lugar).
- **Corrigido o erro depois de uma atualização automática.** Às vezes,
  logo depois do programa se atualizar e reabrir sozinho, aparecia um erro
  e era preciso fechar e abrir de novo na mão para funcionar. Isso
  acontecia porque a versão nova podia tentar abrir o navegador antes da
  versão antiga ter fechado o dela de verdade. Agora o programa espera o
  navegador antigo fechar direito antes de abrir a versão nova — e, se
  mesmo assim o navegador não abrir de primeira por qualquer outro motivo
  passageiro (por exemplo, um antivírus examinando o programa recém
  atualizado), ele tenta de novo sozinho antes de desistir.
- **Reforçada a proteção contra duplicar um registro na SED**: se a
  internet travar bem no instante de clicar "Enviar", o programa agora
  confere de verdade se a SED recebeu o registro antes de marcá-lo como
  enviado — antes, essa checagem não existia. Se não conseguir confirmar,
  ele avisa e NÃO marca como enviado, em vez de arriscar.
- Fechar o programa enquanto um envio está em andamento agora pede
  confirmação, avisando do risco.
- Se o arquivo do histórico de envios estiver corrompido (queda de luz,
  antivírus), o programa agora avisa na tela — antes, ficava em silêncio e
  tratava tudo como se nada tivesse sido enviado.
- Corrigida uma tela que podia parar de atualizar status e botões pelo
  resto da sessão, sem avisar, se algo raro desse errado ao processar um
  evento interno.
- Trocar de professor (computador dividido entre dois orientadores) agora
  limpa a aula selecionada na hora — evita o risco raro de clicar
  "Preencher formulário" bem no meio da troca e misturar o nome do
  professor novo com dados de aula do professor anterior.
- Instalado pelo instalador (não pelo `.exe` portátil): os dados do
  professor (login, senha, histórico) passaram a ficar numa pasta própria
  do Windows em vez de dentro de "Arquivos de Programas". Quem já tinha
  instalado antes não perde nada — a migração acontece sozinha, na
  próxima vez que abrir.
- Adicionada uma licença (MIT) ao repositório no GitHub.

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
