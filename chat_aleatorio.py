import socket
import random
from threading import Thread

sujeitos = ["O gato", "A Maria", "O sistema", "Um robô", "O professor", "O carro", "A criança", "O cachorro", "O programador", "O cientista"]
verbos = ["correu", "saltou", "falhou", "funcionou", "desapareceu", "apareceu", "programou", "descobriu", "construiu", "quebrou"]
objetos = ["na rua", "na escola", "no trabalho", "em casa", "na internet", "no parque", "no laboratório", "no quarto", "no mercado", "na estrada"]


def chat(socket):
    try:
        msg = socket.recv(1024).decode('utf-8')
        msg_list = msg.split('|')
        if len(msg_list) != 2:
            raise Exception
        else:
            username, mensagem = msg_list[0], msg_list[1]
            resposta = f"{random.choice(sujeitos)} {random.choice(verbos)} {random.choice(objetos)}."
            socket.send(resposta.encode('utf-8'))
            print(f"{username}: {mensagem}")
            print(f"chat: {resposta}")
    except Exception:
        socket.send("ERROR".encode('utf-8'))
    finally:
        socket.close()
            
    

IP, PORTA = '10.1.23.44', 9003

# Criar o Socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind IP, Porta
server_socket.bind((IP, PORTA))

# Listen
server_socket.listen(10)

print("Servidor iniciado...")

#idx = 0
# Accept
while True:
    client_socket, client_address = server_socket.accept()
    t = Thread(target=chat, args=(client_socket,))
    t.start()
