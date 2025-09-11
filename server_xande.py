import socket 

##ifconfig - comando achar ip no linux

IP, PORTA = '172.31.230.241',9004

##Cria o sockeet
server_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

##Bind IP, PORTA
server_socket.bind((IP,PORTA))

##Listen
server_socket.listen(5)

print("Servidor pronto e aguardando conexões...")
cache=[]
i=0
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
            card = f"{username}:{mensagem}"

            #Manutenção da Cache ()
            if len(cache) >= 10:
                cache.pop(0)

            #Não duplicar mensagem
            if card in cache: 
                i=i+1
            else:
                cache.append(card)
                print(card)
                ##Responder
                Client_socket.send("OK".encode('utf-8'))
            
    except KeyError:
        Client_socket.send("Erro".encode('utf-8'))
    finally:
        if 'mensagem' in locals() and mensagem == "FIM":
            break