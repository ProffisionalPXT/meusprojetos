# Mapa de campos — GW Webtrans (prints)

## Escopo
Só preencher o que foi **testado**.  
**Não preencher:** apelido, telefone, e-mail, estado civil, escolaridade, PIS/Renach, rastreador nº, CF-e, etc.

**Composição de veículos (CRLV):** 1=TRUCK · 2=CAVALO+CARRETA · 3=+Bi-Trem · 4=+3º Reboque.

### Naturalidade (CNH)
- Se ao lado da **data de nascimento** vier a cidade (ex.: CAROLINA, MA) → usa essa.
- Se **não** vier local de nascimento → usa o **local de emissão** da CNH (ex.: GOIANIA/GO no verso).

## Navegação (após login)

| Passo | Ação | URL / tela |
|-------|------|------------|
| 1 | Menu principal | `/menu` |
| 2 | **Cadastros** (topo) | dropdown |
| 3 | **Operacional** | submenu |
| 4 | **Motoristas** | → Consulta |
| 5 | Consulta de Motoristas | `/ConsultaControlador?codTela=60` |
| 6 | Botão **Novo Motorista** | → formulário |
| 7 | Cadastro de Motoristas | `/cadmotorista?acao=iniciar` |

Outros:
- Veículo: `/cadveiculo?acao=iniciar`
- Proprietário: `/cadproprietario?acao=iniciar`

---

## Motorista — Dados Principais (sempre visível)

| Campo | Exemplo | Obrig.? |
|-------|---------|---------|
| Categoria | Motorista (Transporte) | sim |
| CPF | 00579021196 | * |
| Nome | DEIVID FERNANDES DOS SANTOS | * |
| Apelido | | |
| Telefone Fixo | | |
| Telefone Celular | (ou NAO_INFORMADO) | |

## Aba Dados Pessoais

| Campo | Exemplo |
|-------|---------|
| CEP | 74935000 (+ lupa) |
| Endereço | RUA ABY BARROSO |
| Bairro | CONJUNTO VERA CRUZ |
| Complem. | |
| Cidade | GOIANIA (+ UF/lupa) |
| Sexo | Masculino |
| Tipo de Propriedade | Não informado |
| Reside desde | |
| Nascimento | 02/12/1985 |
| Naturalidade | GOIANIA |
| Nacionalidade | BRASILEIRO |
| Est. civil | Solteiro |
| QTD Dep. | |
| Nome Pai | JOAO CESAR DOS SANTOS |
| Nome Mãe | DALVA FERNANDES DOS SANTOS |
| Grau escolaridade / Qualif. / Email | |

## Aba Documentação

| Campo | Exemplo |
|-------|---------|
| RG | 3777806 |
| Órgão Emissor | SSP/C |
| CNH | 0211943405 |
| Validade | 16/07/2031 |
| Categoria CNH | AE |
| Emissão 1ª CNH | 03/03/2004 |
| PIS/PASEP, Prontuário, Renach, Título... | opcional |

## Aba Dados Operacionais

| Campo | Exemplo |
|-------|---------|
| Tipo | Carreteiro |
| Veículo (placa cavalo) | ONR4E09 |
| Carreta | DWU9135 (2º CRLV) |
| Bi-Trem | 3º CRLV → `#bi_placa` + `#localiza_veiculo3` |
| 3º Reboque | 4º CRLV → `#tri_placa` + `#localiza_veiculo4` |

---

## Veículo (`cadveiculo`)

| Campo | Cavalo (ex.) | Carreta (ex.) |
|-------|--------------|---------------|
| Categoria | Veículo Terrestre | Veículo Terrestre |
| Placa | ONR4E09 | DWU9135 |
| Renavam | 00529728567 | 01246061217 |
| Modelo / Marca | SCANIA R 440 A6X4 | TRUCK ART SRBG 3E |
| Ano Mod/Fab | 2013 / 2013 | 2020 / 2020 |
| Chassi | 9BS6X... | 9ASF... |
| Proprietário | VALRAF... | CLEBIO... |
| Tipo | **CAVALO** | **CARRETA** |
| Cidade | ARARANGUÁ SC | GOIANIA GO |
| Cor | BRANCA | CINZA |
| Tipo de frota | Carreteiro | Carreteiro |
| Cap. carga / Tara | 27000 | 27000 |

---

## Proprietário (`cadproprietario`)

**Só estes campos:** Nome · CPF ou CNPJ · R.G. (CPF) ou I.E. (CNPJ, `0000000`) · RNTRC (se houver TAC).  
**Não preencher:** cidade, endereço, telefone, Representante Legal, checkbox TAC, etc.

| Campo | Exemplo |
|-------|---------|
| Nome | VALRAF - TRANSPORTES... |
| CPF/CNPJ | CNPJ 30038398000116 |
| I.E. | **00000000** (CNPJ) |
| RG | **0000000** (se CPF) |
| Cidade | ARARANGUÁ SC |
| RNTRC | 059276500 (se tiver) |

---

## Botão final

Em todas as telas de cadastro: **Salvar** (barra inferior).

---

## Aba Dados Operacionais — IDs reais (dump 2026-07-09)

