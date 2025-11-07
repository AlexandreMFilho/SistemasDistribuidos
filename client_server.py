import socket
import threading
import uuid
from collections import deque
import time
import os
import sys

# --- MODO DE EXECUÇÃO (DEBUG / HEARTBEAT / PADRÃO) ---
if len(sys.argv) > 1:
    MODO = sys.argv[1]
else:
    MODO = ""
   
# --- CONFIGURAÇÃO DE MULTICAST ---
MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007

# --- VARIÁVEIS GLOBAIS ---
MEU_IP = "127.0.0.1"
MEU_PORTA = 9001
MEU_ID = None # Será formatado como "IP:PORTA"

PROXIMO_IP = "127.0.0.1"
PROXIMO_PORTA = 9002

LIDER = None # "IP:PORTA" do líder

STATUSLIDER = None # "waiting" | "elected"

NETWORK_MEMBERS = [] # Lista com os IDs de todos os nós na rede

ultimo_heartbeat = 0
heartbeat_thread_started = False

cache = deque(maxlen=50)
username = "system"

# --- FUNÇÕES HANDLER PARA CADA COMANDO ---

def handle_lider(user, conteudo,**kwargs):
    """Trata mensagens de eleição."""
    return eleger_lider(conteudo) # Retorna True se o ciclo deve parar

def handle_list_build(user, conteudo, msg_id, **kwargs):
    """Trata a construção da lista de membros."""
    global NETWORK_MEMBERS
    partes_list = conteudo.split(">>")
    iniciador, membros_str = partes_list[1], partes_list[2]

    if iniciador == MEU_ID:
        if MODO == "debug":
            print("[REDE] Lista de membros completa recebida.")
        NETWORK_MEMBERS = sorted(membros_str.split(','))
        distribuir_lista_membros()
    else:
        nova_lista_membros = f"{membros_str},{MEU_ID}"
        msg_atualizada = f"{msg_id}|{user}|@LIST_BUILD>>{iniciador}>>{nova_lista_membros}"
        enviar_para_proximo(msg_atualizada)
    return True # Sempre paramos o repasse da msg original (ou ela finalizou ou foi atualizada)

def handle_list_update(user, conteudo,**kwargs):
    """Trata a atualização da lista de membros."""
    global NETWORK_MEMBERS
    NETWORK_MEMBERS = sorted(conteudo.split(">>")[1].split(','))
    if MODO == "debug":
        print(f"[REDE] Lista de membros atualizada: {NETWORK_MEMBERS}")
    return False # Deixa a mensagem circular para todos

def handle_exit(user, conteudo,**kwargs):
    """Trata o anúncio de saída de um nó."""
    if LIDER == MEU_ID:
        no_saindo = conteudo.split(">>")[1]
        if MODO == "debug":
            print(f"[LIDER] Nó {no_saindo} está saindo. Recalculando o anel.")
        gerenciar_saida_de_no(no_saindo)
    return False # Deixa a mensagem circular para chegar ao líder

def handle_reconnect(user, conteudo,**kwargs):
    """Trata a instrução de reconexão para consertar o anel."""
    global PROXIMO_IP, PROXIMO_PORTA
    _, alvo, novo_vizinho = conteudo.split(">>")
    if alvo == MEU_ID:
        novo_ip, nova_porta = novo_vizinho.split(":")
        PROXIMO_IP = novo_ip
        PROXIMO_PORTA = int(nova_porta)
        if MODO == "debug":
            print(f"[REDE] Anel atualizado. Meu novo vizinho é {novo_vizinho}")
        return True # Mensagem era para mim, para o ciclo.
    return False # Deixa circular se não for para mim

def handle_leader_exit(user, conteudo,**kwargs):
    """Trata a saída do líder, forçando nova eleição."""
    global LIDER, STATUSLIDER, NETWORK_MEMBERS
    if MODO == "debug":
        print("[REDE] O LÍDER SAIU! Resetando estado e iniciando nova eleição.")
    LIDER = None
    STATUSLIDER = None
    NETWORK_MEMBERS = []
    iniciar_eleicao()
    return False # Deixa a mensagem circular para todos

