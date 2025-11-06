# Trabalho Final – Sistemas Distribuídos
## Tema: Sistema de Chat Distribuído com Tolerância a Falhas
### Enunciado:
Desenvolva um sistema de mensagens instantâneas distribuído (sem servidor central)
onde os nós da rede podem enviar e receber mensagens em tempo real. O sistema deve
ser resiliente a falhas de nós e capaz de se reorganizar automaticamente em caso de
desconexões.
#### Requisitos mínimos obrigatórios:
1. Arquitetura peer-to-peer: não pode haver um servidor único; cada cliente deve
atuar também como nó da rede.
2. Entrada na rede: um nó pode entrar conhecendo apenas o IP de multicast.
Apenas o coordenador deve responder, iniciando, assim, o início do cadastro desse nó.
3. Coordenador:
    1. O coordenador é responsável por atribuir identificadores únicos aos nós que entram.
    2. O Coordenador e responsável por anunciar saída de um nó.
    3. O coordenador envia periodicamente um heartbeat para indicar que continua ativo.
4. Eleição de novo coordenador:
    1. Se o coordenador falhar ou sair, os nós devem detectar a ausência do heartbeat e eleger automaticamente um novo coordenador (ex.: algoritmo do Bully ou Ring).
5. Tolerância a falhas: quando um nó sai ou falha, a rede deve se reorganizar
automaticamente (por exemplo, elegendo um novo coordenador para alguma
função, se necessário).
6. Histórico consistente: todos os nós ativos devem convergir para o mesmo
histórico de mensagens (mesmo que em ordem causal e não necessariamente
cronológica perfeita).
7. Demonstração prática: crie um protótipo funcional onde pelo menos 4
máquinas/nós distintos participem simultaneamente.
Usar linguagem de programação Python ou Java.

O aluno terá 13 minutos para mostrar ao professor o código executando e responder suas
perguntas. Caso o aluno passe do tempo, perderá ponto. Não será necessário apresentar,
apenas irá demonstrar o código e tirar dúvidas na mesa do professor. O Código será ser
enviado pelo classroom.

# SistemasDistribuidos

## Arquitetura peer-to-peer
## Entrada multicast na rede

✔️ Listener multicast inicia apenas uma vez (evita erro “address already in use”).

✔️ O primeiro nó assume automaticamente como líder, garantindo inicialização suave da rede distribuída.

## Papel do Coordenador
### Integração do heartbeat

✔️ O líder envia @HEARTBEAT a cada 5 s.

✔️ Os demais nós atualizam ultimo_heartbeat sempre que recebem.

✔️ O monitor verifica ausência de batimento e dispara eleição após 10 s.

✔️ As duas threads (enviar_heartbeat e monitorar_heartbeat) são criadas no main com daemon=True, o que mantém o loop principal livre.

✔️ A variável ultimo_heartbeat é inicializada antes do start das threads.

✔️ Os prints condicionais com sys.argv[1] == "heartbeat" ou "debug" são uma boa prática de instrumentação.

🔹 Comportamento esperado:

Apenas o líder enviará batimentos (if LIDER == MEU_ID:).

Ao perder o líder, os outros nós iniciarão uma nova eleição.

Quando o novo líder for eleito, ele automaticamente começará a enviar batimentos (pois a thread já está rodando e a condição passará a ser verdadeira).

O envio de batimentos (enviar_heartbeat) só é iniciado quando há eleição concluída — ou seja, quando o nó se torna líder.

Isso evita batimentos prematuros e reduz ruído na rede.

## Eleição de novo coordenador
## Tolerância a falhas
## Histórico consistente
## Demonstração prática:



