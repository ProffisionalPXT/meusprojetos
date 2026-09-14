# 🚨 LEIA-ME PRIMEIRO: GUIA RÁPIDO PARA O PC DE CASA

Bem-vindo! Este repositório contém os códigos-fonte atualizados, configurações e histórico completo dos nossos 3 robôs de automação:
1. **🤖 Robô GW** (`/gw-motorista-bot`): Cadastro de Motoristas, Veículos e Proprietários no GW com OCR inteligente.
2. **🤖 Robô de Programação CHEP** (`/chep-motorista-bot`): Alocação de coletas e remessas no JDA SmartBench CHEP com lógica de cascata.
3. **🤖 Robô de Ocorrências CHEP** (`/chep_occurrence_bot`): Monitoramento e abertura automática de chamados de ocorrência no portal CMA Service Desk.

---

## ⚡ Passo a Passo Rápido para Usar no PC de Casa

### 1️⃣ Como Clonar no PC de Casa
Abra o terminal PowerShell ou Prompt de Comando na pasta onde quer salvar os projetos e rode:
```bash
git clone https://github.com/ProffisionalPXT/meusprojetos.git
```

### 2️⃣ Como Abrir no VS Code / Antigravity
Abra a pasta clonada `meusprojetos` no seu editor ou no **Antigravity**.

### 3️⃣ Prompt Mágico para Copiar e Colar na IA de Casa
Assim que abrir o chat da IA no seu PC de casa, **copie e cole o texto abaixo**:

```text
Olá! Estou continuando o desenvolvimento que fiz no computador do escritório.
Por favor, leia atentamente o arquivo "HISTORICO_E_CONTEXTO_ROBOS_CASA.md" e o "README.md" que estão na raiz deste projeto.

Nele você tem todo o dossiê completo dos nossos 3 robôs:
1. Robô GW (gw-motorista-bot)
2. Robô de Programação CHEP (chep-motorista-bot)
3. Robô de Ocorrências CHEP (chep_occurrence_bot)

Com todos os prompts que já utilizei, regras de negócio, lógica de cascata, OCR, cadastro atualizado de motoristas e contas configuradas.
Regras de ouro:
- Apresente um plano de especialista antes de alterar qualquer arquivo.
- Aguarde meu comando explícito ("faça", "execute", "prossiga") antes de fazer alterações.
- Mantenha a integridade do código sem modificar arquivos desnecessários.

Pode confirmar que leu os arquivos e me dizer como estamos organizados?
```

---

## 🔑 Quadro de Contas e Credenciais dos Projetos

| Projeto | Sistema / Plataforma | Contas / Usuários | Senha / Configurações |
| :--- | :--- | :--- | :--- |
| **🤖 Robô GW** | GW Transportes (`gw.gwsistemas.com.br`) | `juvenalcorreia@transraplogistica.com.br` | Org: `PURM` / Senha: `Nazinho1975@` |
| **🤖 Robô Ocorrências** | Portal CHEP CMA (`jdadelivers.com`) | • **PURM2**: `gabrielpeixoto@purm2.com.br`<br>• **PURM3**: `gabrielpeixoto@purm3.com.br` | Senha: `12345`<br>Perfis: `BR__LH_PURM2` e `BR__LH_PURM3` |
| **🤖 Robô Programação** | JDA SmartBench + Painel Operacional | Painel `controleechep.onrender.com` / `137.131.190.170` | Vercel / GitHub |
| **🐙 GitHub Geral** | GitHub (`ProffisionalPXT`) | `https://github.com/ProffisionalPXT/meusprojetos.git` | Repositório central dos 3 robôs |
| **🐙 GitHub Ocorrências** | GitHub (`ProffisionalPXT`) | `https://github.com/ProffisionalPXT/ocorrenciaschep.git` | Repositório do Robô de Ocorrências |
| **🐙 GitHub Controle** | GitHub (`bielpxt98`) | `https://github.com/bielpxt98/Controle-Operacional-.git` | Repositório do Painel Web |

---

## 📚 Dossiê Completo
Para ver todo o histórico detalhado, arquivos, arquitetura e mais de 200 prompts reais feitos durante o desenvolvimento, abra o arquivo:
📄 **[HISTORICO_E_CONTEXTO_ROBOS_CASA.md](HISTORICO_E_CONTEXTO_ROBOS_CASA.md)**
