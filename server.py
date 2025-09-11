import socket

# Cria um socket TCP/IP
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Liga o socket a um endereço e porta
server_socket.bind(('localhost', 65432))

# Define o número máximo de conexões em fila
server_socket.listen(5)

print("Servidor pronto e aguardando conexões...")

while True:
    # Aceita uma nova conexão
    client_socket, client_address = server_socket.accept()
    print(f"Conexão estabelecida com {client_address}")

    try:
        # Recebe dados do cliente
        data = client_socket.recv(1024)

        # Decodifica a mensagem recebida
        decoded_data = data.decode('utf-8')
        print(f"Recebido: {decoded_data}")

        # Envia uma resposta ao cliente
        response = "Mensagem recebida"
        client_socket.send(response.encode('utf-8'))

    except UnicodeDecodeError as e:
        print(f"Erro de decodificação: {e}")
        client_socket.send("Erro de decodificação".encode('utf-8'))

    finally:
        # Fecha a conexão
        client_socket.close()