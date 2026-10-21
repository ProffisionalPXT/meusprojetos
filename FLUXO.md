# Fluxo Completo — Bot de Cadastro de Motorista (GW Webtrans)

## Fase 1 — Login e navegação inicial
1. Abrir `https://webtrans.saas.gwsistemas.com.br/login`
2. Preencher E-mail e Senha
3. Clicar em **Login**
4. Selecionar organização **PURM**
5. Aguardar menu principal

## Fase 2 — Ir até Cadastro de Motorista (confirmado nos prints)
1. Menu principal `/menu`
2. **Cadastros** (barra superior)
3. **Operacional** → **Motoristas**
4. Tela **Consulta de Motoristas** (`ConsultaControlador?codTela=60`)
5. Botão **Novo Motorista**
6. Formulário `/cadmotorista?acao=iniciar`

## Fase 3 — Dados Pessoais
- CPF, Nome, Data de Nascimento, Sexo
- CEP (+ lupa) / Endereço, Bairro, Cidade, UF
- Telefone celular (se houver)
- Nome do Pai, Nome da Mãe

## Fase 4 — Documentação
- RG, Órgão Emissor
- CNH, Validade, Categoria
- Data da 1ª Habilitação (se houver)

## Fase 5 — Veículo (se necessário)
1. Pesquisar pela **Placa**
2. Se não achar → **Novo Cadastro** (nova página)
3. Preencher, salvar e voltar

## Fase 6 — Proprietário (se necessário)
1. Pesquisar nome/CPF/CNPJ
2. Se não achar → **Novo Cadastro**
3. CPF → RG = `0000000` | CNPJ → I.E. = `0000000`
4. Salvar e voltar

## Fase 7 — Finalização
1. Campos obrigatórios restantes
2. **Salvar**
3. Confirmar sucesso
4. Fechar ou voltar ao menu

## Fotos / documentos de entrada
Coloque arquivos em `input/` (ver `input/COMO_USAR.txt`).
O bot lista as fotos, o **OCR local** extrai dados, **você confirma** no terminal e a automação preenche o GW.

### Fluxo de cadastro (2 fases — não perde progresso)

```
1. OCR + você confirma dados no terminal
2. FASE A: Dados Pessoais + Documentação → SALVAR
3. FASE B: Consulta de Motoristas → filtra CPF → EDITAR
4. FASE B: Aba Operacional → pesquisa/cadastra placas → SALVAR
```

Se a fase de veículo falhar, o motorista **já está salvo** — basta Editar de novo.

### OCR, confirmação e 3 pontinhos

No `.env`:

| Variável | Padrão | Significado |
|----------|--------|-------------|
| `OCR_ENGINE` | `auto` | `local` / `gemini` / `auto` / `cache` — auto = Tesseract + Gemini nos vazios |
| `GEMINI_SE_VAZIO` | `1` | se local deixar campo vazio, Gemini completa (só esses arquivos) |
| `CONFIRMAR_DADOS` | `1` | revisar **todos** os campos no terminal antes do GW |
| `BROWSER_MODE` | `headless` | sem janela na tela |
| `PRINTS` | `0` | sem screenshots |
| `DRY_RUN` | `1` | não grava Salvar / Novo Cadastro |

**Regra de ouro nos 3 pontinhos:** sempre **PESQUISAR** (placa, marca, prop CPF/CNPJ).  
Só **Novo Cadastro** se a pesquisa não achar.  
Proprietário CNPJ muitas vezes já existe (outro veículo).  
CPF/placa: se o GW disser que já existe, o bot avisa (várias pessoas cadastram).

```bash
python testar_ocr_local.py   # só OCR + confirmação
python main.py               # fluxo completo
```

Confirmação: `ENTER` segue · `n` cancela · `e 3` / `e cpf=...` edita.
