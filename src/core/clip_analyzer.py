import logging
import subprocess
import sys
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# POSIX-safe: creationflags só existe no Windows. Passar o kwarg direto
# crasha em Python 3.12+ no Linux/macOS, então expandimos via **_SP_KW.
_SP_KW: dict = {}
if sys.platform == "win32":
    _SP_KW["creationflags"] = subprocess.CREATE_NO_WINDOW


class ClipAnalyzer:
    """Analisa vídeo e sugere melhores trechos para clips virais"""
    
    def __init__(self, video_path: Path):
        self.video_path = Path(video_path)
        self.duracao_total = self._obter_duracao()
        self.frame_rate = self._obter_frame_rate()
    
    def _obter_duracao(self) -> float:
        """Obtém duração do vídeo em segundos"""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(self.video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, **_SP_KW)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data['format']['duration'])
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Erro ao obter duração: {e}")
            return 0.0
    
    def _obter_frame_rate(self) -> float:
        """Obtém frame rate do vídeo"""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "json",
                str(self.video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, **_SP_KW)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                rate_str = data['streams'][0]['r_frame_rate']
                num, den = map(int, rate_str.split('/'))
                return num / den
            
            return 30.0
            
        except Exception as e:
            logger.error(f"Erro ao obter frame rate: {e}")
            return 30.0
    
    def analisar_clips(self, duracao_min=15, duracao_max=60, max_clips=10) -> List[Dict]:
        clips = []
        
        if self.duracao_total < duracao_min:
            logger.warning("Vídeo muito curto para análise")
            return clips
        
        # Analisar mudanças de cena
        mudancas_cena = self._detectar_mudancas_cena()
        
        # Analisar movimento
        movimento = self._analisar_movimento()
        
        # Analisar áudio (energia, silêncios)
        energia_audio = self._analisar_audio()
        
        # Gerar janelas deslizantes
        step = max(5, duracao_min // 2)  # Passo de 5s ou metade da duração mínima
        
        for inicio in range(0, int(self.duracao_total - duracao_min), step):
            for duracao in range(duracao_min, min(duracao_max + 1, int(self.duracao_total - inicio))):
                fim = inicio + duracao
                
                # Calcular score deste trecho
                score = self._calcular_score_clip(
                    inicio, fim,
                    mudancas_cena,
                    movimento,
                    energia_audio
                )
                
                razoes = self._gerar_razoes(
                    score, inicio, fim,
                    mudancas_cena,
                    movimento,
                    energia_audio
                )
                
                clips.append({
                    'inicio': inicio,
                    'fim': fim,
                    'duracao': duracao,
                    'score': score,
                    'razoes': razoes
                })
        
        # Ordenar por score e retornar top N
        clips.sort(key=lambda x: x['score'], reverse=True)
        
        # Remover clips muito sobrepostos (NMS - Non-Maximum Suppression)
        clips_filtrados = self._nms_clips(clips, overlap_threshold=0.3)
        
        if not max_clips or max_clips <= 0:
            return clips_filtrados
            
        return clips_filtrados[:max_clips]
    
    def _detectar_mudancas_cena(self) -> List[float]:
        """Detecta timestamps de mudanças de cena usando FFmpeg"""
        try:
            # Usar filtro scene do FFmpeg
            cmd = [
                "ffmpeg",
                "-i", str(self.video_path),
                "-vf", "select='gt(scene,0.3)',showinfo",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                **_SP_KW
            )

            # Parsear output para encontrar timestamps
            mudancas = []
            for line in result.stderr.split('\n'):
                if 'pts_time:' in line:
                    try:
                        time_str = line.split('pts_time:')[1].split()[0]
                        mudancas.append(float(time_str))
                    except (ValueError, IndexError):
                        continue
            
            return mudancas
            
        except Exception as e:
            logger.warning(f"Erro ao detectar cenas: {e}")
            # Fallback: gerar mudanças estimadas a cada 10s
            return list(range(0, int(self.duracao_total), 10))
    
    def _analisar_movimento(self) -> Dict[int, float]:
        """
        Analisa movimento no vídeo por segundo
        Retorna dict {segundo: score_movimento}
        """
        # Placeholder determinístico até análise real (optical flow) ser implementada.
        # Retornar 0.5 fixo evita scores aleatórios que mudam a cada clique.
        return {i: 0.5 for i in range(int(self.duracao_total))}
    
    def _analisar_audio(self) -> Dict[int, float]:
        """
        Analisa energia do áudio por segundo via astats em janelas de 1s.

        Usa um único pass do ffmpeg: resample para 8kHz, força frames de 8000
        samples (= 1 segundo cada) e pede astats com reset=1 para emitir RMS
        por janela. Fallback para volumedetect global se astats falhar.
        """
        duration = max(int(self.duracao_total), 1)
        try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-i", str(self.video_path),
                "-af", "aresample=8000,asetnsamples=n=8000:p=0,astats=metadata=1:reset=1",
                "-f", "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                **_SP_KW,
            )

            energia: Dict[int, float] = {}
            in_overall = False
            seg_idx = 0
            for raw in result.stderr.splitlines():
                line = raw.strip()
                if "Overall" in line:
                    in_overall = True
                    continue
                if in_overall and line.startswith("Channel:"):
                    in_overall = False
                    continue
                if in_overall and "RMS level dB" in line:
                    try:
                        rms = float(line.split(":")[-1].strip())
                    except ValueError:
                        in_overall = False
                        continue
                    if rms != rms or rms == float("-inf"):
                        score = 0.0
                    else:
                        # -60dB → 0, -10dB → 1
                        score = float(np.clip((rms + 60) / 50, 0, 1))
                    energia[seg_idx] = score
                    seg_idx += 1
                    in_overall = False

            if not energia:
                return self._fallback_audio_global()

            # Preencher segundos faltantes com último valor conhecido
            ultimo = next(iter(energia.values()))
            for i in range(duration):
                if i in energia:
                    ultimo = energia[i]
                else:
                    energia[i] = ultimo
            return energia

        except Exception as e:
            logger.warning(f"Erro ao analisar áudio (astats): {e}")
            return self._fallback_audio_global()

    def _fallback_audio_global(self) -> Dict[int, float]:
        """Caminho de fallback: volumedetect global (mesmo score para todos os segundos)."""
        try:
            cmd = [
                "ffmpeg",
                "-i", str(self.video_path),
                "-af", "volumedetect",
                "-f", "null",
                "-"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                **_SP_KW
            )

            # Parsear volume médio
            mean_volume = -20.0  # Default
            for line in result.stderr.split('\n'):
                if 'mean_volume:' in line:
                    try:
                        mean_volume = float(line.split('mean_volume:')[1].split('dB')[0].strip())
                    except (ValueError, IndexError):
                        pass

            # Normalizar volume médio do vídeo inteiro em score 0-1 (-60dB -> 0, -10dB -> 1).
            # Todos os segundos recebem o mesmo score: é impreciso, mas determinístico.
            # Para análise por-segundo real, usar astats com janela deslizante.
            score_global = float(np.clip((mean_volume + 60) / 50, 0, 1))
            return {i: score_global for i in range(int(self.duracao_total))}
            
        except Exception as e:
            logger.warning(f"Erro ao analisar áudio: {e}")
            return {i: 0.6 for i in range(int(self.duracao_total))}
    
    def _calcular_score_clip(
        self,
        inicio: int,
        fim: int,
        mudancas_cena: List[float],
        movimento: Dict[int, float],
        energia_audio: Dict[int, float]
    ) -> float:
        """
        Calcula score de viralização para um clip.

        Pesos atuais (movimento desativado por ser placeholder fixo):
        - Mudanças de cena (0.30) — dinâmica visual
        - Energia de áudio per-segundo (0.40) — excitação real do trecho
        - Duração ideal (0.20) — sweet spot de shorts
        - Posicionamento (0.10) — início/fim do vídeo
        """
        scores = []

        # 1. Mudanças de cena (peso: 0.30)
        cenas_no_clip = [c for c in mudancas_cena if inicio <= c <= fim]
        duracao = fim - inicio
        cenas_por_segundo = len(cenas_no_clip) / duracao if duracao > 0 else 0
        # Ideal: 0.1-0.3 cenas/segundo
        score_cenas = 1.0 - abs(cenas_por_segundo - 0.2) / 0.2
        score_cenas = float(np.clip(score_cenas, 0, 1))
        scores.append(score_cenas * 0.30)

        # 2. Energia de áudio per-segundo (peso: 0.40)
        energia_media = float(np.mean([energia_audio.get(i, 0.5) for i in range(inicio, fim)]))
        scores.append(energia_media * 0.40)

        # 3. Duração ideal (peso: 0.20)
        # Shorts ideais: 15-60s, ótimo: 30-45s
        if 30 <= duracao <= 45:
            score_duracao = 1.0
        elif 15 <= duracao < 30:
            score_duracao = 0.7 + (duracao - 15) / 15 * 0.3
        elif 45 < duracao <= 60:
            score_duracao = 1.0 - (duracao - 45) / 15 * 0.3
        else:
            score_duracao = 0.5
        scores.append(score_duracao * 0.20)

        # 4. Posicionamento (peso: 0.10)
        # Primeiros 30% e últimos 30% do vídeo tendem a ser melhores
        posicao_relativa = inicio / self.duracao_total if self.duracao_total > 0 else 0.0
        if posicao_relativa <= 0.3 or posicao_relativa >= 0.7:
            score_posicao = 0.9
        else:
            score_posicao = 0.6
        scores.append(score_posicao * 0.10)

        # Score final ∈ [0, 1]
        return float(np.clip(sum(scores), 0.0, 1.0))
    
    def _gerar_razoes(
        self,
        score: float,
        inicio: int,
        fim: int,
        mudancas_cena: List[float],
        movimento: Dict[int, float],
        energia_audio: Dict[int, float]
    ) -> List[str]:
        """Gera lista de razões para o score"""
        razoes = []
        
        # Mudanças de cena
        cenas_no_clip = len([c for c in mudancas_cena if inicio <= c <= fim])
        if cenas_no_clip >= 3:
            razoes.append(f"🎬 {cenas_no_clip} mudanças de cena (alta dinâmica)")
        elif cenas_no_clip == 0:
            razoes.append("📹 Cena contínua (boa para foco)")
        
        # Movimento
        movimento_medio = np.mean([movimento.get(i, 0.5) for i in range(inicio, fim)])
        if movimento_medio > 0.7:
            razoes.append("⚡ Alto movimento (engajante)")
        elif movimento_medio < 0.3:
            razoes.append("🎯 Baixo movimento (calmante)")
        
        # Energia de áudio
        energia_media = np.mean([energia_audio.get(i, 0.5) for i in range(inicio, fim)])
        if energia_media > 0.7:
            razoes.append("🔊 Alta energia de áudio")
        elif energia_media < 0.3:
            razoes.append("🔇 Áudio suave")
        
        # Duração
        duracao = fim - inicio
        if 30 <= duracao <= 45:
            razoes.append(f"⏱️ Duração ideal ({duracao}s)")
        elif duracao < 30:
            razoes.append(f"⚡ Clip curto ({duracao}s)")
        
        # Posicionamento
        posicao_relativa = inicio / self.duracao_total
        if posicao_relativa <= 0.3:
            razoes.append("🎯 Início do vídeo (hook forte)")
        elif posicao_relativa >= 0.7:
            razoes.append("🏁 Final do vídeo (conclusão)")
        
        # Score geral
        if score >= 0.8:
            razoes.append("🔥 ALTÍSSIMO potencial viral!")
        elif score >= 0.6:
            razoes.append("✨ Bom potencial viral")
        
        return razoes[:5]  # Limitar a 5 razões
    
    def _nms_clips(self, clips: List[Dict], overlap_threshold=0.3) -> List[Dict]:
        """
        Non-Maximum Suppression para remover clips muito sobrepostos
        Mantém apenas o clip com maior score entre clips sobrepostos
        """
        if not clips:
            return []
        
        # Já está ordenado por score
        clips_filtrados = []
        clips_usados = set()
        
        for clip in clips:
            # Verificar sobreposição com clips já adicionados
            sobreposto = False
            
            for clip_existente in clips_filtrados:
                overlap = self._calcular_overlap(
                    clip['inicio'], clip['fim'],
                    clip_existente['inicio'], clip_existente['fim']
                )
                
                if overlap > overlap_threshold:
                    sobreposto = True
                    break
            
            if not sobreposto:
                clips_filtrados.append(clip)
        
        return clips_filtrados
    
    def _calcular_overlap(self, inicio1, fim1, inicio2, fim2) -> float:
        """Calcula proporção de overlap entre dois intervalos"""
        overlap_inicio = max(inicio1, inicio2)
        overlap_fim = min(fim1, fim2)
        
        if overlap_fim <= overlap_inicio:
            return 0.0
        
        overlap_duracao = overlap_fim - overlap_inicio
        duracao1 = fim1 - inicio1
        duracao2 = fim2 - inicio2
        
        # Retorna overlap relativo ao menor clip
        return overlap_duracao / min(duracao1, duracao2)
    
    def extrair_clip(self, inicio: int, fim: int, output_path) -> bool:
        """
        Extrai um clip do vídeo
        
        Args:
            inicio: Timestamp de início em segundos
            fim: Timestamp de fim em segundos
            output_path: Caminho para salvar o clip (str ou Path)
        
        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Garantir que output_path seja um Path
            output_path = Path(output_path)
            
            duracao = fim - inicio
            
            cmd = [
                "ffmpeg",
                "-ss", str(inicio),
                "-i", str(self.video_path),
                "-t", str(duracao),
                "-c", "copy",
                "-y",
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                **_SP_KW
            )
            
            if result.returncode == 0 and output_path.exists():
                logger.info(f"Clip extraído: {output_path}")
                return True
            else:
                logger.error(f"Erro ao extrair clip: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao extrair clip: {e}")
            return False