def enviar_heartbeat():
    while True:
        if LIDER == MEU_ID:
            cliente_envio(username, "@HEARTBEAT")
            if MODO == "debug" or MODO == "heartbeat":
                print(f"[HEARTBEAT] Enviado pelo líder {LIDER}")  
        time.sleep(5)
        
        
def handle_heartbeat(user, conteudo, **kwargs):
    global ultimo_heartbeat
    ultimo_heartbeat = time.time()
    if MODO == "debug" or MODO == "heartbeat":
        print(f"[HEARTBEAT] Recebido de {user} ({time.strftime('%H:%M:%S')})")
    return False

# E em cada nó:
def monitorar_heartbeat():
    global ultimo_heartbeat
    ultimo_heartbeat = time.time()
    while True:
        if time.time() - ultimo_heartbeat > 10:
            if MODO == "debug" or MODO == "heartbeat":
                print("[ALERTA] Falha do líder detectada. Iniciando eleição.")
            iniciar_eleicao()
        time.sleep(2)



# --- MAPA CENTRAL DE COMANDOS ---
# Mapeia o início de uma mensagem à sua função de tratamento (handler)
COMMAND_HANDLERS = {
    "@LIDER": handle_lider,
    "@LIST_BUILD": handle_list_build,
    "@LIST_UPDATE": handle_list_update,
    "@EXIT": handle_exit,
    "@RECONNECT": handle_reconnect,
    "@LEADER_EXIT": handle_leader_exit,
    "@HEARTBEAT": handle_heartbeat,
    # <--- Para adicionar novas rotinas como @ROLLCALL, basta adicionar uma linha:
    # "@ROLLCALL": handle_rollcall,
}

