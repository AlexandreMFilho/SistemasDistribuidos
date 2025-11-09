import socket
import threading
import uuid
from collections import deque
import os
import sys
import signal
import random
import time

# --- MODO DE EXECUÇÃO (DEBUG / HEARTBEAT / PADRÃO) ---
if len(sys.argv) > 1:
    MODO = sys.argv[1]
else:
    MODO = ""

# --- CONFIGURAÇÃO DE MULTICAST ---
MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007

# --- VARIÁVEIS GLOBAIS ---
RECONEXAO_LOCK = threading.Lock()

MEU_IP = "127.0.0.1"
MEU_PORTA = 9001
MEU_ID = None

PROXIMO_IP = None
PROXIMO_PORTA = None

LIDER = None
STATUSLIDER = None  # "waiting" | "elected" | "connected"

NETWORK_MEMBERS = []

ultimo_heartbeat = 0
cache = deque(maxlen=50)
username = "system"


# --- FUNÇÃO PARA OBTER IP LOCAL ---
def obter_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

MEU_IP = obter_ip_local()


# --- HANDLERS DE COMANDOS ---
def handle_lider(user, conteudo, **kwargs):
    return eleger_lider(conteudo)

def handle_list_build(user, conteudo, msg_id, **kwargs):
    global NETWORK_MEMBERS
    partes_list = conteudo.split(">>")
    iniciador, membros_str = partes_list[1], partes_list[2]
    if iniciador == MEU_ID:
        if MODO == "debug":
            print("[REDE] Lista de membros completa recebida.  🧾  ")
        NETWORK_MEMBERS = membros_str.split(',')
        distribuir_lista_membros()
    else:
        nova_lista_membros = f"{membros_str},{MEU_ID}"
        msg_atualizada = f"{msg_id}|{user}|@LIST_BUILD>>{iniciador}>>{nova_lista_membros}"
        enviar_para_proximo(msg_atualizada)
    return True

def handle_list_update(user, conteudo, **kwargs):
    global NETWORK_MEMBERS
    NETWORK_MEMBERS = conteudo.split(">>")[1].split(',')
    if MODO == "debug":
        print(f"[REDE] Lista de membros atualizada: {NETWORK_MEMBERS}  🧾")
    return False

def handle_exit(user, conteudo, **kwargs):
    global NETWORK_MEMBERS
    partes = conteudo.split(">>")
    if len(partes) >= 4:
        _, no_saindo, predecessor, sucessor = partes
        if LIDER == MEU_ID:
            print(f"[LIDER] Nó {no_saindo} saiu 🏃‍♂️ . Recalculando o anel.")
            # reconecta predecessor -> sucessor
            cliente_envio(username, f"@RECONNECT>>{predecessor}>>{sucessor}")
            if no_saindo in NETWORK_MEMBERS:
                NETWORK_MEMBERS.remove(no_saindo)
                distribuir_lista_membros()
        return False
    elif LIDER == MEU_ID:
        # fallback para versão antiga (sem predecessor)
        no_saindo = conteudo.split(">>")[1].strip()
        print(f"[LIDER] Nó {no_saindo} saiu 🏃‍♂️ . Recalculando o anel.")
        gerenciar_saida_de_no(no_saindo)
    return False

def handle_reconnect(user, conteudo, **kwargs):
    global PROXIMO_IP, PROXIMO_PORTA
    _, alvo, novo_vizinho = conteudo.split(">>")
    if alvo == MEU_ID:
        novo_ip, nova_porta = novo_vizinho.split(":")
        PROXIMO_IP = novo_ip
        PROXIMO_PORTA = int(nova_porta)
        if MODO == "debug":
            print(f"[REDE] Anel atualizado. Meu novo vizinho é {novo_vizinho}   🏘️  ")
        return True
    return False


