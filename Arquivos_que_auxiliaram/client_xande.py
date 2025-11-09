import socket

# Cria um socket TCP
erro_conexao = 0
while True:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Conecta ao servidor
        client_socket.connect(('172.31.230.241', 9004))

        # Envia uma mensagem
        mensagem = input("digite a mensagem:\n")
        message = f"Xande|{mensagem}"
        client_socket.send(message.encode('utf-8'))

        # Recebe a resposta do servidor
        response = client_socket.recv(1024)
        print(f"Resposta do servidor: {response.decode('utf-8')}")

    except ConnectionRefusedError as e:
        erro_conexao += 1
        if erro_conexao > 3:
            print("Número máximo de tentativas de conexão atingido. Encerrando.")
            break
        else:
            print(f"Erro de conexão: {e}")

    except UnicodeEncodeError as e:
        print(f"Erro de codificação: {e}")

    finally:
        # Fecha o socket
        client_socket.close()
        if 'mensagem' in locals() and mensagem == "FIM":
            break