# --- FUNÇÕES DE REDE ---
def enviar_para_proximo(msg):
    """Envia uma mensagem para o próximo nó conhecido na cadeia."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((PROXIMO_IP, PROXIMO_PORTA))
            client_socket.send(msg.encode('utf-8'))
    except Exception as e:
        print(f"!! Erro ao conectar com o próximo nó {PROXIMO_IP}:{PROXIMO_PORTA}: {e}")

def cliente_envio(user, content):
    """Cria uma nova mensagem com ID único e a envia."""
    msg_id = str(uuid.uuid4())
    u = user if user else username
    msg = f"{msg_id}|{u}|{content}"
    enviar_para_proximo(msg)

# --- LÓGICA DE TRATAMENTO DE MENSAGENS (DISPATCHER) ---
def tratar_conexao(client_socket, addr):
    """Thread que trata cada conexão e delega o processamento."""
    try:
        msg = client_socket.recv(1024).decode("utf-8")
        if not msg or "|" not in msg:
            return

        partes = msg.split("|")
        if len(partes) != 3:
            return

        msg_id, user, conteudo = partes
        card = f"{msg_id}|{user}|{conteudo}"

        if card in cache:
            return
        cache.append(card)

        # 🔹 Filtra mensagens internas antes de exibir
        comando_interno = conteudo.strip().split(">>")[0].upper()
        comandos_internos = (
            "@HEARTBEAT", "@LIDER", "@LIST_BUILD", "@LIST_UPDATE",
            "@EXIT", "@RECONNECT", "@LEADER_EXIT"
        )

        if not comando_interno.startswith(comandos_internos):
            print(f"\n[MSG de {addr}] {user}: {conteudo}\n> ", end="")

        # Delega toda a lógica para o dispatcher
        deve_repassar = processar_mensagem(card, msg_id, user, conteudo)

        if deve_repassar:
            enviar_para_proximo(card)

    finally:
        client_socket.close()

def processar_mensagem(card, msg_id, user, conteudo):
    """
    Verifica o tipo de mensagem e chama a função handler correspondente.
    Retorna se a mensagem original deve ser repassada.
    """
    # Argumentos extras que algumas funções precisam
    kwargs = {'msg_id': msg_id}

    for command, handler in COMMAND_HANDLERS.items():
        if conteudo.strip().startswith(command):
            # Filtra os argumentos que a função realmente precisa
            import inspect
            sig = inspect.signature(handler)
            handler_args = {k: v for k, v in kwargs.items() if k in sig.parameters}
            
            # Chama o handler e decide se deve parar o ciclo
            parar_ciclo = handler(user, conteudo, **handler_args)
            return not parar_ciclo # Retorna se deve repassar

    # Se não for nenhum comando conhecido, é uma mensagem de chat normal
    return True # Sempre repassa mensagens de chat


# --- LÓGICA DE GERENCIAMENTO DA REDE ---

def eleger_lider(msg):
    global LIDER, STATUSLIDER
    conteudo = msg.strip().upper()
    partes = conteudo.split(">>")

    if len(partes) == 2 and partes[0] == "@LIDER":  # Token de votação
        ip_iniciador = partes[1]
        if ip_iniciador == MEU_ID and STATUSLIDER == "waiting":
            LIDER = MEU_ID
            STATUSLIDER = "elected"
            print(f"\n[ELEIÇÃO] 🏆 Novo líder estabelecido: {LIDER}")

            cliente_envio(username, f"@LIDER>>{LIDER}>>ELECTED")
            time.sleep(1)
            iniciar_construcao_lista()

            threading.Thread(target=enviar_heartbeat, daemon=True, name="enviar_heartbeat").start()
            if MODO == "debug" or MODO == "heartbeat":
                print(f"[HEARTBEAT] Thread iniciada automaticamente para o novo líder {LIDER}")

            if LIDER == MEU_ID:
                if not any(t.name == "multicast_listener" for t in threading.enumerate()):
                    t = threading.Thread(target=multicast_listener, daemon=True, name="multicast_listener")
                    t.start()
                    if MODO == "debug":
                        print(f"[MULTICAST] Listener iniciado pelo líder {LIDER}")
            return True

        
    elif len(partes) == 3 and partes[0] == "@LIDER" and partes[2] == "ELECTED": # Anúncio de líder
        ip_lider = partes[1]
        if LIDER is None:
            LIDER = ip_lider
            STATUSLIDER = "elected"
            print(f"\n[ELEIÇÃO] Líder eleito: {LIDER}")
        else:
            return True
    
    return False

def iniciar_eleicao():
    global STATUSLIDER, LIDER, ultimo_heartbeat
    tempo_desde_ultimo_heartbeat = time.time() - ultimo_heartbeat
    
    if LIDER is None and STATUSLIDER not in ("waiting", "connected") and tempo_desde_ultimo_heartbeat > 10:
        STATUSLIDER = "waiting"
        if MODO == "debug":
            print("\n[ELEIÇÃO] Iniciei uma nova eleição...")
        cliente_envio(username, f"@LIDER>>{MEU_ID}")
    else:
        if MODO == "debug":
            print("\n[ELEIÇÃO] Condições não atendidas (há líder ou heartbeat recente).")

def iniciar_construcao_lista():
    if LIDER == MEU_ID:
        if MODO == "debug":
            print("[LIDER] Iniciando construção da lista de membros da rede.")
        # Mensagem: @LIST_BUILD>>IP_do_Lider>>IP_do_primeiro_no (eu mesmo)
        cliente_envio(username, f"@LIST_BUILD>>{MEU_ID}>>{MEU_ID}")

def distribuir_lista_membros():
    if LIDER == MEU_ID:
        if MODO == "debug":
            print(f"[LIDER] Distribuindo a lista final para a rede: {NETWORK_MEMBERS}")
        membros_str = ",".join(NETWORK_MEMBERS)
        cliente_envio(username, f"@LIST_UPDATE>>{membros_str}")

def gerenciar_saida_de_no(no_saindo):
    global NETWORK_MEMBERS
    if no_saindo not in NETWORK_MEMBERS: return

    # Encontra o predecessor e o sucessor do nó que está saindo
    tamanho_rede = len(NETWORK_MEMBERS)
    idx_saindo = NETWORK_MEMBERS.index(no_saindo)
    
    predecessor = NETWORK_MEMBERS[(idx_saindo - 1 + tamanho_rede) % tamanho_rede]
    sucessor = NETWORK_MEMBERS[(idx_saindo + 1) % tamanho_rede]

    # O nó que está saindo é o próprio líder, não há o que fazer aqui
    if predecessor == sucessor or predecessor == no_saindo:
        if MODO == "debug":
            print("[LIDER] A rede ficará com apenas um nó. Nenhuma reconexão necessária.")
        NETWORK_MEMBERS.remove(no_saindo)
        return

    if MODO == "debug":print(f"[LIDER] Instruindo {predecessor} a se conectar com {sucessor}.")
    # Mensagem: @RECONNECT>>Nó_Alvo>>Novo_Vizinho
    cliente_envio(username, f"@RECONNECT>>{predecessor}>>{sucessor}")
    
    # Remove o nó e distribui a nova lista
    NETWORK_MEMBERS.remove(no_saindo)
    time.sleep(1) # Dá um tempo para a mensagem de reconexão ser processada
    distribuir_lista_membros()

def graceful_exit():
    if MODO == "debug":
        print("\nIniciando procedimento de saída da rede...")
    if LIDER == MEU_ID:
        # Se sou o líder, aviso a todos para começarem uma nova eleição
        cliente_envio(username, "@LEADER_EXIT")
    else:
        # Se sou um nó comum, apenas aviso que estou saindo
        cliente_envio(username, f"@EXIT>>{MEU_ID}")
    
    time.sleep(1) # Espera um segundo para garantir que a mensagem foi enviada
    if MODO == "debug":
        print("Até logo!")
    os._exit(0) # Força a saída do programa

# --- FUNÇÕES DE INICIALIZAÇÃO E LOOP PRINCIPAL ---
def servidor():
    global MEU_PORTA, MEU_ID
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            server_socket.bind((MEU_IP, MEU_PORTA))
            MEU_ID = f"{MEU_IP}:{MEU_PORTA}"
            break
        except OSError:
            MEU_PORTA += 1
    server_socket.listen(10)
    print(f"Servidor rodando em {MEU_ID}")
    while True:
        client_socket, addr = server_socket.accept()
        threading.Thread(target=tratar_conexao, args=(client_socket, addr)).start()

def configurar_username():
    global username
    username = input("Digite o nome de usuário: ")


# --- FUNÇÕES PARA COMANDOS INICIADOS PELO USUÁRIO ---

def local_cmd_help():
    """Mostra a lista de todos os comandos disponíveis."""
    print("\n--- Comandos Disponíveis ---")
    print("  Comandos de Rede:")
    print("    @LIDER - Inicia uma eleição para líder.")
    print("    @LIST  - Pede ao líder para reenviar a lista de membros.")
    print("    FIM    - Sai da rede de forma organizada.")
    print("\n  Comandos Locais:")
    print("    @MEMBERS - Mostra a lista de membros da rede conhecida localmente.")
    print("    @HELP    - Mostra esta mensagem de ajuda.")
    print("\n  Qualquer outro texto será enviado como chat.")
    print("-" * 30)

def local_cmd_members():
    """Mostra a lista de membros da rede atualmente conhecida."""
    print("\n--- Membros da Rede (Visão Local) ---")
    if NETWORK_MEMBERS:
        for i, member in enumerate(NETWORK_MEMBERS):
            is_leader = " (Líder)" if member == LIDER else ""
            is_self = " (Eu)" if member == MEU_ID else ""
            print(f"  {i+1}: {member}{is_leader}{is_self}")
    else:
        print("  Ainda não conheço os outros membros da rede.")
    print("-" * 30)

def local_cmd_lider():
    """Inicia o processo de eleição de líder."""
    iniciar_eleicao()

def local_cmd_list():
    """Solicita ao líder a lista atual de membros."""
    if LIDER:
        print("Solicitando a lista de membros ao líder...")
        iniciar_construcao_lista()
    else:
        print("Nenhum líder conhecido para solicitar a lista.")

def local_cmd_fim():
    """Inicia o processo de saída da rede."""
    graceful_exit()


# --- MAPA DE COMANDOS DO USUÁRIO ---
LOCAL_COMMANDS = {
    "FIM": local_cmd_fim,
    "@LIDER": local_cmd_lider,
    "@LIST": local_cmd_list,
    "@MEMBERS": local_cmd_members,
    "@HELP": local_cmd_help,
}



# --- CONFIGURACAO MULTICAST ---

# --- FUNÇÃO DE ESCUTA MULTICAST PARA LÍDER ---
def multicast_listener():
    """Líder escuta pedidos de entrada via multicast e responde via unicast."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MULTICAST_PORT))

    mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton('0.0.0.0')
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"[MULTICAST] Escutando em {MULTICAST_GROUP}:{MULTICAST_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        msg = data.decode('utf-8')
        if msg.startswith("DISCOVER"):
            _, ip, porta = msg.split(":")
            print(f"[MULTICAST] Pedido de entrada recebido de {ip}:{porta}")

            # Define o último nó conhecido como o próximo para o novo nó
            if NETWORK_MEMBERS:
                ultimo_no = NETWORK_MEMBERS[-1]
            else:
                ultimo_no = MEU_ID  # primeiro nó

            # Envia resposta: JOIN|<vizinho_anterior>|<líder>
            resposta = f"JOIN|{ultimo_no}|{MEU_ID}"
            sock.sendto(resposta.encode('utf-8'), (ip, int(porta)))
            print(f"[MULTICAST] Resposta enviada: {resposta}")

            # Atualiza a lista de membros do líder
            novo_no = f"{ip}:{porta}"
            if novo_no not in NETWORK_MEMBERS:
                NETWORK_MEMBERS.append(novo_no)
                distribuir_lista_membros()
                if MODO == 'debug':
                    print(f"[MULTICAST] Novo nó adicionado: {novo_no}")

