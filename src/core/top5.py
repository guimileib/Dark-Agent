"""Pipeline "Top 5": cortes do início (músicas) ou dos momentos engraçados, em contagem #N → #1.

A detecção é heurística offline: picos de energia acima do nível local + áudio "picotado" (risada).
"""

import logging
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Janela (s) usada como "nível normal" do áudio ao redor de cada segundo.
_JANELA_BASE = 15
# Janela (s) para medir o quanto o áudio oscila (risada = rajadas curtas).
_JANELA_RAJADA = 2
# Fração do corte que vem ANTES do pico: a risada/grito chega depois da piada.
_ANTECEDENCIA = 0.7


@dataclass
class Momento:
    """Trecho candidato do ranking: [inicio, inicio+duracao) de um vídeo, com score 0–1."""
    video: Path
    inicio: float
    duracao: float
    score: float = 0.0


def _normalizar(valores: List[float]) -> List[float]:
    """Escala para 0–1 pelo máximo (lista toda zero continua zero)."""
    topo = max(valores, default=0.0)
    return [v / topo for v in valores] if topo > 0 else [0.0] * len(valores)


def pontuar_engracado(energia: List[float]) -> List[float]:
    """Score 0–1 por segundo de "reação" (risada, grito, aplauso) a partir da energia RMS 0–1.

    Pico relativo ao entorno pesa 0.6 e oscilação curta pesa 0.4; volume alto constante (música) não pontua.
    """
    n = len(energia)
    if n == 0:
        return []
    picos, rajadas = [], []
    for i in range(n):
        base = statistics.median(energia[max(0, i - _JANELA_BASE): i + _JANELA_BASE + 1])
        picos.append(max(0.0, energia[i] - base))
        viz = energia[max(0, i - _JANELA_RAJADA): i + _JANELA_RAJADA + 1]
        rajadas.append(statistics.pstdev(viz) if len(viz) > 1 else 0.0)
    picos, rajadas = _normalizar(picos), _normalizar(rajadas)
    bruto = [0.6 * p + 0.4 * r for p, r in zip(picos, rajadas)]
    # Suaviza 3s pra um pico isolado de 1s (porta batendo) não vencer uma risada longa.
    return [
        sum(bruto[max(0, i - 1): i + 2]) / len(bruto[max(0, i - 1): i + 2])
        for i in range(n)
    ]


def escolher_momentos(
    scores_por_video: Dict[Path, List[float]],
    duracao: float,
    quantidade: int = 5,
) -> List[Momento]:
    """Escolhe os `quantidade` melhores cortes sem sobreposição, somando todos os vídeos.

    Retorna do melhor para o pior (o #1 primeiro).
    """
    candidatos = []
    for video, scores in scores_por_video.items():
        total = len(scores)
        if total == 0:
            continue
        for pico, score in enumerate(scores):
            inicio = pico - duracao * _ANTECEDENCIA
            inicio = max(0.0, min(inicio, total - duracao))
            candidatos.append(Momento(Path(video), round(inicio, 2), duracao, score))

    candidatos.sort(key=lambda m: m.score, reverse=True)
    escolhidos: List[Momento] = []
    for cand in candidatos:
        if len(escolhidos) >= quantidade:
            break
        sobrepoe = any(
            m.video == cand.video
            and cand.inicio < m.inicio + m.duracao
            and m.inicio < cand.inicio + cand.duracao
            for m in escolhidos
        )
        if not sobrepoe:
            escolhidos.append(cand)
    return escolhidos


def detectar_momentos_engracados(
    videos: List[Path],
    duracao: float,
    quantidade: int = 5,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancelado: Optional[Callable[[], bool]] = None,
) -> List[Momento]:
    """Analisa o áudio de cada vídeo e retorna os melhores momentos (bloqueante — chamar de QThread)."""
    from core.clip_analyzer import ClipAnalyzer

    scores: Dict[Path, List[float]] = {}
    for i, video in enumerate(videos):
        if cancelado and cancelado():
            return []
        if progress_callback:
            progress_callback(int(i / len(videos) * 100), f"Analisando áudio: {Path(video).name}")
        analisador = ClipAnalyzer(video)
        if analisador.duracao_total < duracao:
            logger.warning(f"{video} tem menos de {duracao}s — ignorado")
            continue
        energia = analisador._analisar_audio()
        scores[Path(video)] = pontuar_engracado([energia[s] for s in sorted(energia)])

    momentos = escolher_momentos(scores, duracao, quantidade)
    logger.info(
        "Top momentos: "
        + ", ".join(f"{m.video.name}@{m.inicio:.0f}s ({m.score:.2f})" for m in momentos)
    )
    return momentos


def ordem_contagem(momentos: List[Momento]) -> List[Momento]:
    """Ordena para exibição em contagem regressiva: pior primeiro (#N), melhor por último (#1)."""
    return sorted(momentos, key=lambda m: m.score)


def rotulo_rank(posicao: int, total: int, titulo: str = "") -> str:
    """Rótulo da posição `posicao` (0-based) na contagem: o primeiro clipe é #total."""
    rank = f"#{total - posicao}"
    return f"{rank} — {titulo.strip()}" if titulo.strip() else rank


def aplicar_edicoes(transcricao: dict, textos: List[str]) -> dict:
    """Retorna cópia da transcrição com os textos editados (vazio remove o segmento).

    Texto alterado perde o timing por palavra do Whisper: redistribui igualmente no segmento.
    """
    novos = []
    for seg, texto in zip(transcricao.get("segmentos", []), textos):
        texto = " ".join(texto.split())
        if not texto:
            continue
        seg = dict(seg)
        if texto != " ".join(seg.get("texto", "").split()):
            palavras = texto.split()
            passo = (seg["fim"] - seg["inicio"]) / len(palavras)
            seg["palavras"] = [
                {
                    "texto": p,
                    "inicio": seg["inicio"] + k * passo,
                    "fim": seg["inicio"] + (k + 1) * passo,
                    "confianca": 1.0,
                }
                for k, p in enumerate(palavras)
            ]
        seg["texto"] = texto
        novos.append(seg)
    return {
        **transcricao,
        "segmentos": novos,
        "texto_completo": " ".join(s["texto"] for s in novos),
    }
