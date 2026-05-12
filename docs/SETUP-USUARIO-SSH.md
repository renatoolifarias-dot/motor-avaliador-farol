# Setup do usuário SSH no servidor

Vamos criar um usuário dedicado (`farol`) com acesso `sudo` no VPS. Esse usuário é o que vamos usar pra gerenciar o sistema.

## Pré-requisito

Você precisa de acesso `root` (ou outro usuário com `sudo`) no servidor pra criar esse usuário. Geralmente é o usuário inicial que veio do provedor de VPS.

## Opção A — Gerar a chave SSH no seu PC primeiro (mais seguro)

### No Windows (PowerShell):

```powershell
# Cria par de chaves (pressiona ENTER 3x para passar pelas perguntas)
ssh-keygen -t ed25519 -C "farol@meu-pc"

# Mostra a public key (vou precisar copiar isso)
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

A public key tem este formato:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... farol@meu-pc
```

**Copia essa linha inteira.** Você vai colar dentro do servidor no passo abaixo.

A private key fica em `C:\Users\renat\.ssh\id_ed25519` e **NUNCA deve sair do seu PC**.

## Passo a passo no servidor (você executa via SSH como root)

Acesse o servidor com o usuário inicial (geralmente `root` ou `ubuntu`):

```bash
ssh root@<IP_DO_SERVIDOR>
```

Cole os comandos abaixo (um por vez, ou tudo de uma vez):

```bash
# 1. Criar o usuário 'farol' com home directory
adduser --disabled-password --gecos "" farol

# 2. Dar permissão sudo (sem precisar senha pra simplificar)
usermod -aG sudo farol
echo "farol ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/farol
chmod 440 /etc/sudoers.d/farol

# 3. Preparar pasta SSH do usuário
mkdir -p /home/farol/.ssh
chmod 700 /home/farol/.ssh
touch /home/farol/.ssh/authorized_keys
chmod 600 /home/farol/.ssh/authorized_keys
chown -R farol:farol /home/farol/.ssh

# 4. Adicionar SUA public key (substitua a string entre aspas pela sua key copiada do passo anterior)
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... farol@meu-pc" >> /home/farol/.ssh/authorized_keys

# 5. Validar que funciona (sem desconectar a sessão atual!)
# Abre OUTRO terminal no seu PC e tenta:
#   ssh farol@<IP_DO_SERVIDOR>
# Se logar sem pedir senha, deu certo.
```

## Endurecer SSH (opcional mas recomendado depois)

Quando você confirmar que `ssh farol@IP` funciona com chave, pode **desabilitar login por senha e como root**:

```bash
# Edite o sshd_config
sudo nano /etc/ssh/sshd_config

# Procure e altere (ou adicione) estas linhas:
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes

# Salve (Ctrl+O, Enter, Ctrl+X)
# Reinicie o SSH
sudo systemctl restart ssh
```

**ATENÇÃO:** só faça isso DEPOIS de confirmar que o login com chave do `farol` funciona. Se algo der errado e você ficar travado fora, vai precisar de console do provedor pra recuperar.

## O que me passar quando terminar

1. **IP público do servidor** (xxx.xxx.xxx.xxx)
2. **Usuário criado**: `farol`
3. Confirmação que `ssh farol@IP` funciona com chave (sem pedir senha)

Não precisa me mandar a private key. Eu vou te guiar nos comandos via SSH; você executa, copia e cola a saída quando eu pedir.

## Alternativa simplificada (se preferir só pra agilizar)

Se quiser, pode usar o usuário inicial mesmo (ex: `root` ou `ubuntu`) e pular essa parte. **Mas:**
- Menos seguro
- Tudo vai estar como root, qualquer erro afeta o sistema todo
- Não é recomendado pra produção, mas pra PoC funciona

Pra essa rota:
- Só me passa o usuário inicial e a senha/chave que você usa hoje pra logar
