import socket
import threading
import uuid
from collections import deque
import time
import os
import inspect

# --- VARIÁVEIS GLOBAIS ---
MEU_IP = "127.0.0.1"
MEU_PORTA = 9001
MEU_ID = None # Será formatado como "IP:PORTA"

PROXIMO_IP = "127.0.0.1"
PROXIMO_PORTA = 9002

LIDER = None # "IP:PORTA" do líder
STATUSLIDER = None # "waiting" | "elected"

NETWORK_MEMBERS = [] # Lista com os IDs de todos os nós na rede

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
    print(f"[REDE] Lista de membros atualizada: {NETWORK_MEMBERS}")
    return False # Deixa a mensagem circular para todos

def handle_exit(user, conteudo,**kwargs):
    """Trata o anúncio de saída de um nó."""
    if LIDER == MEU_ID:
        no_saindo = conteudo.split(">>")[1]
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
        print(f"[REDE] Anel atualizado. Meu novo vizinho é {novo_vizinho}")
        return True # Mensagem era para mim, para o ciclo.
    return False # Deixa circular se não for para mim

def handle_leader_exit(user, conteudo,**kwargs):
    """Trata a saída do líder, forçando nova eleição."""
    global LIDER, STATUSLIDER, NETWORK_MEMBERS
    print("[REDE] O LÍDER SAIU! Resetando estado e iniciando nova eleição.")
    LIDER = None
    STATUSLIDER = None
    NETWORK_MEMBERS = []
    iniciar_eleicao()
    return False # Deixa a mensagem circular para todos


# --- MAPA CENTRAL DE COMANDOS ---
# Mapeia o início de uma mensagem à sua função de tratamento (handler)
COMMAND_HANDLERS = {
    "@LIDER": handle_lider,
    "@LIST_BUILD": handle_list_build,
    "@LIST_UPDATE": handle_list_update,
    "@EXIT": handle_exit,
    "@RECONNECT": handle_reconnect,
    "@LEADER_EXIT": handle_leader_exit,
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
        if not msg or "|" not in msg: return
            
        partes = msg.split("|")
        if len(partes) != 3: return

        msg_id, user, conteudo = partes
        card = f"{msg_id}|{user}|{conteudo}"

        if card in cache: return
        cache.append(card)
        
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

    if len(partes) == 2 and partes[0] == "@LIDER": # Token de votação
        ip_iniciador = partes[1]
        if ip_iniciador == MEU_ID and STATUSLIDER == "waiting":
            LIDER = MEU_ID
            STATUSLIDER = "elected"
            print(f"\n[ELEIÇÃO] Venci! Sou o novo líder: {LIDER}")
            cliente_envio(username, f"@LIDER>>{LIDER}>>ELECTED")
            time.sleep(1) # Pequena pausa antes de iniciar a construção da lista
            iniciar_construcao_lista() # Líder eleito inicia a criação da lista
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
    global STATUSLIDER
    if LIDER is None and STATUSLIDER is None:
        STATUSLIDER = "waiting"
        print("\n[ELEIÇÃO] Iniciei uma nova eleição...")
        cliente_envio(username, f"@LIDER>>{MEU_ID}")
    else:
        print("\n[ELEIÇÃO] Eleição já em andamento ou líder já definido.")

def iniciar_construcao_lista():
    if LIDER == MEU_ID:
        print("[LIDER] Iniciando construção da lista de membros da rede.")
        # Mensagem: @LIST_BUILD>>IP_do_Lider>>IP_do_primeiro_no (eu mesmo)
        cliente_envio(username, f"@LIST_BUILD>>{MEU_ID}>>{MEU_ID}")

def distribuir_lista_membros():
    if LIDER == MEU_ID:
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
        print("[LIDER] A rede ficará com apenas um nó. Nenhuma reconexão necessária.")
        NETWORK_MEMBERS.remove(no_saindo)
        return

    print(f"[LIDER] Instruindo {predecessor} a se conectar com {sucessor}.")
    # Mensagem: @RECONNECT>>Nó_Alvo>>Novo_Vizinho
    cliente_envio(username, f"@RECONNECT>>{predecessor}>>{sucessor}")
    
    # Remove o nó e distribui a nova lista
    NETWORK_MEMBERS.remove(no_saindo)
    time.sleep(1) # Dá um tempo para a mensagem de reconexão ser processada
    distribuir_lista_membros()

def graceful_exit():
    print("\nIniciando procedimento de saída da rede...")
    if LIDER == MEU_ID:
        # Se sou o líder, aviso a todos para começarem uma nova eleição
        cliente_envio(username, "@LEADER_EXIT")
    else:
        # Se sou um nó comum, apenas aviso que estou saindo
        cliente_envio(username, f"@EXIT>>{MEU_ID}")
    
    time.sleep(1) # Espera um segundo para garantir que a mensagem foi enviada
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


if __name__ == "__main__":
   
    # --- INICIALIZAÇÃO ---
    threading.Thread(target=servidor, daemon=True).start()
    
    print("--- Configuração do Nó ---")
    aux = input(f"IP do próximo nó é {PROXIMO_IP}. Pressione Enter ou digite um novo IP: ")
    if aux: PROXIMO_IP = aux
    
    aux2 = input(f"Porta do próximo nó é {PROXIMO_PORTA}. Pressione Enter ou digite uma nova porta: ")
    if aux2: PROXIMO_PORTA = int(aux2)
    
    configurar_username()
    time.sleep(1) 
    
    local_cmd_help() # Mostra a ajuda inicial

    # --- LOOP PRINCIPAL REATORADO ---
    while True:
        texto_usuario = input("> ")
        comando = texto_usuario.strip().upper()

        handler = LOCAL_COMMANDS.get(comando)

        if handler:
            handler()
        else:
            cliente_envio(username, texto_usuario)