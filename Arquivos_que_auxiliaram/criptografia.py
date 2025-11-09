import rsa

def encript(mensagem, public):
    return rsa.encrypt(mensagem.encode(), public)

def decript(mensagem, privado):
    return rsa.decrypt(mensagem, privado).decode()
# https://www.geeksforgeeks.org/python/how-to-encrypt-and-decrypt-strings-in-python/