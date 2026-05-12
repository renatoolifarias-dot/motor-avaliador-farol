# Configuração de DNS — avaliador.farolpublico.com.br

## O que vamos fazer

Apontar o subdomínio `avaliador.farolpublico.com.br` para o IP do seu servidor próprio (VPS Ubuntu).

## Pré-requisito

Você precisa do **IP público (IPv4)** do seu VPS. Você pega isso assim:

- No painel do seu provedor de VPS (Vultr, DigitalOcean, Hetzner, OVH, Locaweb Cloud, etc.) — geralmente aparece como "IP público" ou "Endereço IPv4"
- Ou via SSH no próprio servidor: `curl ifconfig.me`

Formato esperado: `xxx.xxx.xxx.xxx` (4 grupos de 1 a 3 dígitos)

## Passo a passo no painel do Locaweb

1. Acesse o **painel de hospedagem da Locaweb**
2. Vá em **DNS** ou **Zona DNS** do domínio `farolpublico.com.br`
3. Clique em **Adicionar registro** (ou "Novo registro")
4. Preencha:

   | Campo | Valor |
   |---|---|
   | **Tipo** | A |
   | **Nome / Host / Subdomínio** | `avaliador` (só essa palavra, sem `.farolpublico.com.br`) |
   | **Valor / Aponta para** | (o IP do seu VPS, ex: `192.168.1.100`) |
   | **TTL** | 3600 (1 hora) ou 300 (5 min) se preferir mudar rápido |

5. Salve.

## Validar que funcionou

Depois de 5-15 minutos (propagação do DNS), abra um terminal e rode:

```bash
nslookup avaliador.farolpublico.com.br
```

ou no Windows PowerShell:

```powershell
Resolve-DnsName avaliador.farolpublico.com.br
```

O resultado deve mostrar o IP do seu VPS. Se aparecer outro IP ou "não encontrado", aguarde mais um pouco.

Também dá pra checar via web em https://dnschecker.org → digita o subdomínio → confere se aponta para o IP certo nos vários servidores do mundo.

## Por que apenas DNS é o suficiente

- O **Coolify** (que vamos instalar no VPS) automatiza:
  - Geração do certificado SSL via Let's Encrypt
  - Configuração do reverse proxy (Caddy)
  - Redirect HTTP → HTTPS

- O Locaweb continua hospedando o portal público (`farolpublico.com.br` raiz) — o subdomínio é uma entrada DNS separada que aponta pra outro servidor. **Não interfere no portal atual.**

## Reverse: como desfazer

Se quiser desativar o subdomínio depois, é só:

1. No painel DNS, encontrar o registro `avaliador`
2. Excluir o registro

O domínio principal `farolpublico.com.br` continua funcionando normal.

## Troubleshooting

**"Não consigo achar onde editar DNS no Locaweb"** — entra no painel de hospedagem, vai em "Meus produtos" → "Hospedagem" → seleciona `farolpublico.com.br` → "DNS" ou "Configurações DNS" ou "Zona DNS". Se não achar, pede suporte da Locaweb.

**"O TTL não deixa eu escolher"** — alguns painéis deixam só TTL fixo. Não tem problema, segue assim.

**"Posso usar CNAME em vez de A?"** — Sim, se o seu VPS tem um hostname tipo `meuserver.exemplo.com`. Mas A com IP direto é mais simples e rápido.

**"E se eu mudar o IP do VPS depois?"** — Só editar o registro DNS com o IP novo. Propagação leva minutos.