| Tela | Elemento HTML | Função |
|------|---------------|--------|
| Tipo motorista | `select#tipo` / `name=tipo` | Funcionário \| **Agregado** \| **Carreteiro** |
| Placa veículo | `input#vei_placa` (readonly) | mostra placa vinculada |
| **Botão ... veículo** | `input#localiza_veiculo` value=`...` | `launchPopupLocate(...idlista=7...,'Veiculo')` |
| Limpar veículo | img borracha | zera idveiculo / vei_placa |
| Placa carreta | `input#car_placa` | |
| **Botão ... carreta** | `input#localiza_veiculo2` | lookup carreta |
| Bi-Trem | `#bi_placa` + `#localiza_veiculo3` | |
| 3º Reboque | `#tri_placa` + `#localiza_veiculo4` | |

## Fluxo 3 pontinhos — Veículo

```
Aba Dados Operacionais
  → clicar #localiza_veiculo  (botão "...")
  → popup Localizar Veículo (idlista=7)
  → filtro Placa | digita | Pesquisar
  → SE achou: clica na linha
  → SE 0 registros: Novo Cadastro → cadveiculo → preenche → Salvar → volta
  → carreta: mesmo fluxo com #localiza_veiculo2
```

## Fluxo 3 pontinhos — Proprietário (print Localizar proprietário)

```
Form Veículo → 3 pontinhos em Proprietário
  → popup "Localizar proprietário"
  → filtro Nome/CPF/CNPJ | Pesquisar
  → SE tem linha: clicar no nome
  → SE não tem: Novo Cadastro
       → cadproprietario?acao=iniciar
       → CPF  → combo CPF + R.G. = 0000000
       → CNPJ → combo CNPJ + I.E. = 0000000
       → Salvar → fechar → voltar ao veículo
```

## Cadastro de Veículo — preenchimento COMPLETO (print referência)

Names reais (`cadveiculo?acao=iniciar`):

| Tela | name HTML | Exemplo print |
|------|-----------|---------------|
| Categoria | `categoria` | Veículo Terrestre |
| *Placa | `pl` | ACY0F00 / HNW6501 |
| Frota Nº | `numeroFrota` | (vazio ok) |
| Renavam | `ren` | 00642383600 |
| Modelo | `mod` | M BENZ LS 1935 |
| Ano Mod / Fab | `anomodelo` / `ano` | 1995 / 1995 |
| Chassi | `chs` | 9M388054… |
| *Marca | `marca` + `#localiza_marca` | **1º** — texto MARCA/MODELO/VERSÃO do CRLV |
| Modelo | `mod` | **2º** — o **mesmo** texto |
| Marca (abaixo cestos) | `marca_rastreador` + `#localiza_marca2` | **3º** — o **mesmo** texto de novo |
| Proprietário | `nome_prop` + `#localiza_proprietario` | SERGIO… |
| *Tipo | `tip` | CAVALO / CARRETA / TRUCK |
| *Cidade | `cidade_proprietario` | **Vem sozinha ao escolher o Proprietário** (não precisa lookup separado) |
| Cor | `cor` | CINZA / PRATA / BRANCA |
| Tipo de frota | `tipofrota` | Carreteiro / Agregada |
| Cap. carga | `capacidadeCarga` | 27000 (cavalo/carreta) ou 12000 (truck) |
| Tara | `taraVeiculo` | igual cap |
| Pallets/Cestos/Cubagem | `qtdPallets` `qtdCestos` `cubagemVeiculo` | 0 |
| Baú A/L/C | `altura_carroceria`… | 0 |

### Marca / Modelo / Versão (regra do usuário)

No documento (CRLV) vem algo como `M BENZ LS 1935` ou `VW GOL 1.0`.

No GW esse texto vai em **3 campos**, nesta ordem:
1. Clica `...` em ***Marca*** (topo) → pesquisa / Novo Cadastro (`cadmarca` = Descrição)
2. Campo **Modelo** (`mod`)
3. Campo **Marca** embaixo de Qtd. Cestos (`marca_rastreador`)

Marca nova: `cadmarca` → só `*Descrição` → Salvar.

### DRY-RUN (teste sem registrar)

No teste **não pode Salvar** → não cadastra marca/proprietário/veículo novos.

| Campo | No teste |
|--------|----------|
| Modelo (`mod`) | Preenche texto |
| Marca de baixo (`marca_rastreador`) | Preenche texto |
| *Marca (topo) | Só se **já existir** na base; senão pula |
| Proprietário | Só se **já existir**; senão pula |
| Cidade | Só se **já existir** (ex. PAULISTA/PE) |
| Placa, renavam, chassi, tipo, cor, cap/tara | Preenche normalmente no form aberto |

Modo real (`DRY_RUN=0`): aí sim Novo Cadastro + Salvar em marca/prop/veículo.

## Fluxo 3 pontinhos — Marca (print Localizar marca)

```
Form Veículo → 3 pontinhos em *Marca
  → popup /localiza?acao=consultar...  "Localizar marca"
  → filtro: Descrição | digita marca | Pesquisar
  → SE tem linha: clicar na descrição (ex: DAF XF105 FT 510A)
  → SE não tem: Novo Cadastro
       → cadastra a marca
       → Salvar → fechar → volta ao veículo com a marca vinculada
```

No form de veículo, os campos com **...** que usam esse padrão:
- Proprietário
- *Marca
- *Cidade (e às vezes Alienado a)
- Tipo (dropdown, sem popup)