def handle_leader_exit(user, conteudo, **kwargs):
    global LIDER, STATUSLIDER, NETWORK_MEMBERS, PROXIMO_IP, PROXIMO_PORTA

    partes = conteudo.split(">>")

    if MODO == "debug":
        print(f"[REDE] O LÍDER SAIU! Processando msg: {conteudo}")

    # CASO 1: Mensagem de reparo completa (o líder saiu de forma controlada)
    if len(partes) == 4:
        _, lider_saindo, predecessor_no_anel, sucessor_no_anel = partes

        # Se EU sou o predecessor, eu me reconecto E inicio a eleição
        if MEU_ID == predecessor_no_anel: 
            novo_ip, nova_porta = sucessor_no_anel.split(":")
            PROXIMO_IP = novo_ip
            PROXIMO_PORTA = int(nova_porta)
            print(f"[REDE] O líder saiu. Reparando anel: conectando a {sucessor_no_anel}")
            
            # Agora SÓ EU inicio a eleição
            LIDER = None
            STATUSLIDER = None # Limpa o status para permitir a eleição
            NETWORK_MEMBERS = [] # Limpa a lista
            iniciar_eleicao() 
        
        # Se eu NÃO sou o predecessor, eu apenas anoto a falha e aguardo
        else:
            LIDER = None
            STATUSLIDER = "waiting" # Aguarda o novo líder
            NETWORK_MEMBERS = [] # Limpa a lista
            print("[REDE] Líder saiu. Aguardando novo líder ser eleito.")

    # CASO 2: Mensagem simples (fallback, ou morte súbita acionou o monitor)
    # Se a mensagem for apenas "@LEADER_EXIT" (sem reparo), todos tentam.
    else:
        LIDER = None
        STATUSLIDER = None
        NETWORK_MEMBERS = []
        iniciar_eleicao()

    return False # Sempre deixa a mensagem circular

# --- HEARTBEAT ---
def enviar_heartbeat():
    while True:
        if LIDER == MEU_ID:
            cliente_envio(username, f"@HEARTBEAT>>{LIDER}")
            if MODO in ("debug", "heartbeat"):
                print(f"[HEARTBEAT]  ❤️  Enviado pelo líder {LIDER}")
        time.sleep(5)

def handle_heartbeat(user, conteudo, **kwargs):
    global ultimo_heartbeat, LIDER
    partes = conteudo.split(">>")
    if len(partes) == 2:
        _, id_lider = partes
        if LIDER != id_lider:
            if LIDER is None or id_lider > LIDER:
                if MODO in ("debug", "heartbeat"):
                    print(f"[HEARTBEAT] ❤️ Atualizando líder para {id_lider}  👑 ")
                LIDER = id_lider
    ultimo_heartbeat = time.time()
    if MODO in ("debug", "heartbeat"):
        print(f"[HEARTBEAT]  ❤️  Recebido de {user} ({time.strftime('%H:%M:%S')}) - líder {LIDER} 👑  ")
    return False


def monitorar_heartbeat():
    global ultimo_heartbeat
    ultimo_heartbeat = time.time()
    while True:
        # Simplificado: apenas chama a função de iniciar eleição.
        # A própria função decidirá se o tempo foi excedido.
        time.sleep(2) 
        if LIDER != MEU_ID:
            iniciar_eleicao()

COMMAND_HANDLERS = {
    "@LIDER": handle_lider,
    "@LIST_BUILD": handle_list_build,
    "@LIST_UPDATE": handle_list_update,
    "@EXIT": handle_exit,
    "@RECONNECT": handle_reconnect,
    "@LEADER_EXIT": handle_leader_exit,
    "@HEARTBEAT": handle_heartbeat,
}


# --- REDE TCP ---
def enviar_para_proximo(msg):
    global PROXIMO_IP, PROXIMO_PORTA, LIDER, STATUSLIDER
    
    if not PROXIMO_IP or not PROXIMO_PORTA:
        if MODO == "debug":
            print("Nenhum próximo definido, ignorando envio. 😔")
        return

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((PROXIMO_IP, PROXIMO_PORTA))
            client_socket.send(msg.encode('utf-8'))
    except Exception as e:
        if MODO == "debug":
            print(f"⚠️  !! Erro ao conectar com o próximo nó {PROXIMO_IP}:{PROXIMO_PORTA}: {e}")
        
        # --- Início da Rotina de Reconexão de Nó Órfão ---
        if RECONEXAO_LOCK.acquire(blocking=False):
            try:
                print("[REDE] Conexão com o próximo nó perdida. Tentando redescobrir a rede...")
                LIDER = None
                STATUSLIDER = "lost" # Novo estado para indicar "perdido"
                PROXIMO_IP = None
                PROXIMO_PORTA = None
                
                threading.Thread(target=multicast_discovery, daemon=True).start()
            except Exception as e_thread:
                print(f"Erro ao iniciar thread de redescoberta: {e_thread}")
                RECONEXAO_LOCK.release() 
        else:
            if MODO == "debug":
                print("[REDE] Já estou em processo de reconexão. Ignorando este envio.")
        # --- Fim da Rotina de Reconexão ---