# --- FUNÇÃO DE ENVIO MULTICAST PARA NÓS NOVOS ---
def multicast_discovery():
    """Nó novo envia um DISCOVER e aguarda resposta do líder."""
    global PROXIMO_IP, PROXIMO_PORTA, LIDER, STATUSLIDER

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    # Descobrir IP local
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    meu_ip = s.getsockname()[0]
    s.close()
    
    sock.bind(("", 0))  # Porta aleatória
    minha_porta = sock.getsockname()[1]

    msg = f"DISCOVER:{meu_ip}:{minha_porta}"
    sock.sendto(msg.encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
    if MODO == 'debug':
        print(f"[MULTICAST] Pedido de entrada enviado: {msg}")

    sock.settimeout(5)
    try:
        data, addr = sock.recvfrom(1024)
        resposta = data.decode("utf-8").strip()

        if resposta.startswith("JOIN"):
            partes = resposta.split("|")
            if len(partes) == 3:
                _, prox_id, lider_id = partes
                PROXIMO_IP, PROXIMO_PORTA = prox_id.split(":")
                PROXIMO_PORTA = int(PROXIMO_PORTA)
                LIDER = lider_id
                STATUSLIDER = "connected"

                if MODO == 'debug':
                    print(f"[MULTICAST] Conectado ao anel via {PROXIMO_IP}:{PROXIMO_PORTA}, líder = {LIDER}")

                # 🔹 Anuncia entrada no anel
                cliente_envio(username, f"Olá, entrei na rede! Meu ID é {meu_ip}:{minha_porta}")

        # Dá tempo para estabilizar o anel antes do chat
        time.sleep(3)

    except socket.timeout:
        if MODO == "debug":
            print("[MULTICAST] Nenhum líder respondeu. Iniciando como primeiro nó (possível líder).")
        LIDER = f"{MEU_IP}:{MEU_PORTA}"
        STATUSLIDER = "elected"
        threading.Thread(target=multicast_listener, daemon=True, name="multicast_listener").start()
        print(f"[ELEIÇÃO] 🏆 Assumindo papel de líder inicial: {LIDER}")

if __name__ == "__main__":
    if MODO == 'debug':
        print("--- Descoberta via Multicast ---")

    # ⚙️ Inicializa o servidor primeiro para garantir MEU_ID
    threading.Thread(target=servidor, daemon=True, name="servidor").start()
    time.sleep(1)  # dá tempo para o bind definir MEU_ID

    multicast_discovery()  # só depois faz a descoberta e possível eleição

    configurar_username()
    time.sleep(1)

    threading.Thread(target=monitorar_heartbeat, daemon=True, name="monitorar_heartbeat").start()


    local_cmd_help()

    while True:
        texto_usuario = input("> ")
        comando = texto_usuario.strip().upper()

        handler = LOCAL_COMMANDS.get(comando)
        if handler:
            handler()
        else:
            cliente_envio(username, texto_usuario)
