"""Renderizador de previews de legendas usando FFmpeg"""

import logging
import subprocess
from pathlib import Path
from typing import Optional
import tempfile

try:
    from models import EstiloLegenda
    from config import settings
except ImportError:
    from ..models import EstiloLegenda
    from ..config import settings

logger = logging.getLogger(__name__)


class PreviewRenderer:
    """Renderizador otimizado de previews de legendas usando FFmpeg"""
    
    def __init__(self, canvas_size=(640, 360)):
        self.canvas_size = canvas_size
        self.cache_dir = Path(tempfile.gettempdir()) / "darkagent_previews"
        self.cache_dir.mkdir(exist_ok=True)
    
    def renderizar_ffmpeg(self, estilo: EstiloLegenda, texto: Optional[str] = None, output_path: Optional[Path] = None) -> Optional[Path]:
        """
        Renderiza preview da legenda usando FFmpeg com drawtext
        
        Args:
            estilo: Estilo de legenda
            texto: Texto para renderizar (usa texto_exemplo se None)
            output_path: Caminho do arquivo de saída (gera automático se None)
        
        Returns:
            Path do arquivo de preview gerado
        """
        if texto is None:
            texto = estilo.texto_exemplo
        
        # Gerar nome único para cache
        if output_path is None:
            # Sanitizar cor para nome de arquivo (remover &H e &)
            cor_safe = estilo.cor_primaria.replace("&H", "").replace("&", "")
            output_path = self.cache_dir / f"preview_{estilo.id}_{estilo.tamanho}_{cor_safe}.png"
        
        # Verificar se já existe no cache
        if output_path.exists():
            logger.debug(f"Preview em cache: {output_path}")
            return output_path
        
        try:
            # Converter cor primária ASS (&HBBGGRR) para hexadecimal RGB
            def ass_to_rgb(cor_ass):
                cor = cor_ass.replace("&H", "").replace("&", "")
                if len(cor) >= 6:
                    b, g, r = cor[0:2], cor[2:4], cor[4:6]
                    return f"#{r}{g}{b}"
                return "#FFFFFF"
            
            cor_texto = ass_to_rgb(estilo.cor_primaria)
            cor_borda = ass_to_rgb(estilo.cor_borda)
            
            # Determinar fonte e estilo
            fonte = estilo.fonte
            if fonte == "Helvetica" and not Path("C:/Windows/Fonts/Helvetica.ttf").exists():
                fonte = "Arial"  # Fallback
            
            # Usar texto simplificado sem espaços para preview
            texto_preview = "TEXTO_EXEMPLO"
            
            # Construir filtro drawtext SEM aspas (o FFmpeg não precisa de aspas para valores simples)
            drawtext_params = [
                f"text={texto_preview}",
                f"fontcolor={cor_texto}",
                f"fontsize={estilo.tamanho}",
                f"font={fonte}",
            ]
            
            # Adicionar peso da fonte (bold)
            if estilo.bold:
                drawtext_params.append("fontweight=bold")
            
            # Adicionar estilo itálico
            if estilo.italic:
                drawtext_params.append("fontslant=italic")
            
            # Adicionar borda
            if estilo.borda_espessura > 0:
                drawtext_params.append(f"borderw={estilo.borda_espessura}")
                drawtext_params.append(f"bordercolor={cor_borda}")
            
            # Adicionar sombra
            if estilo.sombra_offset > 0:
                drawtext_params.append(f"shadowx={estilo.sombra_offset}")
                drawtext_params.append(f"shadowy={estilo.sombra_offset}")
                drawtext_params.append("shadowcolor=black@0.8")
            
            # Posicionamento (centralizado)
            drawtext_params.append("x=(w-text_w)/2")
            drawtext_params.append("y=(h-text_h)/2")
            
            # Renderizar usando filtro drawtext do FFmpeg
            # Construir filtro manualmente com sintaxe correta
            texto_preview = "PREVIEW"
            
            filtro_parts = [
                f"drawtext=text={texto_preview}",
                f"fontcolor={cor_texto}",
                f"fontsize={estilo.tamanho}",
                f"font={fonte}",
            ]
            
            # Bold e italic usam sintaxe diferente
            if estilo.bold and estilo.italic:
                filtro_parts.append("font='Arial Black':fontfile=/Windows/Fonts/arialbi.ttf")
            elif estilo.bold:
                filtro_parts.append("font='Arial Black'")
            elif estilo.italic:
                filtro_parts.append("fontfile=/Windows/Fonts/ariali.ttf")
            
            # Borda
            if estilo.borda_espessura > 0:
                filtro_parts.append(f"borderw={estilo.borda_espessura}")
                filtro_parts.append(f"bordercolor={cor_borda}")
            
            # Sombra
            if estilo.sombra_offset > 0:
                filtro_parts.append(f"shadowx={estilo.sombra_offset}")
                filtro_parts.append(f"shadowy={estilo.sombra_offset}")
                filtro_parts.append("shadowcolor=black@0.8")
            
            # Posição
            filtro_parts.append("x=(w-text_w)/2")
            filtro_parts.append("y=(h-text_h)/2")
            
            drawtext_filter = ":".join(filtro_parts)
            
            cmd = [
                "ffmpeg",
                "-f", "lavfi",
                "-i", f"color=c=black:s={self.canvas_size[0]}x{self.canvas_size[1]}:d=1",
                "-vf", drawtext_filter,
                "-frames:v", "1",
                "-y",
                str(output_path)
            ]
            
            logger.debug(f"Comando FFmpeg: {' '.join(cmd)}")
            
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if resultado.returncode == 0 and output_path.exists():
                logger.info(f"Preview gerado: {output_path} ({estilo.nome})")
                return output_path
            else:
                logger.error(f"Erro ao gerar preview para {estilo.nome}: {resultado.stderr}")
                return None
        except Exception as e:
            logger.error(f"Erro ao renderizar preview {estilo.nome}: {e}")
            return None
    
    def gerar_preview(self, estilo: EstiloLegenda, tamanho: Optional[int] = None, output_dir: Optional[Path] = None, force: bool = False) -> Optional[Path]:
        """
        Gera preview para um estilo e tamanho específico
        
        Args:
            estilo: Estilo de legenda
            tamanho: Tamanho da fonte (usa estilo.tamanho se None)
            output_dir: Diretório de saída (usa assets/previews se None)
            force: Se True, regenera mesmo se já existir
        
        Returns:
            Path do preview gerado
        """
        if output_dir is None:
            output_dir = settings.assets_dir / "previews"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Usar tamanho especificado ou padrão do estilo
        tamanho_atual = tamanho if tamanho is not None else estilo.tamanho
        tamanho_original = estilo.tamanho
        
        # Temporariamente definir o tamanho desejado
        estilo.tamanho = tamanho_atual
        
        # Nome do arquivo inclui tamanho e cor para diferenciar
        cor_safe = estilo.cor_primaria.replace("&H", "").replace("&", "")
        output_path = output_dir / f"{estilo.id}_size{tamanho_atual}_{cor_safe}.png"
        
        # Se force=True, apagar preview existente
        if force and output_path.exists():
            output_path.unlink()
            logger.debug(f"Preview antigo removido: {output_path}")
        
        # Gerar preview
        preview = self.renderizar_ffmpeg(estilo, output_path=output_path)
        
        # Restaurar tamanho original
        estilo.tamanho = tamanho_original
        
        if preview:
            logger.info(f"Preview gerado: {preview}")
        
        return preview
    
    def gerar_previews_todos_tamanhos(self, estilo: EstiloLegenda, tamanhos: Optional[list] = None, force: bool = False) -> dict[int, Path]:
        """
        Gera previews para todos os tamanhos disponíveis de um estilo
        
        Args:
            estilo: Estilo de legenda
            tamanhos: Lista de tamanhos (usa size_options do estilo se None)
            force: Se True, regenera previews mesmo se já existirem
        
        Returns:
            Dict mapeando tamanho -> caminho do preview
        """
        previews = {}
        
        # Determinar tamanhos a gerar
        if tamanhos is None:
            if hasattr(estilo, 'size_options') and estilo.size_options:
                tamanhos = estilo.size_options
            else:
                tamanhos = [12, 18, 24, 28, 32, 36, 40, 44, 48]
        
        output_dir = settings.assets_dir / "previews"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for tamanho in tamanhos:
            preview_path = self.gerar_preview(estilo, tamanho=tamanho, output_dir=output_dir, force=force)
            
            if preview_path:
                previews[tamanho] = preview_path
                logger.debug(f"Preview gerado: {estilo.id} tamanho {tamanho}")
        
        return previews
    
    def limpar_cache(self):
        """Remove todos os previews em cache"""
        try:
            # Limpar cache temporário
            for arquivo in self.cache_dir.glob("preview_*.png"):
                arquivo.unlink()
                logger.debug(f"Removido do cache: {arquivo}")
            
            for arquivo in self.cache_dir.glob("temp_*.ass"):
                arquivo.unlink()
            
            # Limpar diretório de previews permanentes
            preview_dir = settings.assets_dir / "previews"
            if preview_dir.exists():
                for arquivo in preview_dir.glob("*.png"):
                    arquivo.unlink()
                    logger.debug(f"Removido preview antigo: {arquivo}")
            
            logger.info("Cache de previews limpo com sucesso")
        except Exception as e:
            logger.error(f"Erro ao limpar cache: {e}")
