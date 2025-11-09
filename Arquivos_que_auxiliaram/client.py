# Cria um socket TCP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    # Conecta ao servidor
    client_socket.connect(('localhost', 65432))

    # Envia uma mensagem
    message = "Olá, servidor!"
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
    client_socket.close()