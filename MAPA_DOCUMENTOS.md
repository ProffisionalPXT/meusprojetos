# Documentos que chegam → campos do GW

Geralmente chegam **4 tipos** de foto/PDF:

| # | Documento | Arquivo tipico | O que extrai |
|---|-----------|----------------|--------------|
| 1 | **TAC (ANTT)** | `*TAC*`, `*ANTT*`, `*RNTRC*` | Nome, CPF, RNTRC (usa nos 2 veículos se só tiver 1 TAC) |
| 2 | **CNH** | `*cnh*`, `*habilit*` | Motorista: CPF, nome, nascimento, pais, RG/orgão, CNH, validade, categoria, 1ª hab. |
| 3 | **CRLV** | `*crlv*`, `*placa*`, `DWU*`, renavam | Veículo: placa, renavam, chassi, marca/modelo, ano, cor, tipo (cavalo/carreta/truck), proprietário |
| 4 | **Comprovante** | conta de luz, água, etc. | Endereço: CEP, logradouro, bairro, cidade, UF |

## Regras de negócio

1. **1 TAC** → o mesmo RNTRC/dados do transportador valem para cavalo e carreta (quando houver 2 veículos).
2. **Tipo / composição por quantidade de CRLV:**
   - 1 CRLV → **TRUCK** (só campo Veículo)
   - 2 CRLV → **CAVALO** + **CARRETA** (texto só desempatar qual é o cavalo)
   - 3 CRLV → **CAVALO** + **CARRETA** + **Bi-Trem** (2ª carreta no `#bi_placa`)
   - 4 CRLV → + **3º Reboque** (`#tri_placa`)
   - Bi-Trem e 3º Reboque cadastram com tipo **CARRETA** (cap/tara 27000)
3. **Cap. carga e Tara — SEMPRE fixos** (não usar outro valor):

   | Tipo    | Cap. carga | Tara   |
   |---------|------------|--------|
   | CAVALO  | 27000      | 27000  |
   | CARRETA | 27000      | 27000  |
   | TRUCK   | 12000      | 12000  |

4. **Tipo de frota:** **Agregada** ou **Carreteiro** (os dois são válidos no GW).
5. **Cidade do veículo e do proprietário:** SEMPRE a cidade que está no documento (CRLV do proprietário), nunca inventar.
6. **Proprietário** vem do CRLV; se não existir → 3 pontinhos → Novo Cadastro (CPF RG=0000000 / CNPJ IE=0000000).
7. **Comprovante** pode estar em nome de terceiro — o endereço ainda serve.
8. **Sem comprovante de residência:** SEMPRE usa a **cidade de nascimento** (naturalidade da CNH).
   Ex.: nasceu em Arapiraca/AL → CEP/endereço de Arapiraca-AL (não usa cidade do CRLV/prop).
   Se a cidade não estiver na tabela → ViaCEP (Centro) ou capital da UF de nascimento.
   Último recurso: Recife/PE. Lista em `utils/endereco_fallback.py`.

## Exemplo real (Deivid)

### TAC
- Nome: DEIVID FERNANDES DOS SANTOS  
- CPF: 005.790.211-90  
- RNTRC: 059276500  
- Categoria: TAC  

### CNH → Motorista
- Nome, CPF, nasc. 02/12/1985  
- Pai / Mãe  
- Categoria AE, validade, nº registro  

### CRLV (ex. DWU9135) → Carreta
- Placa DWU9135  
- Renavam, chassi, marca/modelo, ano 2020  
- Cor CINZA  
- Tipo: semi-reboque → **CARRETA** no GW  
- Proprietário: CLEIDIO BRITO RIBEIRO / CPF no doc  

### Conta de energia → Endereço
- Logradouro, bairro, cidade, CEP (quando legível)  
- Nome no comprovante pode ser outro (ex. THAYS...)  

## Botão 3 pontinhos (azul)

Em **todo** campo com `...` azul:

```
clicar 3 pontinhos
  → abre tela de pesquisa
  → digitar termo (placa / CPF / nome / cidade)
  → pesquisar
  → se ACHOU: selecionar linha
  → se NÃO ACHOU: Novo Cadastro → preencher → Salvar → volta com o vínculo
```

Campos típicos com 3 pontinhos:
- Cidade  
- Veículo / Carreta (Dados Operacionais)  
- Proprietário (no cadastro de veículo)  
- Marca (às vezes)  
- Naturalidade  
