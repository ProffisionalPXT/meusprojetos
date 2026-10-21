"""
Rótulos do GW em PT e EN.

Se o navegador/sistema abrir o Webtrans em inglês, os mesmos fluxos
(Pesquisar, Salvar, Novo Cadastro) continuam encontrando os botões.
Preferir estes seletores em vez de só texto em português.
"""
from __future__ import annotations

# Botão Salvar / Save / Gravar
SELETORES_SALVAR = (
    'button:has-text("Salvar")',
    'button:has-text("Save")',
    'button:has-text("Gravar")',
    'a:has-text("Salvar")',
    'a:has-text("Save")',
    'input[type="submit"][value*="Salvar"]',
    'input[type="submit"][value*="Save"]',
    'input[type="button"][value*="Salvar"]',
    'input[type="button"][value*="Save"]',
    'input[value="Salvar"]',
    'input[value="Save"]',
    'text=Salvar',
    'text=Save',
)

# Botão Pesquisar / Search
SELETORES_PESQUISAR = (
    'button:has-text("Pesquisar")',
    'button:has-text("Search")',
    'button:has-text("Buscar")',
    'input[type="button"][value="Pesquisar"]',
    'input[type="button"][value="Search"]',
    'input[type="submit"][value="Pesquisar"]',
    'input[type="submit"][value="Search"]',
    'input[value*="Pesquis"]',
    'input[value*="Search"]',
    'a:has-text("Pesquisar")',
    'a:has-text("Search")',
)

# Novo Cadastro / New (popup Localizar - botão azul à direita de Pesquisar)
SELETORES_NOVO_CADASTRO = (
    'input[type="button"][value="Novo Cadastro"]',
    'input[type="submit"][value="Novo Cadastro"]',
    'input[value="Novo Cadastro"]',
    'input[value*="Novo Cadastro"]',
    'input[value*="Novo cadastro"]',
    'input[value*="NOVO CADASTRO"]',
    'input[value*="New Registration"]',
    'input[value*="New Record"]',
    'button:has-text("Novo Cadastro")',
    'button:has-text("Novo cadastro")',
    'button:has-text("New Registration")',
    'button:has-text("New Record")',
    'a:has-text("Novo Cadastro")',
    'a:has-text("New Registration")',
    'input[type="button"][value*="Novo"]',
    'button:has-text("Novo")',
    'text=Novo Cadastro',
    'text=New Registration',
)

# Diálogo OK
SELETORES_OK = (
    'button:has-text("OK")',
    'button:has-text("Ok")',
    'button:has-text("Yes")',
    'button:has-text("Sim")',
    'input[value="OK"]',
    'input[value="Ok"]',
    '.ui-dialog-buttonset button',
)

# Textos de sucesso (body lower)
TEXTOS_SUCESSO = (
    "salvo com sucesso",
    "gravado com sucesso",
    "cadastrado com sucesso",
    "operação realizada com sucesso",
    "operação realizada",
    "registro incluído",
    "registro incluido",
    "saved successfully",
    "successfully saved",
    "record saved",
    "operation completed",
    "successfully completed",
)

# Textos de falha de validação (body lower)
TEXTOS_FALHA_SALVAR = (
    "campo obrigat",
    "obrigatório",
    "obrigatorio",
    "preencha o",
    "preencha a",
    "não foi possível",
    "nao foi possivel",
    "erro ao salvar",
    "erro ao gravar",
    "falha ao",
    "inválido",
    "invalido",
    "cidade é obrigat",
    "cidade e obrigat",
    "required field",
    "is required",
    "please fill",
    "mandatory",
    "could not save",
    "unable to save",
    "error saving",
    "invalid",
)

# Títulos de tela de cadastro ainda aberta
TEXTOS_FORM_ABERTO = (
    "cadastro de propriet",
    "cadastro de veículo",
    "cadastro de veiculo",
    "cadastro de marca",
    "voltar para consulta",
    "owner registration",
    "vehicle registration",
    "brand registration",
    "back to search",
    "back to query",
)