def cliente_envio(user, content):
    msg_id = str(uuid.uuid4())
    u = user if user else username
    msg = f"{msg_id}|{u}|{content}"
    enviar_para_proximo(msg)

def tratar_conexao(client_socket, addr):
    try:
        msg = client_socket.recv(1024).decode("utf-8")
        if not msg or "|" not in msg:
            return
        msg_id, user, conteudo = msg.split("|")
        card = f"{msg_id}|{user}|{conteudo}"
        if card in cache:
            return
        cache.append(card)
        comando_interno = conteudo.strip().split(">>")[0].upper()
        comandos_internos = ("@HEARTBEAT", "@LIDER", "@LIST_BUILD", "@LIST_UPDATE", "@EXIT", "@RECONNECT", "@LEADER_EXIT")
        if not comando_interno.startswith(comandos_internos):
            print(f"\n[MSG de {addr}] {user}: {conteudo}\n> ", end="")
        deve_repassar = processar_mensagem(card, msg_id, user, conteudo)
        if deve_repassar:
            enviar_para_proximo(card)
    finally:
        client_socket.close()

def processar_mensagem(card, msg_id, user, conteudo):
    kwargs = {'msg_id': msg_id}
    for command, handler in COMMAND_HANDLERS.items():
        if conteudo.strip().startswith(command):
            import inspect
            sig = inspect.signature(handler)
            handler_args = {k: v for k, v in kwargs.items() if k in sig.parameters}
            parar_ciclo = handler(user, conteudo, **handler_args)
            return not parar_ciclo
    return True

# --- ELEIÇÃO ---
def eleger_lider(msg):
    global LIDER, STATUSLIDER, NETWORK_MEMBERS
    partes = msg.strip().upper().split(">>")
    if len(partes) == 2 and partes[0] == "@LIDER":
        ip_iniciador = partes[1]
        if ip_iniciador == MEU_ID and STATUSLIDER == "waiting":
            LIDER = MEU_ID
            STATUSLIDER = "elected"
            if not NETWORK_MEMBERS:
                NETWORK_MEMBERS = [MEU_ID]

            print(f"\n[ELEIÇÃO] 🏆 Novo líder estabelecido: {LIDER} 👑")
            cliente_envio(username, f"@LIDER>>{LIDER}>>ELECTED")
            time.sleep(1)
            iniciar_construcao_lista() # <-- NOVO LÍDER RECONSTRÓI A LISTA
            threading.Thread(target=enviar_heartbeat, daemon=True, name="enviar_heartbeat").start()
            if not any(t.name == "multicast_listener" for t in threading.enumerate()):
                threading.Thread(target=multicast_listener, daemon=True, name="multicast_listener").start()
            return True
    elif len(partes) == 3 and partes[2] == "ELECTED":
        ip_lider = partes[1]
        if LIDER is None:
            LIDER = ip_lider
            STATUSLIDER = "elected"
            print(f"\n[ELEIÇÃO] Líder eleito: {LIDER} 👑")
        return True
    time.sleep(1)
    if not NETWORK_MEMBERS:
        iniciar_construcao_lista()
    else:
        distribuir_lista_membros()
    return False





