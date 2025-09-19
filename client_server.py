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

def enviar_para_proximo(msg):
    """Envia a mensagem para o próximo nó da cadeia"""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((PROXIMO_IP, PROXIMO_PORTA))
        client_socket.send(msg.encode('utf-8'))
        client_socket.close()
    except Exception as e:
        print(f"Erro ao enviar para próximo nó: {e}")

def tratar_conexao(client_socket, addr):
    """Thread que trata cada conexão"""
    try:
        msg = client_socket.recv(1024).decode("utf-8")
        if not msg:
            return

        # Estrutura esperada: id|username|mensagem
        partes = msg.split("|")
        if len(partes) != 3:
            return

        msg_id, user, conteudo = partes
        card = f"{msg_id}|{user}|{conteudo}"

        if card in cache:
            lixo = 0
            # print(f"[{addr}] Mensagem duplicada ignorada.")
        else:
            cache.append(card)
            print(f"[{addr}] {user}: {conteudo}")
            # Repassar ao próximo nó
            enviar_para_proximo(card)

    finally:
        client_socket.close()

def servidor():
    """Servidor multithread que recebe mensagens"""
    global MEU_PORTA
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Tentar até achar uma porta livre
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

def cliente_envio(user, conteudo):
    """Cliente usado pelo próprio nó para iniciar mensagens"""
    msg_id = str(uuid.uuid4())
    msg = f"{msg_id}|{user}|{conteudo}"
    enviar_para_proximo(msg)




def configurar_username():
    global username
    username = input("Digite o nome de usuário:\n ")

def eleger_lider(msg):
    #Mensagem pode ser @LIDER ou @LIDER|IP:PORTA
    global LIDER, STATUSLIDER

    print(f"Eleição de líder iniciada. Status atual: LIDER={LIDER}, STATUSLIDER={STATUSLIDER}\nmensagem: {msg}")

    if(LIDER == None and STATUSLIDER == None):
        enviar_para_proximo("@LIDER")
        STATUSLIDER = 'waiting'
        print(f"STATUSLIDER atualizado para {STATUSLIDER} Aguardando eleição de líder...")

    if(LIDER == None and STATUSLIDER == 'waiting'):
        if msg.startswith("@LIDER"):
            LIDER = f"{MEU_IP}:{MEU_PORTA}"
            STATUSLIDER = 'elected'
            enviar_para_proximo(f"@LIDER|{MEU_IP}:{MEU_PORTA}")
            print(f"Novo líder eleito sou eu: {LIDER}")

        if msg.startswith("@LIDER|"):
            ip_rec = msg.split("|")[1]
            if(ip_rec != f"{MEU_IP}:{MEU_PORTA}"):
                LIDER = ip_rec
                STATUSLIDER = 'elected'
                enviar_para_proximo(f"@LIDER|{LIDER}")
                print(f"Novo líder eleito não sou eu é o: {LIDER}")

            else:
                lixo = 0  
                print("Recebi minha própria mensagem de líder, ignorando...")

    if(LIDER != None and STATUSLIDER == 'elected'):
        if msg.startswith("@LIDER") or msg.startswith("@LIDER|"):
            enviar_para_proximo(f"@LIDER|{LIDER}")
            print(f"Líder já eleito: {LIDER}, ignorando nova eleição.") 
        
if __name__ == "__main__":
    # Inicia servidor em thread
    threading.Thread(target=servidor, daemon=True).start()

    # Loop para enviar mensagens manualmente
    
    aux = input(f"Comunicando com {PROXIMO_IP}:{PROXIMO_PORTA}.\nDigite o IP que você deseja se conectar Ou pressione Enter para continuar...\n")
    if(aux):
        PROXIMO_IP = aux
        print(f"IP do Próximo nó alterado para {PROXIMO_IP}")

    aux2 = input(f"Digite a PORTA que você deseja se conectar:\n Ou pressione Enter para continuar...\n")
    if(aux2):
        PROXIMO_PORTA = int(aux2)
        print(f"Porta do Próximo nó alterado para {PROXIMO_PORTA}")
    
    configurar_username()

    print(f"Servidor rodando em {MEU_IP}:{MEU_PORTA}")
    print(f"Comunicando com {PROXIMO_IP}:{PROXIMO_PORTA}")

    while True:
        texto = input("Digite a mensagem (ou FIM para sair): ")
        if texto.strip().upper() == "FIM":
            break
        if texto.strip().upper() == "@LIDER" or texto.strip().startswith("@LIDER|"):
            #pegar também a mensagem recebida
            eleger_lider(texto)


        cliente_envio(username, texto)
