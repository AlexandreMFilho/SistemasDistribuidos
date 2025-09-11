import socket 

##ifconfig - comando achar ip no linux

IP, PORTA = '10.1.23.57',9002


##Cria o sockeet
server_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

##Bind IP, PORTA
server_socket.bind((IP,PORTA))

##Listen
server_socket.listen(5)

print("Servidor pronto e aguardando conexões...")

##Accept
while True:
    Client_socket, client_address = server_socket.accept()
    try:
        ##Tratar a mensagem (Print)
        print(f"Conexão estabelecida com {client_address}")
        msg = Client_socket.recv(1024).decode('utf-8')
        msg_list = msg.split('|')
        if len(msg_list) != 2:
            raise Exception
        else:    
            username, mensagem = msg_list[0], msg_list[1]
            print(f"{username}:{mensagem}")
            ##Responder
            Client_socket.send("OK".encode('utf-8'))
            
    except KeyError:
        Client_socket.send("Erro".encode('utf-8'))
    finally:
        server_socket.close()