def iniciar_eleicao():
    global STATUSLIDER, LIDER, ultimo_heartbeat

    tempo_desde_ultimo_heartbeat = time.time() - ultimo_heartbeat
    condicao_falha_hb = (LIDER is not None and tempo_desde_ultimo_heartbeat > 15)
    condicao_saida_lider = (LIDER is None and STATUSLIDER != "connected")

    if (condicao_falha_hb or condicao_saida_lider) and STATUSLIDER != "waiting":
        LIDER = None
        STATUSLIDER = "waiting"
        ultimo_heartbeat = time.time()

        print(f"\n[ELEIÇÃO] Iniciei uma nova eleição... (motivo: {'HB falhou' if condicao_falha_hb else 'sem líder'})")
        espera_eleicao = random.uniform(2.0, 8.0)
        print(f"[ELEIÇÃO] Aguardando {espera_eleicao:.2f}s antes de enviar o token...")
        time.sleep(espera_eleicao)
        cliente_envio(username, f"@LIDER>>{MEU_ID}")
    else:
        if MODO == "debug":
            print("\n[ELEIÇÃO] Condições não atendidas (Líder OK).")

             
# --- GERENCIAMENTO DE REDE ---
def iniciar_construcao_lista():
    if LIDER == MEU_ID:
        # Quando o líder (novo ou antigo) constrói a lista, ele deve ser o primeiro
        global NETWORK_MEMBERS
        NETWORK_MEMBERS = [MEU_ID]
        cliente_envio(username, f"@LIST_BUILD>>{MEU_ID}>>{MEU_ID}")

def distribuir_lista_membros():
    if LIDER == MEU_ID:
        membros_str = ",".join(NETWORK_MEMBERS)
        cliente_envio(username, f"@LIST_UPDATE>>{membros_str}")

def gerenciar_entrada_de_no(novo_no):
    pass

# *** AÇÃO 2: LÓGICA DE REPARO ATUALIZADA ***
def gerenciar_saida_de_no(no_saindo):
    global NETWORK_MEMBERS, PROXIMO_IP, PROXIMO_PORTA
    if no_saindo not in NETWORK_MEMBERS:
        return

    # Lista agora reflete o anel: [P1, P_ultimo, P_penultimo, ..., P2]
    # Anel: P1 -> P_ultimo -> P_penultimo -> ... -> P2 -> P1
    
    try:
        idx = NETWORK_MEMBERS.index(no_saindo)
    except ValueError:
        print(f"[ERRO] Nó {no_saindo} saiu mas não estava na lista {NETWORK_MEMBERS}")
        return

    predecessor = None
    sucessor = None

    # Caso 1: Nó P_ultimo (idx 1, o "head" do anel) está saindo.
    # O Líder (P1) é o predecessor e P_penultimo (idx 2) é o sucessor.
    if idx == 1:
        predecessor = NETWORK_MEMBERS[0] # P1 (Líder)
        # Se P_penultimo existir (mais de 2 nós), ele é o sucessor
        if len(NETWORK_MEMBERS) > 2:
            sucessor = NETWORK_MEMBERS[idx + 1] # P_penultimo
        else:
            # Se só havia P1 e P_ultimo (P2), o sucessor é P1
            sucessor = NETWORK_MEMBERS[0] # P1 (Líder)

    # Caso 2: P2 (idx -1, o "tail" do anel) está saindo.
    # O predecessor é P3 (idx -2) e o sucessor é P1 (Líder).
    elif idx == len(NETWORK_MEMBERS) - 1:
        predecessor = NETWORK_MEMBERS[idx - 1] # P3 (P_ante-tail)
        sucessor = NETWORK_MEMBERS[0] # P1 (Líder)

    # Caso 3: Um nó do "meio" (P3, P4, etc.) está saindo.
    # O predecessor é P(i+1) e o sucessor é P(i-1).
    else:
        predecessor = NETWORK_MEMBERS[idx - 1]
        sucessor = NETWORK_MEMBERS[idx + 1]
    # Agora, se o nó saindo for o PRÓXIMO do líder (P_ultimo), o líder precisa
    # se auto-atualizar.
    if no_saindo == f"{PROXIMO_IP}:{PROXIMO_PORTA}":
        print(f"[REDE] Reparando meu próprio próximo. {no_saindo} saiu.")
        novo_ip, nova_porta = sucessor.split(":")
        PROXIMO_IP = novo_ip
        PROXIMO_PORTA = int(nova_porta)
        print(f"[REDE] Meu novo próximo é {sucessor}")
    
    # Envia a mensagem de reparo para o nó predecessor
    # (O nó que *apontava* para o nó que saiu)
    cliente_envio(username, f"@RECONNECT>>{predecessor}>>{sucessor}")
    
    # Remove o nó da lista e distribui
    NETWORK_MEMBERS.remove(no_saindo)
    time.sleep(1)
    distribuir_lista_membros()

