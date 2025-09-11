import socket 

# Cria um socket TCP

while True:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Conecta ao servidor
        client_socket.connect(('10.1.23.44', 9002))

        # Envia uma mensagem
        mensagem = input("digite a mensagem:\n")
        message = f"Xande|{mensagem}"
        client_socket.send(message.encode('utf-8'))

        # Recebe a resposta do servidor
        response = client_socket.recv(1024)
        print(f"Resposta do servidor: {response.decode('utf-8')}")

    except ConnectionRefusedError as e:
        print(f"Erro de conexão: {e}")

    except UnicodeEncodeError as e:
        print(f"Erro de codificação: {e}")

    finally:
        # Fecha o socket
        if(mensagem == "FIM"):
            client_socket.close()