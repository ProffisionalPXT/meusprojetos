# Diretrizes do Projeto GW-Motorista-Bot

## Regra de Ouro: Modo Ultrarrápido de Leitura ("ler documentos")

Quando o usuário disser **"ler documentos"**, **"leia os documentos"**, ou a conversa tiver o nome de **"ler documentos"**:

1. **NÃO faça varredura no projeto**:
   - NÃO pesquise o código-fonte, não rode grep no projeto inteiro, não analise scripts `.py` nem explore pastas desnecessárias.
   
2. **Acesse diretamente a pasta de entrada**:
   - Olhe **exclusivamente** os arquivos dentro de `input/motorista/` (especialmente `.pdf`, `.jpg`, `.png`).
   - Ignore arquivos `.bat`, `.txt` de instrução ou atalhos.

3. **Extração direta dos campos**:
   - **Motorista (CNH):**
     - Nome completo do motorista (topo da CNH).
     - CPF (11 dígitos).
     - Data de nascimento, sexo (inferir), RG e órgão emissor.
     - CNH: Nº de Registro (11 dígitos em vermelho).
     - CNH Espelho: Nº do Espelho/Formulário (10 dígitos impresso na vertical esquerda).
     - Categoria CNH, Validade, Data de Emissão, Local de Emissão, 1ª Habilitação.
     - Filiação: Nome da Mãe. Se houver pai legível, coloque o Nome do Pai; se só houver mãe, deixe o pai vazio `""`!
     - Naturalidade / UF de nascimento.
     - **Endereço de Residência (Regra de Fallback):**
       - Se HOUVER comprovante de residência: use o endereço do comprovante.
       - Se NÃO HOUVER comprovante de residência: use OBRIGATORIAMENTE a cidade e UF de nascimento (naturalidade da CNH), logradouro "RUA DO COMERCIO", bairro "CENTRO" e o CEP geral dessa cidade.
   - **Veículo Cavalo e Carreta (CRLVs):**
     - Se houver 2 CRLVs: 1º = Cavalo (caminhão trator) e 2º = Carreta (semi-reboque). `bitrem` DEVE ser `null`.
     - Extrair: Placa, Renavam, Chassi, Marca/Modelo/Versão, Ano Fab/Mod, Cor, Cidade/UF, Proprietário (Nome e CPF/CNPJ).
     - Tara e Capacidade padrão: `"27000"` / `"27000"`, tipo de frota: `"Carreteiro"`.
     - **ATENÇÃO AO PROPRIETÁRIO:** O proprietário do Veículo, Carreta e a chave raiz `"proprietario"` DEVE ser SEMPRE o que consta no **CRLV**. A ANTT serve exclusivamente para preencher o número do **RNTRC** (`rntrc_tac`) e nunca para substituir o proprietário legal do CRLV!
   - **ANTT / TAC (se houver):**
     - Extrair apenas o RNTRC (número de 8 ou 9 dígitos) para o campo `rntrc_tac`. Não usar a Razão Social da ANTT para substituir o proprietário do CRLV.

4. **Gravação Automática**:
   - Salve imediatamente os dados extraídos no arquivo:
     `C:\Users\TRANSRAP05\Desktop\gw-motorista-bot\input\motorista\dados_manuais.json`
   - O formato deve seguir a estrutura padrão com as chaves: `"caso_nome"`, `"rntrc_tac"`, `"motorista"`, `"veiculo"`, `"carreta"`, `"bitrem": null`, `"proprietario"`.

5. **Resposta ao Usuário**:
   - Apresente um resumo claro e direto com uma tabela dos dados encontrados.
   - Informe ao usuário que o arquivo foi gravado e que basta dar dois cliques em `INICIAR_ROBO.bat` para iniciar o cadastro no GW WebTrans.
   - Conclua a resposta em poucos segundos!