# --- MULTICAST ---
def multicast_listener():
    """Líder escuta pedidos de entrada via multicast e responde via unicast."""
    global PROXIMO_IP, PROXIMO_PORTA, NETWORK_MEMBERS # Precisamos modificar o próximo do líder

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MULTICAST_PORT))
    mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton('0.0.0.0')
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    print(f"[MULTICAST] Escutando em {MULTICAST_GROUP}:{MULTICAST_PORT} (iface {MEU_IP})")

    while True:
        data, addr_remoto = sock.recvfrom(1024) # addr_remoto é (ip, porta_udp_efemera) do novo nó
        msg = data.decode('utf-8')
        
        if msg.startswith("DISCOVER:"):
            _, ip, porta_tcp = msg.split(":")
            novo_no = f"{ip}:{porta_tcp}"
            
            # Ignora a si mesmo se o DISCOVER der a volta
            if novo_no == MEU_ID:
                continue

            print(f"[MULTICAST] Pedido de entrada recebido de {novo_no}")

            # 🔧 LÓGICA DE INSERÇÃO SIMPLIFICADA
            
            # 1. Guarda o próximo nó atual do líder
            if PROXIMO_IP:
                proximo_atual = f"{PROXIMO_IP}:{PROXIMO_PORTA}"
            else:
                # Se for o primeiro nó a se conectar, ele aponta para o líder
                proximo_atual = MEU_ID 

            # 2. Responde ao novo nó, dizendo para ele apontar para o 'proximo_atual'
            #    Formato: JOIN | {ip_proximo}:{porta_proximo} | {id_lider}
            resposta = f"JOIN|{proximo_atual}|{MEU_ID}"
            
            # Envia a resposta para o IP e a porta UDP de onde veio a msg
            sock.sendto(resposta.encode('utf-8'), addr_remoto) 
            print(f"[MULTICAST] Resposta enviada para {addr_remoto}: {resposta}")

            # 3. ATUALIZA O PRÓXIMO DO LÍDER para apontar para o novo nó
            PROXIMO_IP = ip
            PROXIMO_PORTA = int(porta_tcp)
            print(f"[REDE] Anel atualizado: Líder -> {novo_no} -> {proximo_atual}")

            # 4. Atualiza a lista de membros e distribui
            if novo_no not in NETWORK_MEMBERS:
                # *** CORREÇÃO AQUI ***
                # Insere o novo nó na posição 1 (logo após o líder)
                NETWORK_MEMBERS.insert(1, novo_no)
                distribuir_lista_membros()

