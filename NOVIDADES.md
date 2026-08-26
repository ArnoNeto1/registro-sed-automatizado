# Novidades

Este arquivo é a fonte das notas que cada professor lê quando o programa
avisa que saiu versão nova. O texto da seção da versão publicada vai
inteiro para dentro daquela caixinha — então escreva pensando em quem vai
ler ali, e não em quem programa.

Para publicar: aumente o número em `VERSAO.txt` e acrescente aqui uma
seção `## <número>` com o que mudou. O resto acontece sozinho.

---

## 1.3.1

- Corrigido o motivo de ninguém receber as atualizações: o endereço de
  onde elas vêm dependia de uma linha escrita no arquivo .env, e quem
  não tinha essa linha nunca era avisado de versão nova — sem erro, sem
  aviso, sem nada. Agora o endereço já vem no programa.
- Botão "Procurar atualização" no rodapé, para conferir na hora. Ele
  sempre responde: ou oferece a versão nova, ou diz que você já está na
  mais nova, ou avisa que não conseguiu consultar.

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
