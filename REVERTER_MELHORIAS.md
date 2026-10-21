# Como reverter melhorias (sem apagar código)

Se o robô piorar depois de uma atualização, desligue só a flag no `.env` e rode de novo.
Não precisa reverter git.

## Lookup / Salvar (problema: pesquisa em loop sem gravar)

| Flag | Padrão | Se piorar |
|------|--------|-----------|
| `SALVAR_DETECTAR_FALHA` | `1` | `0` = clica Salvar e assume OK (modo antigo) |
| `RECRIAR_SE_ZERO_RESULTADOS` | `1` | `0` = não tenta Novo Cadastro de novo |
| `LOOKUP_MAX_TENTATIVAS_PESQUISA` | `2` | `1` = pesquisa menos vezes após cadastro |

## Gemini / nomes

| Flag | Padrão | Se piorar |
|------|--------|-----------|
| `GEMINI_SE_VAZIO` | `1` | `0` = nunca chama Gemini |
| `GEMINI_VALIDAR_NOMES` | `1` | `0` = não pede Gemini por nome lixo; não descarta pós-Gemini |

## Outros úteis

| Flag | Efeito |
|------|--------|
| `DRY_RUN=1` | Não grava no GW (teste) |
| `OCR_ENGINE=local` | Só Tesseract (sem Gemini no fluxo) |
| `CONFIRMAR_DADOS=1` | Você confere nomes antes de preencher |
| `INTERVENCAO_MANUAL=1` | Se o robô falhar, **para** e deixa você clicar no browser (ENTER continua · `s` pula). Padrão: ligado com `BROWSER_MODE=visible`. `0` desliga. |
| `TENTATIVAS_AUTO=2` | Quantas vezes o robô tenta **sozinho** antes da 3ª (você faz). Depois do ENTER ele **reconhece** nome na lista / campo preenchido e segue. |

## O que as melhorias resolvem

1. **Salvar** — detecta form ainda aberto / campo obrigatório e **não** fica pesquisando 0 de 0 em loop.
2. **Gemini** — só completa vazio ou nome absurdo; se ainda for lixo, **deixa vazio** (melhor que inventar AXR).
3. **PT/EN** — botões Salvar/Save, Pesquisar/Search, Novo Cadastro/New se o browser abrir em inglês.