def multicast_discovery():
    """Nó novo envia DISCOVER e aguarda resposta do líder"""
    global PROXIMO_IP, PROXIMO_PORTA, LIDER, STATUSLIDER, NETWORK_MEMBERS

    # Se não for a primeira inicialização (estado "lost"), não espera 10s
    if STATUSLIDER != "lost":
        print("[MULTICAST] Aguardando 10 segundos antes de iniciar descoberta...")
        for i in range(10, 0, -1):
            print(f"   -> iniciando em {i}s...", end="\r")
            time.sleep(1)
        print(" " * 30, end="\r")
    else:
        print("[REDE] Re-executando descoberta imediatamente...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.inet_aton(MEU_IP))
    sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((MEU_IP, 0))

    msg = f"DISCOVER:{MEU_IP}:{MEU_PORTA}" 
    sock.sendto(msg.encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
    print(f"[MULTICAST] Pedido de entrada enviado: {msg}")

    sock.settimeout(6)
    try:
        data, addr = sock.recvfrom(1024)
        resposta = data.decode("utf-8").strip()

        if resposta.startswith("JOIN|"):
            _, prox_id, lider_id = resposta.split("|")
            
            PROXIMO_IP, PROXIMO_PORTA_STR = prox_id.split(":")
            PROXIMO_PORTA = int(PROXIMO_PORTA_STR)
            
            LIDER = lider_id
            STATUSLIDER = "connected"
            
            print(f"[MULTICAST] Conectado ao anel. Próximo: {PROXIMO_IP}:{PROXIMO_PORTA}, Líder: {LIDER}")
            
            time.sleep(1) 
    
    except socket.timeout:
        espera = random.uniform(1.5, 10.5)
        print(f"[MULTICAST] Nenhum líder respondeu. Aguardando {espera:.1f}s antes de assumir liderança... ⌚")
        time.sleep(espera)
        
        LIDER = MEU_ID
        STATUSLIDER = "elected"
        NETWORK_MEMBERS = [MEU_ID] 
        PROXIMO_IP = MEU_IP         
        PROXIMO_PORTA = MEU_PORTA
        
        threading.Thread(target=multicast_listener, daemon=True, name="multicast_listener").start()
        threading.Thread(target=enviar_heartbeat, daemon=True, name="enviar_heartbeat").start()
        print(f"[ELEIÇÃO] 🏆 Assumindo papel de líder inicial: {LIDER}")
    
    finally:
        # Libera o lock se o adquirimos
        if RECONEXAO_LOCK.locked():
            RECONEXAO_LOCK.release()

            
# --- FUNÇÕES GERAIS ---
def servidor():
    global MEU_PORTA, MEU_ID
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    while True:
        try:
            s.bind((MEU_IP, MEU_PORTA))
            MEU_ID = f"{MEU_IP}:{MEU_PORTA}"
            break
        except OSError:
            MEU_PORTA += 1
    s.listen(50)
    print(f"Servidor rodando em {MEU_ID}")
    while True:
        c, addr = s.accept()
        threading.Thread(target=tratar_conexao, args=(c, addr)).start()

def configurar_username():
    global username
    username = input("Digite o nome de usuário: ")


def graceful_exit():
    global PROXIMO_IP, PROXIMO_PORTA
    if LIDER == MEU_ID:
        if len(NETWORK_MEMBERS) > 1:
            predecessor_no_anel = NETWORK_MEMBERS[-1]
            sucessor_no_anel = NETWORK_MEMBERS[1]
            msg = f"@LEADER_EXIT>>{MEU_ID}>>{predecessor_no_anel}>>{sucessor_no_anel}"
            cliente_envio(username, msg)
        else:
            cliente_envio(username, "@LEADER_EXIT_SOLO")
    else:
        predecessor = None
        sucessor = None
        if MEU_ID in NETWORK_MEMBERS:
            idx = NETWORK_MEMBERS.index(MEU_ID)
            predecessor = NETWORK_MEMBERS[idx - 1] if idx > 0 else NETWORK_MEMBERS[-1]
            sucessor = NETWORK_MEMBERS[(idx + 1) % len(NETWORK_MEMBERS)]
        msg = f"@EXIT>>{MEU_ID}>>{predecessor}>>{sucessor}"
        cliente_envio(username, msg)

    print("Saindo da rede... 👋")

    # ⏳ Correção crítica
    time.sleep(1)  # 1 segundo é suficiente para o TCP completar envio
    os._exit(0)

def signal_handler(sig, frame):
    print("\n[INFO] Encerrando nó de forma segura... 🏃👮")
    graceful_exit()

signal.signal(signal.SIGINT, signal_handler)

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
        print("  Ainda não conheço os outros membros da rede. 😔")
    print("-" * 30)

def local_cmd_lider():
    """Inicia uma eleição ou mostra o líder atual."""
    if LIDER:
        print(f"\nO líder atual é: {LIDER} 👑")
    else:
        print("Nenhum líder conhecido. Iniciando eleição...")
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

# --- EXECUÇÃO PRINCIPAL ---
if __name__ == "__main__":
    threading.Thread(target=servidor, daemon=True, name="servidor").start()
    time.sleep(1)
    multicast_discovery()
    configurar_username()
    threading.Thread(target=monitorar_heartbeat, daemon=True, name="monitorar_heartbeat").start()

    local_cmd_help()

    print("\n--- Comandos Disponíveis ---")
    print("  @LIDER | @LIST | @MEMBERS | FIM | @HELP")
    
    while True:
        texto = input("> ")
        comando = texto.strip().upper()

        handler = LOCAL_COMMANDS.get(comando)

        if handler:
            handler()
        elif comando == "FIM":
            graceful_exit()
        else:
            cliente_envio(username, texto)