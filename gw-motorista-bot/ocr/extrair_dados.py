"""
Extração de dados das fotos do motorista/veículo/proprietário.

OCR_ENGINE no .env:
  local  - PyMuPDF + Tesseract; se faltar campo, Gemini completa (se tiver chave)
  gemini - só Google Gemini Vision
  auto   - igual ao local com complemento Gemini (recomendado)
  cache  - só lê cache_gemini/ (sem API e sem OCR)

GEMINI_SE_VAZIO=1 (padrão): após o local, Gemini preenche só o que ficou vazio.
GEMINI_SE_VAZIO=0: nunca chama Gemini no modo local/auto.

Depois da extração, use ocr.confirmar.confirmar_dados_caso() antes de preencher.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from gw_automation.regras_veiculo import (
    FROTA_CARRETEIRO,
    TIPO_CAVALO,
    TIPO_CARRETA,
    TIPO_TRUCK,
    aplicar_cap_tara,
    classificar_por_texto,
    normalizar_tipo_frota,
    ordenar_composicao,
)
from ocr.gemini_extrator import (
    extrair_varios as extrair_varios_gemini,
    gemini_disponivel,
    limpar_placa,
    so_digitos,
)
from ocr.tipos_documento import TipoDocumento, agrupar_por_tipo
from utils.endereco_fallback import aplicar_fallback_residencia
from utils.receber_fotos import CasoCadastro


def motor_ocr() -> str:
    """local | gemini | auto | cache"""
    v = (os.getenv("OCR_ENGINE", "auto") or "auto").strip().lower()
    if v in ("local", "gemini", "auto", "cache"):
        return v
    return "auto"


def gemini_se_vazio_ativo() -> bool:
    """Se True, local/auto pedem Gemini só para campos que ficaram vazios."""
    v = (os.getenv("GEMINI_SE_VAZIO", "1") or "1").strip().lower()
    return v not in ("0", "false", "nao", "não", "no", "off")


def gemini_validar_nomes_ativo() -> bool:
    """
    Se True: nomes lixo (AXR, CPEY...) também pedem Gemini;
    após Gemini, descarta nomes que ainda parecem inventados.
    Reverter: GEMINI_VALIDAR_NOMES=0
    """
    try:
        from utils.flags import gemini_validar_nomes

        return gemini_validar_nomes()
    except Exception:
        v = (os.getenv("GEMINI_VALIDAR_NOMES", "1") or "1").strip().lower()
        return v not in ("0", "false", "nao", "não", "no", "off")


from ocr.models import DadosMotorista, DadosVeiculo, DadosProprietario, DadosCaso
def extrair_dados_do_caso(caso: CasoCadastro) -> DadosCaso:
    """
    1) Classifica arquivos (TAC/CNH/CRLV/comprovante)
    2) Lê documentos (local / gemini / auto - ver OCR_ENGINE)
    3) Aplica regras CAVALO/CARRETA/TRUCK + cap/tara + cidade do prop
    """
    dados = DadosCaso(
        caso_nome=caso.nome,
        arquivos=[str(a) for a in caso.arquivos],
    )
    dados.motorista.fotos = [str(a) for a in caso.arquivos]

    grupos = agrupar_por_tipo(caso.arquivos)
    tacs = grupos[TipoDocumento.TAC]
    cnhs = grupos[TipoDocumento.CNH]
    crlvs = grupos[TipoDocumento.CRLV]
    comps = grupos[TipoDocumento.COMPROVANTE]

    engine = motor_ocr()
    dados.fonte_ocr = engine
    print(f"[OCR] Caso '{caso.nome}': {len(caso.arquivos)} arquivo(s) | engine={engine}")
    n_ign = len(grupos.get(TipoDocumento.IGNORAR, []))
    print(
        f"      TAC={len(tacs)} CNH={len(cnhs)} CRLV={len(crlvs)} "
        f"COMPROVANTE={len(comps)} OUTRO={len(grupos[TipoDocumento.OUTRO])}"
        + (f" IGNORAR={n_ign}" if n_ign else "")
    )

    extracoes = _rodar_extracao(caso.arquivos, engine)
    dados.extracoes_gemini = extracoes  # mantém nome do campo (legado)

    crlvs_efetivos = _lista_arquivos_crlv(
        crlvs,
        extracoes.get("crlv", []),
        tacs=extracoes.get("tac", []),
        cnhs=extracoes.get("cnh", []),
        comprovantes=extracoes.get("comprovante", []),
    )
    print(
        f"[OCR] Após leitura: "
        f"cnh={len(extracoes.get('cnh', []))} "
        f"crlv={len(extracoes.get('crlv', []))} "
        f"tac={len(extracoes.get('tac', []))} "
        f"comp={len(extracoes.get('comprovante', []))} "
        f"| veículos a montar (antes deduplicação)={len(crlvs_efetivos)}"
    )

    from ocr.parsers_locais import limpar_placa
    placas_vistas = set()
    crlvs_efetivos_dedup = []
    mapa_ex = {Path(ex.get("_arquivo", "")).name: ex for ex in extracoes.get("crlv", [])}
    
    for arq in crlvs_efetivos:
        ex = mapa_ex.get(arq.name, {})
        placa = limpar_placa(ex.get("placa") or "")
        if not placa:
            try:
                from ocr.tipos_documento import _placa_no_nome
                placa = _placa_no_nome(arq.stem) or ""
                if placa: placa = limpar_placa(placa)
            except Exception:
                pass
                
        if placa:
            if placa in placas_vistas:
                print(f"[OCR] Ignorando arquivo CRLV repetido ({arq.name}) com placa já vista: {placa}")
                continue
            placas_vistas.add(placa)
            
        crlvs_efetivos_dedup.append(arq)

    crlvs_efetivos = crlvs_efetivos_dedup
    # --- Monta estruturas (1=TRUCK, 2=CAVALO+CARRETA, 3=+Bi-Trem, 4=+3º Reboque) ---
    n_crlv = len(crlvs_efetivos)
    if n_crlv == 1:
        dados.veiculo = DadosVeiculo(fotos=[str(crlvs_efetivos[0])], tipo=TIPO_TRUCK)
        dados.veiculo.aplicar_regras_tipo()
        print("[OCR] Composição: 1 CRLV -> TRUCK (Veículo)")
    elif n_crlv >= 2:
        textos = [a.stem + " " + a.name for a in crlvs_efetivos]
        for i, arq in enumerate(crlvs_efetivos):
            for ex in extracoes.get("crlv", []):
                if Path(ex.get("_arquivo", "")).name == arq.name:
                    textos[i] += " " + " ".join(
                        str(ex.get(k, ""))
                        for k in (
                            "tipo_veiculo_doc",
                            "especie",
                            "marca",
                            "modelo",
                        )
                    )
                    if ex.get("eh_semi_reboque"):
                        textos[i] += " semi-reboque"
                    if ex.get("eh_caminhao_trator"):
                        textos[i] += " caminhao trator"
        pares = list(zip(crlvs_efetivos, textos))
        arq_cavalo, arq_carreta, arq_bitrem, arq_tri = ordenar_composicao(pares)
        if arq_cavalo is None:
            arq_cavalo = crlvs_efetivos[0]
            arq_carreta = crlvs_efetivos[1] if n_crlv > 1 else None
            arq_bitrem = crlvs_efetivos[2] if n_crlv > 2 else None
            arq_tri = crlvs_efetivos[3] if n_crlv > 3 else None
        dados.veiculo = DadosVeiculo(fotos=[str(arq_cavalo)], tipo=TIPO_CAVALO)
        dados.veiculo.aplicar_regras_tipo()
        if arq_carreta is not None:
            dados.carreta = DadosVeiculo(fotos=[str(arq_carreta)], tipo=TIPO_CARRETA)
            dados.carreta.aplicar_regras_tipo()
        if arq_bitrem is not None:
            dados.bitrem = DadosVeiculo(fotos=[str(arq_bitrem)], tipo=TIPO_CARRETA)
            dados.bitrem.aplicar_regras_tipo()
        if arq_tri is not None:
            dados.tri_reboque = DadosVeiculo(fotos=[str(arq_tri)], tipo=TIPO_CARRETA)
            dados.tri_reboque.aplicar_regras_tipo()
        slots = ["CAVALO"]
        if dados.carreta:
            slots.append("CARRETA")
        if dados.bitrem:
            slots.append("Bi-Trem")
        if dados.tri_reboque:
            slots.append("3º Reboque")
        print(f"[OCR] Composição: {n_crlv} CRLV -> {' + '.join(slots)}")
        if n_crlv > 4:
            print(
                f"[OCR] [!] {n_crlv} CRLVs - só os 4 primeiros slots do GW "
                "(Veículo/Carreta/Bi-Trem/3º Reboque) serão usados"
            )
    elif extracoes.get("crlv"):
        # extração tem CRLV mas path sumiu - cria TRUCK genérico
        dados.veiculo = DadosVeiculo(tipo=TIPO_TRUCK)
        dados.veiculo.aplicar_regras_tipo()

    # --- Aplica dados extraídos (local ou gemini) ---
    _aplicar_cnh(dados, extracoes.get("cnh", []))
    # Gemini/cache às vezes marca ANTT/CRLV WhatsApp como "outro"
    tacs_lista = list(extracoes.get("tac", []) or [])
    crlvs_lista = list(extracoes.get("crlv", []) or [])
    outros_restantes = []
    for ex in extracoes.get("outro", []) or []:
        if ex.get("_ignorar") or (ex.get("_tipo") or "") == "ignorar":
            continue
        if _parece_extracao_tac(ex):
            ex = dict(ex)
            tacs_lista.append(ex)
            print(
                f"[OCR] OUTRO->TAC: {Path(ex.get('_arquivo') or '').name} "
                f"rntrc={ex.get('rntrc') or '-'} nome={ex.get('nome') or '-'}"
            )
        elif _parece_extracao_crlv(ex):
            ex = dict(ex)
            if not ex.get("proprietario_nome") and ex.get("nome"):
                ex["proprietario_nome"] = _sanitizar_nome_pessoa(ex.get("nome") or "")
            crlvs_lista.append(ex)
            print(
                f"[OCR] OUTRO->CRLV: {Path(ex.get('_arquivo') or '').name} "
                f"placa={ex.get('placa') or '-'} cidade={ex.get('cidade') or '-'}"
            )
        else:
            outros_restantes.append(ex)
    # TAC antes do CRLV: grava RNTRC; nome bom do cartão ANTT
    _aplicar_tac(dados, tacs_lista)
    _aplicar_comprovante(dados, extracoes.get("comprovante", []))
    _aplicar_crlvs(dados, crlvs_lista, crlvs_efetivos)
    # Reaplica TAC depois do CRLV: preenche RNTRC vazio e troca nome lixo
    # (ex: CRLV-e botou "SERVICOS DE TRANSITO" do marketing da CDT)
    if tacs_lista:
        _aplicar_tac(dados, tacs_lista)
        _corrigir_prop_lixo_com_tac(dados, tacs_lista)
    for ex in outros_restantes:
        # não aplicar lixo de omnilink/rastreador como nome/CPF de prop
        nome_u = (ex.get("nome") or "").upper()
        if any(
            x in nome_u
            for x in (
                "OMNILINK", "FICHA DE CLASSIVA", "RASTREADOR", "ATIVAÇÃO", "ATIVACAO",
            )
        ):
            print(f"[OCR] Ignorando OUTRO irrelevante: {ex.get('nome')!r}")
            continue
        _aplicar_generico(dados, ex)
    # ignora extracoes tipo "ignorar" (ficha omnilink etc.)
    for ex in extracoes.get("ignorar", []) or []:
        print(
            f"[OCR] Arquivo ignorado (não é doc de veículo): "
            f"{Path(ex.get('_arquivo', '')).name}"
        )

    # Cidade do CRLV: prop ↔ veículo (sem cidade o GW não salva veículo/prop)
    _sincronizar_cidades_crlv(dados)

    # Placas no motorista (operacional)
    if dados.veiculo and dados.veiculo.placa:
        dados.motorista.placa_veiculo = dados.veiculo.placa
    if dados.carreta and dados.carreta.placa:
        dados.motorista.placa_carreta = dados.carreta.placa

    # Sem comprovante -> residência do MOTORISTA = naturalidade (não mexe no prop/veículo)
    aplicar_fallback_residencia(dados.motorista)

    # Garante RNTRC do TAC em todos os props (1 TAC serve p/ todos os veículos)
    if dados.rntrc_tac and dados.proprietario:
        if not dados.proprietario.rntrc:
            dados.proprietario.rntrc = dados.rntrc_tac
    if dados.rntrc_tac:
        for v in dados.iter_veiculos():
            if v.proprietario and not v.proprietario.rntrc:
                v.proprietario.rntrc = dados.rntrc_tac

    # Regras finais
    if dados.proprietario:
        dados.proprietario.aplicar_regras_gw()
    for v in dados.iter_veiculos():
        v.aplicar_regras_tipo()

    # GW não aceita bem acentos no lookup (PALMEIRA DOS ?NDIOS -> 0 resultados)
    _sem_acentos_nos_textos(dados)

    # Avisos de baixa confiança (placa H↔B, renavam, chassi...) para o usuário
    try:
        from ocr.ocr_qualidade import coletar_avisos_caso

        dados.avisos_ocr = coletar_avisos_caso(extracoes)
    except Exception:
        dados.avisos_ocr = list(dados.avisos_ocr or [])

    _imprimir_resumo(dados)
    return dados


def _sem_acentos_nos_textos(dados: DadosCaso) -> None:
    """Remove acentos de nomes/cidades/endereços antes de confirmar e preencher."""
    from utils.texto import gw_texto

    def _fix(obj, *attrs: str) -> None:
        for a in attrs:
            v = getattr(obj, a, None)
            if isinstance(v, str) and v.strip():
                setattr(obj, a, gw_texto(v))

    m = dados.motorista
    _fix(
        m,
        "nome", "endereco", "bairro", "complemento", "cidade", "uf",
        "naturalidade", "nacionalidade", "nome_pai", "nome_mae",
        "orgao_emissor", "local_emissao_cnh", "sexo", "tipo_motorista",
    )
    # UF sempre 2 letras
    if m.uf:
        m.uf = gw_texto(m.uf)[:2]

    for v in dados.iter_veiculos():
        _fix(v, "marca_modelo_versao", "marca", "modelo", "cor", "cidade", "uf",
               "proprietario_nome", "tipo", "tipo_frota")
        if v.uf:
            v.uf = gw_texto(v.uf)[:2]
        if v.proprietario:
            _fix(v.proprietario, "nome", "cidade", "uf")
            if v.proprietario.uf:
                v.proprietario.uf = gw_texto(v.proprietario.uf)[:2]

    if dados.proprietario:
        _fix(dados.proprietario, "nome", "cidade", "uf")
        if dados.proprietario.uf:
            dados.proprietario.uf = gw_texto(dados.proprietario.uf)[:2]



def _parece_extracao_crlv(ex: Dict) -> bool:
    """True se o dict (mesmo com _tipo=outro) é claramente um CRLV."""
    if not ex:
        return False
    td = (ex.get("tipo_detectado") or ex.get("_tipo") or "").lower()
    if td == "crlv":
        return True
    if ex.get("placa") and (
        ex.get("renavam")
        or ex.get("chassi")
        or ex.get("marca_modelo_versao")
        or ex.get("proprietario_cpf_cnpj")
        or ex.get("cidade")
    ):
        return True
    return False


def _parece_extracao_tac(ex: Dict) -> bool:
    """True se o dict (mesmo com _tipo=outro) é cartão ANTT/TAC/ETC/RNTRC."""
    if not ex:
        return False
    td = (ex.get("tipo_detectado") or ex.get("_tipo") or ex.get("_tipo_sugerido") or "").lower()
    if td == "tac":
        return True
    if ex.get("rntrc") and (ex.get("cnpj") or ex.get("cpf") or ex.get("nome")):
        return True
    # sem placa/renavam (não é CRLV) mas tem CNPJ + indício de transportador
    if ex.get("rntrc") or (
        (ex.get("cnpj") or ex.get("cpf"))
        and not ex.get("placa")
        and not ex.get("renavam")
        and not ex.get("chassi")
    ):
        # só se não parecer CRLV
        if not _parece_extracao_crlv(ex):
            # nome/arquivo/campos típicos
            blob = " ".join(
                str(ex.get(k) or "")
                for k in ("nome", "categoria", "texto_relevante", "_arquivo")
            ).upper()
            if any(
                x in blob
                for x in (
                    "ANTT", "RNTRC", "TAC", "ETC", "CTC", "TRANSPORT",
                    "OLIVEIRA", "CERTIFICADO",
                )
            ) or ex.get("rntrc"):
                return True
    return False


def _corrigir_prop_lixo_com_tac(dados: DadosCaso, tacs: List[Dict]) -> None:
    """
    Se o CRLV colocou nome de marketing (SERVICOS DE TRANSITO) ou nome abreviado,
    e o TAC correspondente tem o nome completo e correto, prioriza o TAC.
    """
    if not tacs:
        return
    try:
        from ocr.parsers_locais import _nome_prop_parece_lixo
    except Exception:
        _nome_prop_parece_lixo = lambda n: False  # type: ignore

    def _melhor_tac() -> Dict:
        for ex in tacs:
            if so_digitos(ex.get("rntrc") or "") or (ex.get("nome") or "").strip():
                return ex
        return tacs[0]

    props = []
    if dados.proprietario:
        props.append(dados.proprietario)
    for v in dados.iter_veiculos():
        if v.proprietario and v.proprietario not in props:
            props.append(v.proprietario)

    for p in props:
        # Tenta achar o TAC correspondente a este proprietário (pelo CNPJ/CPF ou nome)
        p_cnpj = so_digitos(p.cpf_cnpj)
        ex = None
        if p_cnpj:
            for t in tacs:
                t_cnpj = so_digitos(t.get("cnpj") or t.get("cpf") or "")
                if t_cnpj and t_cnpj == p_cnpj:
                    ex = t
                    break
        if not ex and p.nome:
            p_nome_u = p.nome.upper()
            for t in tacs:
                t_nome = (t.get("nome") or "").upper()
                if t_nome and (t_nome in p_nome_u or p_nome_u in t_nome):
                    ex = t
                    break
        if not ex:
            if not p_cnpj:
                ex = _melhor_tac()

        if ex:
            nome_tac = _sanitizar_nome_pessoa(ex.get("nome") or "")
            rntrc = so_digitos(ex.get("rntrc") or "") or dados.rntrc_tac
            if rntrc:
                p.rntrc = rntrc
                if p == dados.proprietario or not dados.rntrc_tac:
                    dados.rntrc_tac = rntrc
                print(f"[TAC] RNTRC {rntrc} para proprietário {p.nome}")

            if nome_tac and not _nome_prop_parece_lixo(nome_tac):
                lixo_atual = _nome_prop_parece_lixo(p.nome or "")
                if not p.nome or lixo_atual:
                    print(f"[TAC] Nome prop lixo '{p.nome}' -> TAC '{nome_tac}'")
                    p.nome = nome_tac
                elif p.nome != nome_tac:
                    p_cnpj_clean = so_digitos(p.cpf_cnpj)
                    t_cnpj_clean = so_digitos(ex.get("cnpj") or ex.get("cpf") or "")
                    mesmo_doc = p_cnpj_clean and t_cnpj_clean and p_cnpj_clean == t_cnpj_clean
                    if mesmo_doc and len(nome_tac) > len(p.nome or ""):
                        print(f"[TAC] Nome prop '{p.nome}' -> TAC completo '{nome_tac}'")
                        p.nome = nome_tac

    for v in dados.iter_veiculos():
        if v.proprietario and v.proprietario.nome:
            v.proprietario_nome = v.proprietario.nome


def _lista_arquivos_crlv(
    crlvs_por_nome: List[Path],
    extracoes_crlv: List[Dict],
    tacs: List[Dict] = [],
    cnhs: List[Dict] = [],
    comprovantes: List[Dict] = [],
) -> List[Path]:
    """Une CRLV detectados no nome + reclassificados pelo OCR (fotos genéricas)."""
    nao_crlv = set()
    for ex in (tacs or []) + (cnhs or []) + (comprovantes or []):
        arq = ex.get("_arquivo") or ""
        if arq:
            p = Path(arq)
            key = str(p.resolve()) if p.exists() else p.name
            nao_crlv.add(key)

    vistos: set[str] = set()
    out: List[Path] = []
    for p in crlvs_por_nome:
        key = str(Path(p).resolve()) if Path(p).exists() else Path(p).name
        if key in nao_crlv:
            continue
        if key not in vistos:
            vistos.add(key)
            out.append(Path(p))
    for ex in extracoes_crlv or []:
        arq = ex.get("_arquivo") or ""
        if not arq:
            continue
        p = Path(arq)
        key = str(p.resolve()) if p.exists() else p.name
        if key in vistos:
            continue
        # só conta se extraiu placa ou renavam (evita falso positivo)
        if ex.get("placa") or ex.get("renavam") or ex.get("chassi"):
            vistos.add(key)
            out.append(p)
    return out


def _rodar_extracao(
    arquivos: List[Path], engine: str
) -> Dict[str, List[Dict]]:
    """Escolhe motor e devolve extracoes por tipo."""
    if engine == "cache":
        print("[OCR] Modo cache - só lê output/cache_gemini/ (sem API/OCR).")
        return _extrair_so_cache(arquivos)

    if engine == "gemini":
        if not gemini_disponivel():
            print("[OCR] OCR_ENGINE=gemini mas sem chave - caindo para local.")
            from ocr.parsers_locais import extrair_varios_local

            return extrair_varios_local(list(arquivos))
        print("[OCR] Motor GEMINI Vision (todos os arquivos)...")
        return extrair_varios_gemini(list(arquivos))

    # local e auto: Tesseract 1ª passada; Gemini SÓ se faltar algo (sem re-zoom)
    label = "LOCAL" if engine == "local" else "AUTO"
    print(
        f"[OCR] Motor {label} - Leitura Rápida Local primeiro"
        + (
            "; Gemini preenche vazios."
            if gemini_se_vazio_ativo()
            else " (GEMINI_SE_VAZIO=0)."
        )
    )
    from ocr.parsers_locais import extrair_varios_local

    local = extrair_varios_local(list(arquivos))
    # 2ª passada local com zoom: sempre se faltar campo ou houver DÚVIDA
    # (placa H↔B, renavam...). Só pula se local já estiver completo e confiante.
    import os as _os

    rapido = (_os.getenv("OCR_RAPIDO", "1") or "1").strip().lower() not in (
        "0", "false", "nao", "não", "no", "off",
    )
    faltas_pre = _listar_faltas(local)
    if faltas_pre:
        print(
            "[OCR] Há campos vazios/ilegíveis na primeira leitura. "
            "Poupando tempo e repassando a dúvida direto para o Gemini..."
        )
        # Desativado intencionalmente _retry_local_com_zoom para acelerar OCR (1 pass local -> Gemini)
    else:
        print("[OCR] Local completo e sem dúvidas - sem re-zoom.")
    return _gemini_completa_vazios(local, list(arquivos))


def _extrair_so_cache(arquivos: List[Path]) -> Dict[str, List[Dict]]:
    from ocr.gemini_extrator import _ler_cache
    from ocr.tipos_documento import classificar_arquivo

    resultado: Dict[str, List[Dict]] = {t.value: [] for t in TipoDocumento}
    for arq in arquivos:
        arq = Path(arq)
        tipo = classificar_arquivo(arq)
        cached = _ler_cache(arq)
        if cached:
            cached["_tipo"] = tipo.value
            resultado[tipo.value].append(cached)
            print(f"[OCR] CACHE {arq.name}")
        else:
            print(f"[OCR] sem cache: {arq.name}")
            resultado[tipo.value].append(
                {"_arquivo": str(arq), "_tipo": tipo.value, "_erro": "sem cache"}
            )
    return resultado


def _extracao_fraca(extracoes: Dict[str, List[Dict]]) -> bool:
    """True se faltam dados críticos (ex.: CNH sem nome/cpf ou CRLV sem placa)."""
    return bool(_listar_faltas(extracoes))


def _listar_faltas(extracoes: Dict[str, List[Dict]]) -> List[str]:
    """
    Lista 'arquivo:campo1,campo2' com o que o local deixou vazio/ruim.
    Usado para decidir se chama Gemini e o que logar.
    """
    faltas: List[str] = []
    for tipo, lista in (extracoes or {}).items():
        if tipo in ("ignorar",):
            continue
        for ex in lista or []:
            if ex.get("_ignorar") or ex.get("_erro"):
                continue
            arq = Path(ex.get("_arquivo") or "?").name
            miss = _campos_faltando(ex, tipo)
            if miss:
                faltas.append(f"{arq}({tipo}): {', '.join(miss)}")
    # nenhum doc útil
    uteis = 0
    for lista in (extracoes or {}).values():
        for ex in lista or []:
            if ex.get("_erro") or ex.get("_ignorar"):
                continue
            if any(v for k, v in ex.items() if not k.startswith("_") and v):
                uteis += 1
    if uteis == 0 and not faltas:
        faltas.append("(nenhum documento com dados úteis)")
    return faltas


def _campos_faltando(ex: Dict, tipo: str) -> List[str]:
    """Campos importantes vazios, lixo OU duvidosos (baixa confianca OCR)."""
    miss: List[str] = []
    t = (tipo or ex.get("_tipo") or "").lower()

    def vazio(k: str) -> bool:
        v = ex.get(k)
        if v is None or v is False:
            return True
        if isinstance(v, str) and not v.strip():
            return True
        return False

    if t == "cnh":
        miss.append("precisa_gemini_cnh")
        n = str(ex.get("nome") or "").strip()
        if n and len(n) < 9:
            miss.append("nome(curto)")
        for k in (
            "nome", "cpf", "cnh", "categoria_cnh", "validade_cnh",
            "data_nascimento", "sexo", "nome_mae", "rg",
            "data_primeira_habilitacao", "data_emissao_cnh",
        ):
            if vazio(k):
                miss.append(k)
        # nomes lixo OCR -> forca Gemini (desliga com GEMINI_VALIDAR_NOMES=0)
        if gemini_validar_nomes_ativo():
            try:
                from ocr.parsers_locais import _nome_parece_lixo_ocr
            except Exception:
                _nome_parece_lixo_ocr = None  # type: ignore
            if _nome_parece_lixo_ocr:
                for k in ("nome", "nome_pai", "nome_mae"):
                    val = (ex.get(k) or "").strip()
                    if val and _nome_parece_lixo_ocr(val):
                        miss.append(f"{k}(lixo)")
            nome_u = (ex.get("nome") or "").upper()
            if any(
                x in nome_u
                for x in (
                    "DOCUMENTO ASSINADO", "CERTIFICADO DIGITAL", "ASSINADO COM",
                    "MEDIDA PROVISORIA", "SERPRO",
                )
            ):
                miss.append("nome(lixo)")
    elif t == "crlv":
        for k in ("placa", "renavam", "proprietario_nome", "proprietario_cpf_cnpj"):
            if vazio(k):
                miss.append(k)
        if vazio("ano_fab") and vazio("ano_mod"):
            miss.append("ano_fab")
        if vazio("marca") and vazio("marca_modelo_versao") and vazio("modelo"):
            miss.append("marca")
        if vazio("cidade") or _cidade_extracao_lixo(str(ex.get("cidade") or "")):
            miss.append("cidade")
        pn = (ex.get("proprietario_nome") or "").upper().strip()
        if gemini_validar_nomes_ativo():
            if pn[:1] in ("'", '"', "`", "\u00b4"):
                miss.append("proprietario_nome(aspas)")
            if pn and any(
                x in pn
                for x in (
                    "DIESEL", "GASOLINA", "ALUGUEL", "BRANCA DIESEL",
                    "SEM NENHUM CUSTO", "NENHUM CUSTO", "OMNILINK", "FICHA DE CLASSIVA",
                )
            ):
                miss.append("proprietario_nome(lixo)")
            if pn and (
                "/" in pn
                or re.search(
                    r"\b(?:SR|VW|SCANIA|VOLVO|FORD|IVECO|DAF|M\.?\s*BENZ)\s*/",
                    pn,
                )
            ):
                miss.append("proprietario_nome(marca)")
            try:
                from ocr.parsers_locais import _nome_prop_parece_lixo

                if pn and _nome_prop_parece_lixo(pn):
                    if "proprietario_nome(lixo)" not in miss:
                        miss.append("proprietario_nome(lixo)")
            except Exception:
                pass
    elif t == "tac":
        if vazio("rntrc"):
            miss.append("rntrc")
    elif t == "comprovante":
        if vazio("cep") and vazio("endereco"):
            miss.append("endereco/cep")

    # Duvida de qualidade (placa H/B, renavam DV) -> tambem pede Gemini
    for d in ex.get("_duvida") or []:
        tag = f"{d}(duvida)"
        if tag not in miss and d not in miss:
            miss.append(tag)
    if ex.get("_precisa_gemini") and not miss:
        miss.append("qualidade_baixa")
    # chassi vazio no CRLV
    if t == "crlv":
        vch = ex.get("chassi")
        if (vch is None or (isinstance(vch, str) and not str(vch).strip())) and "chassi" not in miss:
            miss.append("chassi")
    elif t == "outro":
        miss.append("precisa_gemini_classificacao")
    return miss


def _arquivos_com_falta(
    local: Dict[str, List[Dict]],
    arquivos: List[Path],
) -> List[tuple]:
    """Lista (Path, tipo, miss[]) dos docs incompletos."""
    por_nome: Dict[str, Path] = {Path(a).name: Path(a) for a in arquivos}
    out: List[tuple] = []
    vistos: Set[str] = set()
    for tipo, lista in (local or {}).items():
        if tipo in ("ignorar",):
            continue
        for ex in lista or []:
            if ex.get("_ignorar"):
                continue
            arq_nome = Path(ex.get("_arquivo") or "").name
            if not arq_nome or arq_nome in vistos:
                continue
            miss = _campos_faltando(ex, tipo)
            if not miss and not ex.get("_erro"):
                continue
            p = por_nome.get(arq_nome) or Path(ex.get("_arquivo") or "")
            if p and p.exists():
                out.append((p, tipo, miss))
                vistos.add(arq_nome)
    return out


def _retry_local_com_zoom(
    local: Dict[str, List[Dict]],
    arquivos: List[Path],
) -> Dict[str, List[Dict]]:
    """
    Antes de gastar cota Gemini: re-OCR local com zoom forçado (4x)
    só nos arquivos que ainda têm campos vazios.
    """
    faltas = _listar_faltas(local)
    if not faltas:
        print("[OCR] Local completo após 1ª passada - sem re-zoom.")
        return local

    incompletos = _arquivos_com_falta(local, arquivos)
    if not incompletos:
        return local

    # só fotos se beneficiam de forcar_zoom (PDF já usa OCR_ZOOM)
    from ocr.local_ocr import IMG_EXT, HEIC_EXT, extrair_texto_arquivo
    from ocr.parsers_locais import parsear_arquivo
    from ocr.tipos_documento import classificar_arquivo_e_conteudo

    print(
        f"[OCR] Zoom forçado (4x) em {len(incompletos)} arquivo(s) "
        f"com campos vazios - ANTES do Gemini:"
    )
    for p, tipo, miss in incompletos:
        print(f"      · {p.name} ({tipo}): {', '.join(miss[:8])}")

    melhorias = 0
    for p, tipo_ant, miss in incompletos:
        ext = p.suffix.lower()
        if ext not in IMG_EXT and ext not in HEIC_EXT:
            continue
        try:
            # 2ª passada leve: zoom 3x (OCR_RAPIDO=1) - Gemini cobre o resto
            z = 3.0 if tipo_ant in ("crlv", "cnh") else 2.5
            texto = extrair_texto_arquivo(p, forcar_zoom=z)
        except Exception as e:
            print(f"[OCR] re-zoom falhou {p.name}: {e}")
            continue
        if not (texto or "").strip():
            continue
        tipo_novo, _ = classificar_arquivo_e_conteudo(p, texto)
        tipo_usar = tipo_novo if tipo_novo.value != "outro" else tipo_ant
        # se o tipo_ant for cnh/crlv etc, mantém para o parser certo
        from ocr.tipos_documento import TipoDocumento as TD

        try:
            tipo_enum = TD(tipo_ant) if tipo_ant in {t.value for t in TD} else tipo_novo
        except Exception:
            tipo_enum = tipo_novo
        if tipo_enum.value in ("outro", "ignorar") and tipo_novo.value not in (
            "outro",
            "ignorar",
        ):
            tipo_enum = tipo_novo

        dados = parsear_arquivo(p, texto, tipo_enum)
        dados["_fonte"] = "local+zoom"
        dados["_tipo"] = dados.get("_tipo") or tipo_enum.value
        # mescla no local: preenche só vazios
        tkey = dados.get("_tipo") or tipo_ant
        if tkey not in local:
            local[tkey] = []
        mesclou = False
        for i, ex in enumerate(local.get(tipo_ant, []) or []):
            if Path(ex.get("_arquivo") or "").name != p.name:
                continue
            n_fill = 0
            for k, v in dados.items():
                if k.startswith("_"):
                    continue
                if v in (None, "", False, []) and not isinstance(v, bool):
                    continue
                cur = ex.get(k)
                # troca nome de mãe se for na verdade o pai (heurística: vazio pai)
                if k == "nome_mae" and cur and not ex.get("nome_pai") and v and v != cur:
                    # se zoom trouxe pai+mãe e local só tinha um nome masculino como mãe
                    if dados.get("nome_pai") and not ex.get("nome_pai"):
                        ex["nome_pai"] = dados.get("nome_pai") or ""
                        if dados.get("nome_mae"):
                            ex["nome_mae"] = dados["nome_mae"]
                            n_fill += 2
                        continue
                if not cur and v:
                    ex[k] = v
                    n_fill += 1
                # troca nome lixo OCR por leitura melhor do zoom/Gemini
                elif (
                    cur
                    and v
                    and str(cur).strip() != str(v).strip()
                    and k in ("nome", "nome_pai", "nome_mae")
                ):
                    try:
                        from ocr.parsers_locais import _nome_parece_lixo_ocr
                        if _nome_parece_lixo_ocr(str(cur)) and not _nome_parece_lixo_ocr(
                            str(v)
                        ):
                            ex[k] = v
                            n_fill += 1
                    except Exception:
                        pass
                # zoom pode corrigir campo duvidoso (ex. placa B vs H)
                elif (
                    cur
                    and v
                    and str(cur).strip() != str(v).strip()
                    and k in (
                        "placa", "renavam", "chassi",
                        "proprietario_nome", "proprietario_cpf_cnpj",
                    )
                ):
                    duv = ex.get("_duvida") or []
                    conf = (ex.get("_confianca") or {}).get(k, 1.0)
                    if k in duv or conf < 0.55:
                        ex[k] = v
                        n_fill += 1
            if n_fill:
                ex["_fonte"] = (ex.get("_fonte") or "local") + "+zoom"
                ex["_zoom_preencheu"] = n_fill
                melhorias += n_fill
                mesclou = True
                # reavalia confiança após zoom
                if tipo_ant == "crlv" or (dados.get("_tipo") == "crlv"):
                    try:
                        from ocr.ocr_qualidade import avaliar_extracao_crlv

                        ex = avaliar_extracao_crlv(ex, texto=texto or "")
                    except Exception:
                        pass
                still = _campos_faltando(ex, tipo_ant)
                print(
                    f"[OCR] [OK] zoom {p.name}: +{n_fill} campo(s)"
                    + (f" | ainda falta: {', '.join(still[:6])}" if still else " | completo")
                )
            local[tipo_ant][i] = ex
            break
        if not mesclou and tkey != tipo_ant:
            # reclassificado (outro->cnh) - adiciona na lista certa
            lista = local.setdefault(tkey, [])
            if not any(Path(x.get("_arquivo") or "").name == p.name for x in lista):
                lista.append(dados)
                melhorias += 1
                print(f"[OCR] [OK] zoom reclassificou {p.name} -> {tkey}")

    if melhorias:
        print(f"[OCR] Re-zoom preencheu {melhorias} campo(s) no total.")
    else:
        print("[OCR] Re-zoom não preencheu campos novos.")
    return local


def _gemini_completa_vazios(
    local: Dict[str, List[Dict]],
    arquivos: List[Path],
) -> Dict[str, List[Dict]]:
    """
    SÓ depois do OCR local + zoom: chama Gemini se:
      - campo crítico vazio, OU
      - campo marcado como DÚVIDA (baixa confiança: placa H↔B, renavam, chassi...)

    Mescla: preenche vazios e PODE sobrescrever só campos duvidosos
    (não mexe no que o local tem com boa confiança).
    """
    if not gemini_se_vazio_ativo():
        return local

    faltas = _listar_faltas(local)
    if not faltas:
        print("[OCR] Local+zoom completo e sem dúvidas - Gemini não necessário.")
        return local

    if not gemini_disponivel():
        print(
            "[OCR] Ainda há vazios/dúvidas após OCR local, mas sem GEMINI_API_KEY - "
            "seguindo com Tesseract. Confira os avisos na confirmação."
        )
        for f in faltas[:8]:
            print(f"      · {f}")
        return local

    incompletos = _arquivos_com_falta(local, arquivos)
    precisamos: List[Path] = []
    tipos_por_nome: Dict[str, str] = {}
    for p, tipo, miss in incompletos:
        precisamos.append(p)
        tipos_por_nome[p.name] = tipo
        motivo = ", ".join(miss) or "erro local"
        tem_duvida = any("duvida" in m or m == "qualidade_baixa" for m in miss)
        if tem_duvida:
            print(
                f"[OCR] Gemini (dúvida no local) -> {p.name}: {motivo}"
            )
        else:
            print(
                f"[OCR] Gemini (campo vazio) -> {p.name}: {motivo}"
            )

    # Se local não trouxe CRLV/CNH nenhum, manda os arquivos reais de novo
    if not precisamos:
        from ocr.tipos_documento import TipoDocumento as TD, classificar_arquivo

        for a in arquivos:
            a = Path(a)
            tip = classificar_arquivo(a)
            if tip.value in ("ignorar",):
                continue
            if tip in (TD.CNH, TD.CRLV, TD.TAC, TD.COMPROVANTE):
                precisamos.append(a)
                tipos_por_nome[a.name] = tip.value
        if precisamos:
            print(
                f"[OCR] Local fraco - Gemini em {len(precisamos)} arquivo(s) de doc."
            )

    if not precisamos:
        print("[OCR] Nada a enviar ao Gemini.")
        return local

    print(
        f"[OCR] Complementando {len(precisamos)} arquivo(s) com Gemini Vision "
        f"(só o que o zoom local não resolveu)..."
    )
    try:
        # passa tipo já classificado pelo local (evita PROMPT_GENERICO em WhatsApp)
        gem = extrair_varios_gemini(precisamos, tipos_por_nome=tipos_por_nome)
    except TypeError:
        # compat se extrair_varios ainda não aceita tipos_por_nome
        gem = extrair_varios_gemini(precisamos)
    except Exception as e:
        print(f"[OCR] [!] Gemini falhou ({e}) - mantendo só local.")
        return local

    # se Gemini devolveu só texto_relevante (prompt genérico), parseia localmente
    gem = _enriquecer_gemini_com_texto_relevante(gem)

    mesclado = _mesclar_extracoes(local, gem)
    if gemini_validar_nomes_ativo():
        mesclado = _descartar_nomes_lixo_apos_gemini(mesclado)
    # log do que entrou
    for tipo in mesclado:
        for ex in mesclado.get(tipo) or []:
            if "+gemini" in (ex.get("_fonte") or ""):
                preenchidos = [
                    k
                    for k, v in ex.items()
                    if not k.startswith("_") and v not in (None, "", False, [])
                ]
                print(
                    f"[OCR] [OK] {Path(ex.get('_arquivo','')).name}: "
                    f"fonte={ex.get('_fonte')} campos={preenchidos[:12]}"
                )
    return mesclado


def _enriquecer_gemini_com_texto_relevante(
    gem: Dict[str, List[Dict]],
) -> Dict[str, List[Dict]]:
    """
    Cache/prompt genérico às vezes deixa campos estruturados vazios e
    joga tudo em texto_relevante. Re-parseia com parsers locais.
    """
    from ocr.parsers_locais import parse_cnh, parse_crlv, parse_tac, parse_comprovante

    for tipo, lista in (gem or {}).items():
        for ex in lista or []:
            tr = (ex.get("texto_relevante") or "").strip()
            if not tr or len(tr) < 40:
                continue
            # se já tem os campos críticos, não mexe
            miss = _campos_faltando(ex, tipo)
            if not miss:
                continue
            if tipo == "cnh" or (ex.get("tipo_detectado") or "").lower() == "cnh":
                parsed = parse_cnh(tr)
            elif tipo == "crlv" or (ex.get("tipo_detectado") or "").lower() == "crlv":
                parsed = parse_crlv(tr)
            elif tipo == "tac":
                parsed = parse_tac(tr)
            elif tipo == "comprovante":
                parsed = parse_comprovante(tr)
            else:
                # tenta pelo tipo_detectado
                td = (ex.get("tipo_detectado") or "").lower()
                if td == "cnh":
                    parsed = parse_cnh(tr)
                elif td == "crlv":
                    parsed = parse_crlv(tr)
                else:
                    continue
            n = 0
            for k, v in parsed.items():
                if k.startswith("_") or not v:
                    continue
                if not ex.get(k):
                    ex[k] = v
                    n += 1
            if n:
                ex["_fonte"] = (ex.get("_fonte") or "gemini") + "+texto_relevante"
                print(
                    f"[OCR] Gemini texto_relevante -> +{n} campo(s) em "
                    f"{Path(ex.get('_arquivo') or '').name}"
                )
    return gem


def _descartar_nomes_lixo_apos_gemini(
    extracoes: Dict[str, List[Dict]],
) -> Dict[str, List[Dict]]:
    """
    Pós-Gemini: se ainda devolveu nome absurdo (AXR, CPEY...), limpa o campo.
    Melhor vazio (confirmação manual) do que gravar lixo no GW.
    """
    try:
        from ocr.parsers_locais import _nome_parece_lixo_ocr, _nome_prop_parece_lixo
    except Exception:
        return extracoes

    for tipo, lista in extracoes.items():
        for ex in lista or []:
            if tipo == "cnh" or (ex.get("_tipo") or "") == "cnh":
                for k in ("nome", "nome_pai", "nome_mae"):
                    val = (ex.get(k) or "").strip()
                    if val and _nome_parece_lixo_ocr(val):
                        # Pula a limpeza de nomes lixo para outputs do Gemini,
                        # pois ele é mais confiável com nomes estranhos/curtos.
                        if "gemini" in (ex.get("_fonte") or "").lower():
                            continue
                        print(
                            f"[OCR] Gemini nome rejeitado ({k}={val!r}) - "
                            f"fica vazio (não inventa)"
                        )
                        ex[k] = ""
            if tipo == "crlv" or (ex.get("_tipo") or "") == "crlv":
                pn = (ex.get("proprietario_nome") or "").strip()
                if pn and _nome_prop_parece_lixo(pn):
                    # Também preserva do Gemini para propriedades do CRLV
                    if "gemini" in (ex.get("_fonte") or "").lower():
                        continue
                    print(
                        f"[OCR] Gemini prop rejeitado ({pn!r}) - fica vazio"
                    )
                    ex["proprietario_nome"] = ""
    return extracoes


def _mesclar_extracoes(
    base: Dict[str, List[Dict]], extra: Dict[str, List[Dict]]
) -> Dict[str, List[Dict]]:
    """
    Preenche vazios do base com extra.
    Sobrescreve se o local marcou o campo como DÚVIDA (baixa confiança)
    ou nome/cidade lixo - assim Gemini corrige JSV6B70->JSV6H70 quando preciso.
    Não sobrescreve campos com boa confiança local.
    """
    try:
        from ocr.ocr_qualidade import mesclar_campo_com_duvida, campo_duvidoso
    except Exception:
        mesclar_campo_com_duvida = None  # type: ignore
        campo_duvidoso = None  # type: ignore

    # campos críticos onde dúvida autoriza overwrite
    criticos_duvida = {
        "placa", "renavam", "chassi", "proprietario_nome", "proprietario_cpf_cnpj",
        "nome", "cpf", "cnh", "categoria_cnh", "validade_cnh", "marca_modelo_versao",
        "marca", "modelo", "cidade", "uf",
        "nome_pai", "nome_mae", "data_emissao_cnh", "data_primeira_habilitacao",
    }

    out: Dict[str, List[Dict]] = {t.value: [] for t in TipoDocumento}
    for tipo in out:
        por_arq: Dict[str, Dict] = {}
        for ex in base.get(tipo, []) or []:
            por_arq[Path(ex.get("_arquivo", "")).name] = dict(ex)
        for ex in extra.get(tipo, []) or []:
            nome = Path(ex.get("_arquivo", "")).name
            if not nome:
                continue
            if nome not in por_arq:
                d = dict(ex)
                d["_fonte"] = (d.get("_fonte") or "gemini")
                por_arq[nome] = d
                continue
            cur = por_arq[nome]
            n_fill = 0
            for k, v in ex.items():
                if k.startswith("_"):
                    continue
                # prop nome lixo no local ou erro de digitação OCR (typo) -> deixa Gemini trocar
                if k == "proprietario_nome" and cur.get(k):
                    pu = str(cur.get(k) or "").upper().strip()
                    vu = str(v or "").upper().strip()
                    typo_prop = False
                    if vu and len(pu) > 5 and len(vu) > 5:
                        import difflib
                        if 0.80 < difflib.SequenceMatcher(None, pu, vu).ratio() < 1.0:
                            typo_prop = True
                            
                    lixo_nome = (
                        pu[:1] in ("'", '"', "`", "´")
                        or any(
                            x in pu
                            for x in (
                                "SEM NENHUM CUSTO", "NENHUM CUSTO", "OMNILINK",
                                "DIESEL", "GASOLINA", "FICHA DE CLASSIVA",
                            )
                        )
                        or (
                            "/" in pu
                            and not any(
                                x in pu for x in ("LTDA", "EIRELI", " S.A", " SA")
                            )
                        )
                    )
                    if (lixo_nome or typo_prop) and v:
                        # não troca lixo local por lixo Gemini
                        try:
                            from ocr.parsers_locais import _nome_prop_parece_lixo
                            if gemini_validar_nomes_ativo() and _nome_prop_parece_lixo(
                                str(v)
                            ):
                                continue
                        except Exception:
                            pass
                        cur[k] = v
                        n_fill += 1
                        continue
                # nome/pai/mãe lixo OCR -> Gemini sobrescreve
                if k in ("nome", "nome_pai", "nome_mae") and cur.get(k) and v:
                    try:
                        from ocr.parsers_locais import _nome_parece_lixo_ocr
                        import difflib
                        local_lixo = _nome_parece_lixo_ocr(str(cur.get(k) or ""))
                        
                        trocou_filiacao = False
                        if k == "nome":
                            local_str = str(cur.get(k) or "").upper()
                            gem_mae = str(v if "mae" in k else ex.get("nome_mae") or "").upper()
                            gem_pai = str(v if "pai" in k else ex.get("nome_pai") or "").upper()
                            for filiacao in (gem_mae, gem_pai):
                                if len(filiacao) > 5 and len(local_str) > 5:
                                    sim = difflib.SequenceMatcher(None, local_str, filiacao).ratio()
                                    if sim > 0.7:
                                        trocou_filiacao = True
                                        break
                                        
                        # NOVO: Se as duas extrações forem extremamente parecidas (ex: CRISTOLINO vs CRISTALINO, O vs 0, S vs 5)
                        # significa que o OCR local errou uma letra. Nesse caso, preferimos a inteligência ortográfica do Gemini.
                        typo_ocr = False
                        if v and len(local_str) > 5 and len(str(v)) > 5:
                            sim_typo = difflib.SequenceMatcher(None, local_str, str(v).upper()).ratio()
                            if 0.80 < sim_typo < 1.0:
                                typo_ocr = True

                        # Se o local foi lixo, muito curto, confundiu motorista com filiação, ou teve um erro de digitação de 1-2 letras, confia no Gemini
                        if local_lixo or len(str(cur.get(k) or "")) < 9 or trocou_filiacao or typo_ocr:
                            cur[k] = v
                            n_fill += 1
                            continue
                    except Exception:
                        pass
                # cidade lixo no local (RARE SOE, NAL DRAT...) -> Gemini sobrescreve
                if k == "cidade" and cur.get(k) and v:
                    if _cidade_extracao_lixo(str(cur.get(k) or "")):
                        cur[k] = v
                        n_fill += 1
                        if ex.get("uf") and not cur.get("uf"):
                            cur["uf"] = ex["uf"]
                        continue
                # marca com lixo OCR (". OO ENA", "RANDOM", etc.) -> Gemini limpa
                if k in ("marca", "modelo", "marca_modelo_versao") and cur.get(k) and v:
                    if _marca_extracao_lixo(str(cur.get(k) or "")) and not _marca_extracao_lixo(
                        str(v)
                    ):
                        cur[k] = v
                        n_fill += 1
                        continue
                # chassi: local inventou VIN 17 e Gemini trouxe numérico de carreta
                if k == "chassi" and cur.get(k) and v:
                    cl = re.sub(r"\W", "", str(cur.get(k) or "")).upper()
                    cg = re.sub(r"\W", "", str(v or "")).upper()
                    if (
                        len(cl) == 17
                        and cg.isdigit()
                        and 11 <= len(cg) <= 14
                        and cl != cg
                    ):
                        # preferir numérico se local está em dúvida
                        duv = cur.get("_duvida") or []
                        if "chassi" in duv or (cur.get("_confianca") or {}).get("chassi", 1) < 0.55:
                            cur[k] = v
                            n_fill += 1
                            continue
                # vazio -> preenche
                if v not in (None, "", False, []) and not cur.get(k):
                    cur[k] = v
                    n_fill += 1
                    continue
                # duvidoso -> Gemini pode corrigir (ex. placa B vs H)
                if (
                    k in criticos_duvida
                    and v not in (None, "", False, [])
                    and cur.get(k)
                    and str(v).strip() != str(cur.get(k) or "").strip()
                ):
                    if mesclar_campo_com_duvida is not None:
                        if mesclar_campo_com_duvida(cur, ex, k):
                            n_fill += 1
                            continue
                    elif campo_duvidoso is not None and campo_duvidoso(cur, k):
                        cur[k] = v
                        n_fill += 1
                        continue
            if n_fill:
                cur["_fonte"] = (cur.get("_fonte") or "local") + "+gemini"
                cur["_gemini_preencheu"] = n_fill
            # reavalia avisos após merge
            if (cur.get("_tipo") or tipo) == "crlv":
                try:
                    from ocr.ocr_qualidade import avaliar_extracao_crlv

                    # sem texto bruto aqui; mantém avisos e limpa dúvidas resolvidas
                    still = []
                    for d in cur.get("_duvida") or []:
                        if not cur.get(d):
                            still.append(d)
                    cur["_duvida"] = still
                    if still:
                        av = list(cur.get("_avisos_ocr") or [])
                        av.append(
                            "após Gemini ainda há dúvida em: "
                            + ", ".join(still)
                            + " - confirme no documento"
                        )
                        cur["_avisos_ocr"] = list(dict.fromkeys(av))
                except Exception:
                    pass
        out[tipo] = list(por_arq.values())
    return out


def _cidade_extracao_lixo(cid: str) -> bool:
    """True se cidade do OCR local deve ser descartada em favor do Gemini."""
    try:
        from ocr.parsers_locais import _cidade_parece_lixo

        return _cidade_parece_lixo(cid)
    except Exception:
        cu = (cid or "").upper().strip()
        if not cu or len(cu) < 4:
            return True
        if re.search(r"\b(RARE|SOE|DUTHAT|AINIVE|NAL|DRAT)\b", cu):
            return True
        return False


def _marca_extracao_lixo(mmv: str) -> bool:
    """
    True se a marca do OCR local tem lixo colado e deve ceder ao Gemini.
    Ex.: "SR RANDON SR FG CG 3E . OO ENA" / "SR RANDOM ..."
    """
    u = (mmv or "").strip().upper()
    if not u:
        return True
    # lixo típico do CRLV-e (campo vizinho / carimbo)
    if re.search(r"\.\s*(OO|O0|0O|00|O+)?\s*ENA\b", u):
        return True
    if re.search(r"\b(?:OO|00)\s*ENA\b", u):
        return True
    # RANDOM é OCR errado de RANDON (fabricante)
    if re.search(r"\bRANDOM\b", u):
        return True
    # muito longo para marca de veículo (OCR grudou outra linha)
    if len(u) > 45:
        return True
    # pontuação estranha no meio/fim
    if re.search(r"\s\.\s+[A-Z]{1,4}\s*$", u):
        return True
    return False


def _sanitizar_nome_pessoa(s: str) -> str:
    """Remove aspas/OCR no início do nome (' JOSE... -> JOSE...)."""
    s = (s or "").strip()
    s = s.lstrip("'\"`´‘’“”‚‛ \t")
    s = s.rstrip("'\"`´‘’“”‚‛ \t")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _sanitizar_cidade(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^(?:LOCAL|CIDADE|MUNIC[IÍ]PIO)\s+", "", s, flags=re.I).strip()
    s = re.sub(r"\s+", " ", s).strip()
    try:
        from ocr.parsers_locais import _corrigir_barra_dos_coqueiros

        s = _corrigir_barra_dos_coqueiros(s)
    except Exception:
        pass
    return s.upper() if s else s


def _aplicar_cnh(dados: DadosCaso, lista: List[Dict]) -> None:
    if not lista:
        return
    ex = lista[0]
    m = dados.motorista
    m.nome = m.nome or _sanitizar_nome_pessoa(ex.get("nome", "") or "")
    m.cpf = m.cpf or so_digitos(ex.get("cpf", ""))
    m.data_nascimento = m.data_nascimento or ex.get("data_nascimento", "")
    m.nome_pai = m.nome_pai or ex.get("nome_pai", "")
    m.nome_mae = m.nome_mae or ex.get("nome_mae", "")
    # aviso de nome ambíguo (OCR foto) - usuário corrige na confirmação
    aviso_n = (ex.get("_aviso_nome") or "").strip()
    if aviso_n:
        dados.avisos_ocr = list(dados.avisos_ocr or [])
        if aviso_n not in dados.avisos_ocr:
            dados.avisos_ocr.append(f"[cnh] {aviso_n}")
    m.rg = m.rg or ex.get("rg", "")
    m.orgao_emissor = m.orgao_emissor or ex.get("orgao_emissor", "")
    m.cnh = m.cnh or so_digitos(ex.get("cnh", ""))
    m.categoria_cnh = m.categoria_cnh or ex.get("categoria_cnh", "")
    m.validade_cnh = m.validade_cnh or ex.get("validade_cnh", "")
    m.data_emissao_cnh = m.data_emissao_cnh or ex.get("data_emissao_cnh", "")
    m.local_emissao_cnh = m.local_emissao_cnh or ex.get("local_emissao_cnh", "")
    m.data_primeira_habilitacao = m.data_primeira_habilitacao or ex.get(
        "data_primeira_habilitacao", ""
    )
    m.sexo = m.sexo or ex.get("sexo", "")
    m.nacionalidade = m.nacionalidade or ex.get("nacionalidade", "") or m.nacionalidade

    # Trava de segurança: Motorista MASCULINO não pode ter nome feminino (mãe), nem nome idêntico à filiação
    nome_u = (m.nome or "").strip().upper()
    mae_u = (m.nome_mae or "").strip().upper()
    pai_u = (m.nome_pai or "").strip().upper()
    sexo_u = (m.sexo or "").strip().upper()
    try:
        from ocr.parsers_locais import _prenome_feminino
        eh_fem = _prenome_feminino(nome_u)
    except Exception:
        eh_fem = any(nome_u.startswith(p) for p in ("ANA ", "MARIA ", "JULIANA ", "FRANCISCA ", "ROSANGELA ", "PATRICIA ", "ADRIANA "))

    if ("MASC" in sexo_u or sexo_u == "MASCULINO") and eh_fem:
        print(f"[CNH] Motorista é MASCULINO mas nome {m.nome!r} é feminino! Movendo para nome_mae e zerando motorista.nome.")
        if not m.nome_mae:
            m.nome_mae = m.nome
        m.nome = ""

    if m.nome and (m.nome.strip().upper() == mae_u or (pai_u and m.nome.strip().upper() == pai_u)):
        print(f"[CNH] Nome do motorista {m.nome!r} é idêntico à filiação! Zerando motorista.nome.")
        m.nome = ""
    # Naturalidade: cidade ao lado do nascimento; se vazia -> local de emissão (ex. GOIANIA/GO)
    nat = (ex.get("naturalidade") or "").strip()
    uf_nat = (ex.get("uf_naturalidade") or "").strip().upper()
    if nat:
        m.naturalidade = m.naturalidade or nat
    if not (m.naturalidade or "").strip():
        loc_em = (ex.get("local_emissao_cnh") or m.local_emissao_cnh or "").strip()
        if loc_em:
            if "/" in loc_em:
                cid, uf = loc_em.split("/", 1)
                m.naturalidade = cid.strip()
                uf_nat = uf.strip().upper() or uf_nat
            else:
                m.naturalidade = loc_em
            print(
                f"[CNH] Naturalidade vazia no nascimento -> local emissão: "
                f"{m.naturalidade}/{uf_nat or '?'}"
            )
    # local emissão no form se vazio
    if not m.local_emissao_cnh and ex.get("local_emissao_cnh"):
        m.local_emissao_cnh = ex["local_emissao_cnh"]


def _aplicar_tac(dados: DadosCaso, lista: List[Dict]) -> None:
    """
    Usa SEMPRE o(s) TAC disponível(is), mesmo que não seja do motorista.

    - 1 TAC  -> RNTRC reutilizado em todos os proprietários/veículos
    - N TACs -> guarda todos; tenta casar por nome com o prop do CRLV
    - Nunca sobrescreve nome/CPF do motorista se a CNH já preencheu
    """
    if not lista:
        return

    dados.tacs = lista
    # RNTRC principal = primeiro TAC com número (sempre usa o que tiver)
    for ex in lista:
        rntrc = so_digitos(ex.get("rntrc", ""))
        if rntrc:
            dados.rntrc_tac = rntrc
            break
    if not dados.rntrc_tac:
        dados.rntrc_tac = so_digitos(lista[0].get("rntrc", ""))

    print(
        f"[TAC] {len(lista)} documento(s) - RNTRC em uso: {dados.rntrc_tac or '(vazio)'} "
        f"(reutiliza mesmo se for de outro proprietário)"
    )

    dados.proprietario = dados.proprietario or DadosProprietario()
    p = dados.proprietario
    p.fotos = list({*(p.fotos or []), *[ex.get("_arquivo", "") for ex in lista if ex.get("_arquivo")]})

    # Casa TAC com proprietário pelo nome, senão usa o primeiro
    ex_match = lista[0]
    nome_prop = (p.nome or "").upper()
    if nome_prop and len(lista) > 1:
        for ex in lista:
            if (ex.get("nome") or "").upper() and (
                (ex.get("nome") or "").upper() in nome_prop
                or nome_prop in (ex.get("nome") or "").upper()
            ):
                ex_match = ex
                break

    rntrc = so_digitos(ex_match.get("rntrc", "")) or dados.rntrc_tac
    if rntrc:
        p.rntrc = rntrc
        dados.rntrc_tac = rntrc

    # Nome do TAC: preenche se vazio OU se o atual for lixo OCR / marketing CDT
    nome_tac = (ex_match.get("nome") or "").strip()
    if nome_tac:
        try:
            from ocr.parsers_locais import _nome_prop_parece_lixo

            lixo_atual = _nome_prop_parece_lixo(p.nome or "")
            lixo_tac = _nome_prop_parece_lixo(nome_tac)
        except Exception:
            lixo_atual, lixo_tac = not bool(p.nome), False
        # SERVICOS DE TRANSITO do CRLV-e também conta como lixo
        nu = (p.nome or "").upper()
        if any(x in nu for x in ("SERVICOS DE TRANSITO", "SERVIÇOS DE TRÂNSITO", "SEM NENHUM CUSTO")):
            lixo_atual = True
        if (not p.nome or lixo_atual) and not lixo_tac:
            p.nome = _sanitizar_nome_pessoa(nome_tac)
            print(f"[TAC] Nome do prop <- TAC: {p.nome}")
    if not p.cpf_cnpj:
        p.cpf_cnpj = so_digitos(ex_match.get("cpf", "") or ex_match.get("cnpj", ""))

    # Motorista: NÃO usa nome/CPF do TAC se houver CNH no lote
    # (TAC/ETC é do proprietário - ex.: L.S.OLIVEIRA ≠ motorista JOAO...)
    tem_cnh = any(
        True
        for a in (dados.arquivos or [])
        if "cnh" in Path(a).name.lower() or "habilit" in Path(a).name.lower()
    )
    # WhatsApp sem "cnh" no nome: se já extraiu RG/validade/registro, é CNH
    if not tem_cnh:
        m = dados.motorista
        if m.rg or m.validade_cnh or m.cnh or m.data_emissao_cnh or m.data_nascimento:
            tem_cnh = True
    # extracoes tipo cnh no lote
    if not tem_cnh:
        for ex in (dados.extracoes_gemini or {}).get("cnh") or []:
            if ex and not ex.get("_erro"):
                tem_cnh = True
                break
    if not tem_cnh:
        if not dados.motorista.nome and ex_match.get("nome"):
            dados.motorista.nome = ex_match.get("nome", "")
        if not dados.motorista.cpf and ex_match.get("cpf"):
            dados.motorista.cpf = so_digitos(ex_match.get("cpf", ""))
    else:
        print("[TAC] CNH presente - TAC só fornece RNTRC/nome do PROPRIETÁRIO (não sobrescreve motorista)")
        # se o motorista já ficou com o nome do prop por engano, limpa
        nome_tac = _sanitizar_nome_pessoa(ex_match.get("nome") or "")
        if (
            nome_tac
            and dados.motorista.nome
            and dados.motorista.nome.upper() == nome_tac.upper()
            and not dados.motorista.cnh
        ):
            # só limpa se não tem CNH preenchida (nome veio só do TAC)
            pass


def _aplicar_comprovante(dados: DadosCaso, lista: List[Dict]) -> None:
    if not lista:
        return
    from utils.endereco_fallback import _endereco_parece_logradouro_ruim

    ex = lista[0]
    m = dados.motorista
    end_ex = (ex.get("endereco") or "").strip()
    # não grava aviso de débito / lixo como endereço
    if end_ex and not _endereco_parece_logradouro_ruim(end_ex):
        m.endereco = m.endereco or end_ex
        if ex.get("numero") and ex["numero"] not in (m.endereco or ""):
            m.endereco = f"{m.endereco}, {ex['numero']}".strip(", ")
    elif end_ex:
        print(f"[Comprovante] Endereço ignorado (lixo OCR): {end_ex[:60]!r}")

    cid_ex = (ex.get("cidade") or "").strip()
    if cid_ex and "DETRAN" not in cid_ex.upper() and "DOCUMENTO" not in cid_ex.upper():
        m.cidade = m.cidade or cid_ex
    m.bairro = m.bairro or (ex.get("bairro") or "")
    m.uf = m.uf or (ex.get("uf") or "")
    m.complemento = m.complemento or (ex.get("complemento") or "")
    # CEP só se parecer completo e com cidade/rua úteis, senão fallback limpa
    cep_ex = so_digitos(ex.get("cep", ""))
    if cep_ex and len(cep_ex) == 8:
        if (m.endereco and not _endereco_parece_logradouro_ruim(m.endereco)) or m.cidade:
            m.cep = m.cep or cep_ex
        else:
            # CEP isolado de empresa no topo da conta - não bloqueia fallback
            print(f"[Comprovante] CEP {cep_ex} sem endereço útil - deixa fallback")



def _escolher_placa_ocr_vs_arquivo(placa_ocr: str, placa_arq: str) -> str:
    """
    Nome do arquivo costuma ser a verdade (IUM-1F64.pdf).
    OCR de PDF/foto troca F↔S, B↔H, 0↔O...
    """
    from ocr.ocr_qualidade import (
        limpar_placa as _lp,
        normalizar_placa_mercosul,
        placa_formato_ok,
        _placas_quase_iguais,
    )

    ocr = normalizar_placa_mercosul(_lp(placa_ocr or ""))
    arq = normalizar_placa_mercosul(_lp(placa_arq or ""))
    if arq and placa_formato_ok(arq):
        if not ocr or not placa_formato_ok(ocr):
            if ocr and ocr != arq:
                print(f"[OCR] Placa do arquivo prevalece: {ocr!r} -> {arq!r}")
            return arq
        if ocr == arq:
            return arq
        # 1–2 chars de confusão OCR -> confia no nome do arquivo
        if _placas_quase_iguais(ocr, arq):
            print(
                f"[OCR] Placa OCR≈arquivo (confusão): {ocr} -> {arq} "
                f"(usa nome do arquivo)"
            )
            return arq
        # arquivo e OCR divergem bastante: ainda prefere arquivo se veio do nome
        # (ex. WhatsApp sem placa no nome não passa aqui)
        print(
            f"[OCR] Placa divergente arquivo={arq} OCR={ocr} - usa arquivo"
        )
        return arq
    if ocr and placa_formato_ok(ocr):
        return ocr
    return arq or ocr or ""


def _aplicar_crlvs(
    dados: DadosCaso,
    lista: List[Dict],
    arquivos_crlv: List[Path],
) -> None:
    if not lista:
        return

    # Mapa arquivo -> extração
    por_nome = {Path(ex.get("_arquivo", "")).name: ex for ex in lista}

    def preencher_veiculo(v: DadosVeiculo, ex: Dict) -> None:
        # Placa: nome do arquivo manda quando o OCR troca F↔S, B↔H etc.
        # Ex.: arquivo "IUM-1F64" + OCR "IUM1S64" -> IUM1F64
        placa_ocr = limpar_placa(ex.get("placa", "") or "")
        placa_arq = ""
        for fonte in (
            ex.get("_arquivo"),
            (v.fotos[0] if v.fotos else None),
        ):
            if not fonte:
                continue
            try:
                from ocr.tipos_documento import _placa_no_nome

                placa_arq = _placa_no_nome(Path(fonte).stem) or ""
                if placa_arq:
                    break
            except Exception:
                continue
        if placa_arq:
            placa_arq = limpar_placa(placa_arq)
        placa_final = _escolher_placa_ocr_vs_arquivo(placa_ocr, placa_arq)
        if placa_final:
            if v.placa and limpar_placa(v.placa) != placa_final:
                print(
                    f"[OCR] Placa ajustada: {v.placa} -> {placa_final} "
                    f"(arquivo/OCR)"
                )
            v.placa = placa_final
        elif not v.placa and placa_ocr:
            v.placa = placa_ocr
        v.renavam = v.renavam or so_digitos(ex.get("renavam", ""))
        v.chassi = v.chassi or (ex.get("chassi", "") or "").upper()
        # CRLV: "MARCA / MODELO / VERSÃO" -> um texto para 3 campos no GW
        mmv = (
            ex.get("marca_modelo_versao")
            or " ".join(
                p for p in (ex.get("marca", ""), ex.get("modelo", ""), ex.get("versao", "")) if p
            ).strip()
            or ex.get("marca", "")
            or ex.get("modelo", "")
        )
        if mmv:
            try:
                from ocr.parsers_locais import _limpar_marca_sem_especie

                mmv = _limpar_marca_sem_especie(str(mmv)) or str(mmv)
            except Exception:
                pass
            # se local veio sujo e já temos marca limpa, não piora
            if v.marca_modelo_versao and _marca_extracao_lixo(mmv) and not _marca_extracao_lixo(
                v.marca_modelo_versao
            ):
                mmv = v.marca_modelo_versao
            v.marca_modelo_versao = v.marca_modelo_versao or mmv
            # se marca atual é lixo e mmv limpo, sobrescreve
            if mmv and (
                not v.marca
                or _marca_extracao_lixo(v.marca)
                or len(mmv) < len(v.marca or "")
            ):
                if not _marca_extracao_lixo(mmv):
                    v.marca = mmv
                    v.modelo = mmv
                    v.marca_modelo_versao = mmv
                else:
                    v.marca = v.marca or mmv
                    v.modelo = v.modelo or mmv
            else:
                v.marca = v.marca or mmv
                v.modelo = v.modelo or mmv
        v.ano_fab = v.ano_fab or str(ex.get("ano_fab", "") or "")
        v.ano_mod = v.ano_mod or str(ex.get("ano_mod", "") or "")
        v.cor = v.cor or ex.get("cor", "")
        cid_ex = ex.get("cidade", "") or ""
        if cid_ex and not _cidade_extracao_lixo(cid_ex):
            cid_ok = _sanitizar_cidade(cid_ex)
            if not v.cidade or _cidade_extracao_lixo(v.cidade):
                v.cidade = cid_ok
        elif cid_ex and not v.cidade:
            print(f"[OCR] Cidade lixo ignorada no veículo: {cid_ex!r}")
        v.uf = v.uf or ex.get("uf", "")
        v.proprietario_nome = v.proprietario_nome or ex.get("proprietario_nome", "")
        if not v.tipo:
            if ex.get("eh_semi_reboque"):
                v.tipo = TIPO_CARRETA
            elif ex.get("eh_caminhao_trator"):
                v.tipo = TIPO_CAVALO
        v.aplicar_regras_tipo()

        # Proprietário DESTE CRLV (cavalo e carreta podem ter donos diferentes)
        # Cidade/UF do CRLV = cidade do veículo E do proprietário (obrigatório no GW)
        if ex.get("proprietario_nome") or ex.get("proprietario_cpf_cnpj"):
            prop = DadosProprietario()
            if ex.get("proprietario_nome"):
                nome_ok = _sanitizar_nome_pessoa(ex["proprietario_nome"])
                from ocr.parsers_locais import _nome_prop_parece_lixo
                if nome_ok and not _nome_prop_parece_lixo(nome_ok):
                    prop.nome = nome_ok
                elif nome_ok and _nome_prop_parece_lixo(nome_ok):
                    print(f"[OCR] Prop lixo ignorado no CRLV: {nome_ok!r}")
            doc = so_digitos(ex.get("proprietario_cpf_cnpj", ""))
            if doc:
                prop.cpf_cnpj = doc
            # CRLV "PAULISTA PE" -> prop.cidade (mesmo se TAC já criou o prop sem cidade)
            if ex.get("cidade") and not _cidade_extracao_lixo(str(ex.get("cidade") or "")):
                cid_ok = _sanitizar_cidade(ex["cidade"])
                if not prop.cidade or _cidade_extracao_lixo(prop.cidade):
                    prop.cidade = cid_ok
            elif ex.get("cidade"):
                print(f"[OCR] Cidade lixo ignorada no prop: {ex.get('cidade')!r}")
            if ex.get("uf"):
                prop.uf = ex["uf"]
            # RNTRC do TAC: reutiliza se ainda não tiver (mesmo em props diferentes)
            if dados.rntrc_tac and not prop.rntrc:
                prop.rntrc = dados.rntrc_tac
            prop.aplicar_regras_gw()
            v.proprietario = prop
            v.proprietario_nome = prop.nome or v.proprietario_nome
            # Prop principal: mescla (TAC pode ter criado prop sem cidade antes do CRLV)
            _mesclar_proprietario_caso(dados, prop, preferir=v.tipo in (TIPO_CAVALO, TIPO_TRUCK, ""))

    # Aplica extração em cada slot (casa pelo nome do arquivo da foto)
    slots_fallback = [
        (dados.veiculo, 0),
        (dados.carreta, 1),
        (dados.bitrem, 2),
        (dados.tri_reboque, 3),
    ]
    for v, idx_fb in slots_fallback:
        if not v:
            continue
        nome = Path(v.fotos[0]).name if v.fotos else ""
        if nome in por_nome:
            preencher_veiculo(v, por_nome[nome])
        elif len(lista) > idx_fb:
            preencher_veiculo(v, lista[idx_fb])

    # Se ainda não tem prop principal, usa o de qualquer veículo da composição
    if dados.proprietario is None:
        for v in dados.iter_veiculos():
            if v.proprietario:
                dados.proprietario = v.proprietario
                break


def _mesclar_proprietario_caso(
    dados: DadosCaso,
    prop: DadosProprietario,
    *,
    preferir: bool = False,
) -> None:
    """
    Une dados do prop do CRLV no prop principal do caso.
    TAC costuma criar prop só com RNTRC/nome - o CRLV traz cidade/UF (essencial no GW).
    """
    if dados.proprietario is None:
        dados.proprietario = prop
        return
    p = dados.proprietario
    # mesmo dono (mesmo CPF/CNPJ) ou prop principal ainda sem doc -> mescla campos
    d1 = so_digitos(p.cpf_cnpj)
    d2 = so_digitos(prop.cpf_cnpj)
    mesmo = (d1 and d2 and d1 == d2) or (not d1)
    if not mesmo:
        if preferir:
            dados.proprietario = prop
        return
    if prop.nome and (not p.nome or preferir):
        p.nome = prop.nome
    if prop.cpf_cnpj and not p.cpf_cnpj:
        p.cpf_cnpj = prop.cpf_cnpj
    # Cidade do CRLV SEMPRE preenche se prop estiver sem (ou se preferir e CRLV tem)
    if prop.cidade and (not p.cidade or preferir):
        p.cidade = prop.cidade
    if prop.uf and (not p.uf or preferir):
        p.uf = prop.uf
    if prop.rntrc and not p.rntrc:
        p.rntrc = prop.rntrc
    p.aplicar_regras_gw()


def _sincronizar_cidades_crlv(dados: DadosCaso) -> None:
    """
    Garante cidade/UF no veículo E no proprietário a partir do CRLV.

    - CRLV traz PAULISTA/PE no veículo -> prop também precisa (cadastro prop + save veículo)
    - Se prop já tem cidade e veículo não -> copia prop -> veículo
    - Nunca usa naturalidade do motorista aqui
    """
    veiculos = dados.iter_veiculos()

    # 1) Prop do veículo (por CRLV) -> prop principal se faltar cidade
    for v in veiculos:
        vp = getattr(v, "proprietario", None)
        if vp and (vp.cidade or vp.uf):
            if dados.proprietario is None:
                dados.proprietario = vp
            else:
                if vp.cidade and not dados.proprietario.cidade:
                    dados.proprietario.cidade = vp.cidade
                if vp.uf and not dados.proprietario.uf:
                    dados.proprietario.uf = vp.uf
                if vp.nome and not dados.proprietario.nome:
                    dados.proprietario.nome = vp.nome
                if vp.cpf_cnpj and not dados.proprietario.cpf_cnpj:
                    dados.proprietario.cpf_cnpj = vp.cpf_cnpj

    # 2) Cidade no veículo do CRLV -> preenche prop se ainda vazio
    for v in veiculos:
        if not (v.cidade or "").strip():
            continue
        # prop embutido no veículo
        if v.proprietario:
            if not (v.proprietario.cidade or "").strip():
                v.proprietario.cidade = v.cidade
            if not (v.proprietario.uf or "").strip() and v.uf:
                v.proprietario.uf = v.uf
        # prop principal do caso
        if dados.proprietario:
            if not (dados.proprietario.cidade or "").strip():
                dados.proprietario.cidade = v.cidade
                print(
                    f"[CRLV] Cidade do veículo -> proprietário: "
                    f"{v.cidade}/{v.uf or '?'}"
                )
            if not (dados.proprietario.uf or "").strip() and v.uf:
                dados.proprietario.uf = v.uf

    # 3) Prop com cidade -> qualquer slot sem cidade
    if dados.proprietario and dados.proprietario.cidade:
        for v in veiculos:
            if not (v.cidade or "").strip():
                v.sincronizar_cidade_proprietario(dados.proprietario)

    # 4) Alinha prop embutido do veículo com o principal (mesma cidade do CRLV)
    if dados.proprietario and dados.proprietario.cidade:
        for v in veiculos:
            if v.proprietario is None:
                continue
            d1 = so_digitos(dados.proprietario.cpf_cnpj)
            d2 = so_digitos(v.proprietario.cpf_cnpj)
            if d1 and d2 and d1 != d2:
                continue
            if not v.proprietario.cidade:
                v.proprietario.cidade = dados.proprietario.cidade
            if not v.proprietario.uf and dados.proprietario.uf:
                v.proprietario.uf = dados.proprietario.uf


def _aplicar_generico(dados: DadosCaso, ex: Dict) -> None:
    m = dados.motorista
    if ex.get("nome") and not m.nome:
        m.nome = ex["nome"]
    if ex.get("cpf") and not m.cpf:
        m.cpf = so_digitos(ex["cpf"])
    if ex.get("cep") and not m.cep:
        m.cep = so_digitos(ex["cep"])
    if ex.get("cidade") and not m.cidade:
        m.cidade = ex["cidade"]


def _imprimir_resumo(dados: DadosCaso) -> None:
    m = dados.motorista
    print(f"      Motorista: {m.nome or '?'} | CPF {m.cpf or '?'} | CNH {m.cnh or '?'}")
    rotulos = {
        "veiculo": "Veículo",
        "carreta": "Carreta",
        "bitrem": "Bi-Trem",
        "tri_reboque": "3º Reboque",
    }
    for slot, v in dados.veiculos_composicao():
        if not v:
            continue
        pv = getattr(v, "proprietario", None)
        print(
            f"      {rotulos.get(slot, slot)}: {v.tipo} {v.placa or '?'} "
            f"cap/tara={v.cap_carga}/{v.tara}"
            + (
                f" | prop={pv.cpf_cnpj or pv.nome}"
                if pv and (pv.cpf_cnpj or pv.nome)
                else ""
            )
        )
    if dados.proprietario:
        p = dados.proprietario
        print(
            f"      Proprietário (principal): {p.nome or '?'} | {p.cpf_cnpj or '?'} | "
            f"cidade={p.cidade or '?'}"
        )
    # Aviso se slots tiverem donos diferentes
    docs_props = []
    for slot, v in dados.veiculos_composicao():
        if not v:
            continue
        pv = getattr(v, "proprietario", None)
        if pv and (pv.cpf_cnpj or "").strip():
            docs_props.append((rotulos.get(slot, slot), so_digitos(pv.cpf_cnpj or "")))
    unicos = {d for _, d in docs_props if d}
    if len(unicos) > 1:
        partes = " | ".join(f"{nome}={doc}" for nome, doc in docs_props if doc)
        print(
            f"      [!] Donos DIFERENTES: {partes} "
            f"- cada um será pesquisado/cadastrado no seu veículo"
        )
    # Campos que o OCR pode ter errado (usuário deve confirmar)
    if dados.avisos_ocr:
        print(f"\n      [!] AVISOS OCR - confira no documento e corrija se precisar:")
        for a in dados.avisos_ocr[:20]:
            print(f"         · {a}")
        if len(dados.avisos_ocr) > 20:
            print(f"         · ... +{len(dados.avisos_ocr) - 20} aviso(s)")
