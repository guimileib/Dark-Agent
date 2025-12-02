"""Geração de arquivos de legendas ASS/SRT"""

import logging
from pathlib import Path
from typing import List, Dict
from io import StringIO

try:
    from models import EstiloLegenda
except ImportError:
    from ..models import EstiloLegenda

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """Gerador otimizado de arquivos de legendas"""
    
    # Template ASS básico
    ASS_HEADER_TEMPLATE = """[Script Info]
Title: DarkAgent Pro Subtitles
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0
Timer: 100.0000
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fonte},{tamanho},{cor_primaria},{cor_secundaria},{cor_borda},{cor_fundo},{bold},{italic},0,0,100,100,0,0,1,{borda},{sombra},{alignment},{margem_h},{margem_h},{margem_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def __init__(self):
        pass
    
    def gerar_ass(
        self,
        transcricao: dict,
        estilo: EstiloLegenda,
        output_path: Path
    ) -> bool:
        """
        Gera arquivo ASS com legendas estilizadas
        
        Args:
            transcricao: Resultado da transcrição com segmentos e palavras
            estilo: Estilo de legenda a aplicar
            output_path: Caminho do arquivo ASS de saída
        
        Returns:
            bool indicando sucesso
        """
        logger.info(f"Gerando arquivo ASS: {output_path}")
        
        try:
            # Construir conteúdo em memória
            buffer = StringIO()
            
            # Header com estilo
            header = self._gerar_header(estilo)
            buffer.write(header)
            
            # Eventos (legendas)
            eventos = self._gerar_eventos(transcricao, estilo)
            buffer.write(eventos)
            
            # Escrever arquivo
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(buffer.getvalue())
            
            logger.info(f"Arquivo ASS gerado com sucesso: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao gerar arquivo ASS: {e}")
            return False
    
    def _gerar_header(self, estilo: EstiloLegenda) -> str:
        """Gera header do ASS com estilo"""
        # Se o estilo define opções de tamanho, escolher o mais próximo disponível
        tamanho_usado = estilo.tamanho
        if hasattr(estilo, "size_options") and estilo.size_options:
            if estilo.tamanho not in estilo.size_options:
                tamanho_usado = min(estilo.size_options, key=lambda x: abs(x - estilo.tamanho))

        return self.ASS_HEADER_TEMPLATE.format(
            fonte=estilo.fonte,
            tamanho=tamanho_usado,
            cor_primaria=estilo.cor_primaria,
            cor_secundaria=estilo.cor_secundaria,
            cor_borda=estilo.cor_borda,
            cor_fundo=estilo.cor_fundo,
            bold=-1 if estilo.bold else 0,
            italic=-1 if estilo.italic else 0,
            borda=estilo.borda_espessura,
            sombra=estilo.sombra_offset,
            alignment=estilo.alignment,
            margem_h=estilo.margem_h,
            margem_v=estilo.margem_v
        )

    @staticmethod
    def _ass_color_override(color_str: str) -> str:
        """Prepara uma string de cor para uso em override tags ASS (adiciona '&' final se necessário)."""
        if not color_str:
            return ""
        c = color_str.strip()
        # Se já terminar com '&', retornar
        if c.endswith("&"):
            return c
        # Se começar com &H, apenas adicionar & ao final
        if c.startswith("&H"):
            return c + "&"
        # Caso geral, retornar como está
        return c

    @staticmethod
    def _norm_text(text: str) -> str:
        """Normaliza texto para comparação (remove espaços duplicados e coloca em lower)."""
        if text is None:
            return ""
        return " ".join(str(text).split()).lower()
    
    def _gerar_eventos(self, transcricao: dict, estilo: EstiloLegenda) -> str:
        """Gera eventos de legendas baseado no tipo de exibição"""
        
        if estilo.tipo_exibicao == "palavra":
            return self._gerar_palavra_por_palavra(transcricao, estilo)
        elif estilo.tipo_exibicao == "palavra_destacada":
            return self._gerar_palavra_destacada(transcricao, estilo)
        elif estilo.tipo_exibicao == "frase":
            return self._gerar_frase_completa(transcricao, estilo)
        elif estilo.tipo_exibicao == "karaoke":
            return self._gerar_karaoke(transcricao, estilo)
        else:
            return self._gerar_palavra_por_palavra(transcricao, estilo)
    
    def _gerar_palavra_por_palavra(self, transcricao: dict, estilo: EstiloLegenda) -> str:
        """Gera legendas mostrando uma palavra por vez"""
        buffer = StringIO()
        last_text = None

        for segmento in transcricao["segmentos"]:
            for palavra in segmento.get("palavras", []):
                texto = palavra.get("texto", "")
                norm = self._norm_text(texto)

                # Evitar emitir palavras idênticas consecutivas (reduz repetições tipo "o que é o que é")
                if norm == last_text:
                    continue

                inicio = self._segundos_para_ass(palavra.get("inicio", 0.0))
                fim = self._segundos_para_ass(palavra.get("fim", palavra.get("inicio", 0.0) + 0.5))

                linha = f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}\n"
                buffer.write(linha)

                last_text = norm
        
        return buffer.getvalue()
    
    def _gerar_palavra_destacada(self, transcricao: dict, estilo: EstiloLegenda) -> str:
        """Gera legendas com palavra atual destacada (estilo TikTok)"""
        buffer = StringIO()
        
        for segmento in transcricao["segmentos"]:
            palavras = segmento["palavras"]
            for i, palavra_atual in enumerate(palavras):
                inicio = self._segundos_para_ass(palavra_atual.get("inicio", 0.0))

                # FIM: usar o início da próxima palavra para evitar sobreposição
                if i + 1 < len(palavras):
                    fim = self._segundos_para_ass(palavras[i + 1].get("inicio", palavra_atual.get("fim", 0.0)))
                else:
                    fim = self._segundos_para_ass(palavra_atual.get("fim", palavra_atual.get("inicio", 0.0) + 0.5))

                # Construir texto com contexto (janela deslizante) - reduzir janela para evitar repetições
                janela_antes = 1
                janela_depois = 1

                contexto_antes = palavras[max(0, i-janela_antes):i]
                contexto_depois = palavras[i+1:min(len(palavras), i+1+janela_depois)]

                texto_partes = []

                # Função auxiliar para adicionar sem repetir consecutivamente
                def add_token(tok: str):
                    if not tok:
                        return
                    norm = self._norm_text(tok)
                    if not texto_partes:
                        texto_partes.append(tok)
                        return
                    last_norm = self._norm_text(texto_partes[-1])
                    if norm == last_norm:
                        return
                    texto_partes.append(tok)

                # Palavras anteriores (cor normal)
                for p in contexto_antes:
                    add_token(p.get("texto", ""))

                # Palavra atual (destacada com cor secundária) - usar override ASS corretamente
                cor_sec = self._ass_color_override(estilo.cor_secundaria)
                cor_prim = self._ass_color_override(estilo.cor_primaria)
                highlighted = f"{{\\c{cor_sec}}}{palavra_atual.get('texto','')}{{\\c{cor_prim}}}"
                add_token(highlighted)

                # Palavras seguintes (cor normal)
                for p in contexto_depois:
                    add_token(p.get("texto", ""))

                texto = " ".join(texto_partes)

                linha = f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}\n"
                buffer.write(linha)
        
        return buffer.getvalue()
    
    def _gerar_frase_completa(self, transcricao: dict, estilo: EstiloLegenda) -> str:
        """Gera legendas com frases completas"""
        buffer = StringIO()
        
        for segmento in transcricao["segmentos"]:
            inicio = self._segundos_para_ass(segmento["inicio"])
            fim = self._segundos_para_ass(segmento["fim"])
            texto = segmento["texto"]
            
            # Quebrar texto em linhas se necessário
            palavras = texto.split()
            linhas = []
            linha_atual = []
            
            for palavra in palavras:
                linha_atual.append(palavra)
                if len(linha_atual) >= estilo.palavras_por_linha:
                    linhas.append(" ".join(linha_atual))
                    linha_atual = []
            
            if linha_atual:
                linhas.append(" ".join(linha_atual))
            
            texto_final = "\\N".join(linhas)
            
            dialogo = f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto_final}\n"
            buffer.write(dialogo)
        
        return buffer.getvalue()
    
    def _gerar_karaoke(self, transcricao: dict, estilo: EstiloLegenda) -> str:
        """Gera legendas estilo karaoke (preenchimento progressivo)"""
        buffer = StringIO()
        
        for segmento in transcricao["segmentos"]:
            palavras = segmento["palavras"]
            
            if not palavras:
                continue
            
            inicio = self._segundos_para_ass(segmento["inicio"])
            fim = self._segundos_para_ass(segmento["fim"])
            
            # Calcular duração de cada palavra em centésimos
            texto_karaoke = []
            for palavra in palavras:
                duracao_cs = int((palavra["fim"] - palavra["inicio"]) * 100)
                texto_karaoke.append(f"{{\\k{duracao_cs}}}{palavra['texto']}")
            
            texto = " ".join(texto_karaoke)
            
            linha = f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}\n"
            buffer.write(linha)
        
        return buffer.getvalue()
    
    @staticmethod
    def _segundos_para_ass(segundos: float) -> str:
        """Converte segundos para formato ASS (H:MM:SS.CC)"""
        # Arredondar para 2 casas decimais primeiro para evitar erros de precisão
        segundos = round(segundos, 2)
        
        horas = int(segundos // 3600)
        minutos = int((segundos % 3600) // 60)
        secs = segundos % 60
        
        # Correção para caso de arredondamento (ex: 59.996 -> 60.00)
        if secs >= 60:
            secs = 0
            minutos += 1
            if minutos >= 60:
                minutos = 0
                horas += 1
        
        return f"{horas}:{minutos:02d}:{secs:05.2f}"
    
    def gerar_srt(self, transcricao: dict, output_path: Path) -> bool:
        """
        Gera arquivo SRT simples (sem estilos)
        
        Args:
            transcricao: Resultado da transcrição
            output_path: Caminho do arquivo SRT
        
        Returns:
            bool indicando sucesso
        """
        logger.info(f"Gerando arquivo SRT: {output_path}")
        
        try:
            buffer = StringIO()
            contador = 1
            
            for segmento in transcricao["segmentos"]:
                inicio = self._segundos_para_srt(segmento["inicio"])
                fim = self._segundos_para_srt(segmento["fim"])
                texto = segmento["texto"]
                
                buffer.write(f"{contador}\n")
                buffer.write(f"{inicio} --> {fim}\n")
                buffer.write(f"{texto}\n\n")
                
                contador += 1
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(buffer.getvalue())
            
            logger.info(f"Arquivo SRT gerado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao gerar SRT: {e}")
            return False
    
    @staticmethod
    def _segundos_para_srt(segundos: float) -> str:
        """Converte segundos para formato SRT (HH:MM:SS,mmm)"""
        horas = int(segundos // 3600)
        minutos = int((segundos % 3600) // 60)
        secs = int(segundos % 60)
        milissegundos = int((segundos % 1) * 1000)
        
        return f"{horas:02d}:{minutos:02d}:{secs:02d},{milissegundos:03d}"
