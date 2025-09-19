import socket
import threading
import uuid
from collections import deque

# Configuração do nó
MEU_IP = "127.0.0.1"
MEU_PORTA = 9001
PROXIMO_IP = "127.0.0.1"
PROXIMO_PORTA = 9002
LIDER = None # None | "IP:PORTA"
STATUSLIDER = None # None | "waiting" | "elected"

# Cache de mensagens (FIFO com limite de 50)
cache = deque(maxlen=50)
username = "system" # Default username

def enviar_para_proximo(msg):
    """Envia a mensagem para o próximo nó da cadeia"""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((PROXIMO_IP, PROXIMO_PORTA))
        client_socket.send(msg.encode('utf-8'))
        client_socket.close()
    except Exception as e:
        print(f"Erro ao enviar para próximo nó: {e}")

def cliente_envio(user, content):
    """Gera id|user|content e envia para o próximo nó (padrão)."""
    msg_id = str(uuid.uuid4())
    u = user if user else username
    msg = f"{msg_id}|{u}|{content}"
    enviar_para_proximo(msg)

# ---- FUNÇÃO TRATAR_CONEXAO (MODIFICADA) ----
def tratar_conexao(client_socket, addr):
    """Thread que trata cada conexão"""
    try:
        msg = client_socket.recv(1024).decode("utf-8")
        if not msg:
            return
            
        partes = msg.split("|")
        if len(partes) != 3:
            return

        msg_id, user, conteudo = partes
        card = f"{msg_id}|{user}|{conteudo}"

        if card in cache:
            return # Mensagem duplicada, ignora.

        cache.append(card)
        print(f"[{addr}] {user}: {conteudo}")

        # ----- LÓGICA CENTRALIZADA DE ELEIÇÃO E REPASSE -----
        deve_repassar = True
        
        # Se a mensagem for de eleição, processa o estado do nó
        if conteudo.strip().upper().startswith("@LIDER"):
            # A função eleger_lider agora retorna se o ciclo da mensagem deve ser quebrado
            parar_ciclo = eleger_lider(conteudo)
            if parar_ciclo:
                deve_repassar = False

        if deve_repassar:
            enviar_para_proximo(card)
        # ---------------------------------------------------

    finally:
        client_socket.close()

def servidor():
    """Servidor multithread que recebe mensagens"""
    global MEU_PORTA
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            server_socket.bind((MEU_IP, MEU_PORTA))
            break
        except OSError:
            print(f"Porta {MEU_PORTA} já em uso, tentando {MEU_PORTA+1}...")
            MEU_PORTA += 1
    server_socket.listen(5)
    print(f"Servidor rodando em {MEU_IP}:{MEU_PORTA}")
    while True:
        client_socket, addr = server_socket.accept()
        threading.Thread(target=tratar_conexao, args=(client_socket, addr)).start()

def configurar_username():
    global username
    username = input("Digite o nome de usuário:\n ")

# ---- FUNÇÃO ELEGER_LIDER (MODIFICADA) ----
def eleger_lider(msg):
    """
    Processa mensagens de eleição e atualiza o estado do nó.
    Retorna True se a mensagem original não deve ser mais repassada.
    Retorna False se a mensagem original deve continuar circulando.
    """
    global LIDER, STATUSLIDER
    
    conteudo = msg.strip().upper()
    partes = conteudo.split(">>")

    # Caso 1: Recebeu um token de votação "@LIDER>>IP:PORTA"
    if len(partes) == 2 and partes[0] == "@LIDER":
        ip_iniciador = partes[1]
        # Se o token que eu iniciei voltou para mim
        if ip_iniciador == f"{MEU_IP}:{MEU_PORTA}" and STATUSLIDER == "waiting":
            print(f"Meu token de eleição retornou. Sou o novo líder!")
            LIDER = ip_iniciador
            STATUSLIDER = "elected"
            # Crio uma NOVA mensagem para ANUNCIAR que sou o líder
            cliente_envio(username, f"@LIDER>>{LIDER}>>ELECTED")
            # O token de votação original não precisa mais circular.
            return True # PARAR o ciclo do token de votação
        
    # Caso 2: Recebeu um anúncio de líder eleito "@LIDER>>IP:PORTA>>ELECTED"
    elif len(partes) == 3 and partes[0] == "@LIDER" and partes[2] == "ELECTED":
        ip_lider = partes[1]
        if LIDER is None:
            # É a primeira vez que vejo este anúncio.
            LIDER = ip_lider
            STATUSLIDER = "elected"
            print(f"Líder reconhecido: {LIDER}")
            # Deixo o anúncio passar para que outros saibam.
            return False # CONTINUAR o ciclo do anúncio
        else:
            # Se eu já tenho um líder, o anúncio completou a volta no anel.
            print(f"Anúncio de líder já processado. Interrompendo repasse.")
            return True # PARAR o ciclo do anúncio

    # Para qualquer outro caso (ex: token de outro nó), a mensagem deve continuar circulando.
    return False

def iniciar_eleicao():
    """Função para ser chamada pelo usuário para começar uma eleição."""
    global STATUSLIDER
    if LIDER is None and STATUSLIDER is None:
        STATUSLIDER = "waiting"
        print("Iniciando processo de eleição...")
        cliente_envio(username, f"@LIDER>>{MEU_IP}:{MEU_PORTA}")
    else:
        print(f"Uma eleição já está em andamento ou um líder já foi eleito: {LIDER}")


if __name__ == "__main__":
    threading.Thread(target=servidor, daemon=True).start()
    
    aux = input(f"IP do próximo nó é {PROXIMO_IP}:{PROXIMO_PORTA}. Pressione Enter ou digite um novo IP: ")
    if aux:
        PROXIMO_IP = aux
    
    aux2 = input(f"Porta do próximo nó é {PROXIMO_PORTA}. Pressione Enter ou digite uma nova porta: ")
    if aux2:
        PROXIMO_PORTA = int(aux2)
    
    configurar_username()
    print("-" * 30)
    print(f"Nó configurado em {MEU_IP}:{MEU_PORTA}")
    print(f"Conectado ao próximo nó em {PROXIMO_IP}:{PROXIMO_PORTA}")
    print("Digite a mensagem ou '@LIDER' para iniciar uma eleição, ou 'FIM' para sair.")
    print("-" * 30)

    while True:
        texto = input()
        if texto.strip().upper() == "FIM":
            break
        if texto.strip().upper() == "@LIDER":
            iniciar_eleicao()
            continue
        
        cliente_envio(username, texto)