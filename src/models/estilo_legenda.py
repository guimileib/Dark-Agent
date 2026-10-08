"""Modelos de dados do DarkAgent Pro v2.0"""

from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime

@dataclass
class EstiloLegenda:
    """Definição completa de um estilo de legenda"""
    
    # Identificação
    id: str
    nome: str
    categoria: Literal["social", "profissional", "criativo"]
    
    # Tipografia
    fonte: str = "Arial"
    tamanho: int = 48
    # Opções de tamanhos disponíveis (permite tamanhos menores para escolha)
    size_options: list[int] = field(default_factory=lambda: [12, 18, 24, 28, 32, 36, 40, 44, 48])
    bold: bool = True
    italic: bool = False
    
    # Cores (formato ASS: &HBBGGRR)
    cor_primaria: str = "&H00FFFFFF"  # Branco
    cor_secundaria: str = "&H0000FFFF"  # Amarelo
    cor_borda: str = "&H00000000"  # Preto
    cor_fundo: str = "&H80000000"  # Transparente
    
    # Efeitos
    borda_espessura: int = 3
    sombra_offset: int = 2
    sombra_blur: int = 3
    
    # Posicionamento
    alignment: int = 2  # 2=embaixo, 5=centro, 8=topo
    margem_v: int = 30  # Distância vertical das bordas
    margem_h: int = 50  # Distância horizontal das bordas
    
    # Comportamento
    tipo_exibicao: Literal["palavra", "frase", "karaoke", "palavra_destacada"] = "palavra_destacada"
    palavras_por_linha: int = 3
    duracao_minima_ms: int = 300  # Tempo mínimo de exibição
    
    # Preview
    texto_exemplo: str = "Esta PALAVRA está em destaque"
    imagem_preview: Optional[str] = None
    
    def to_dict(self):
        """Converte para dicionário"""
        return {
            "id": self.id,
            "nome": self.nome,
            "categoria": self.categoria,
            "fonte": self.fonte,
            "tamanho": self.tamanho,
            "bold": self.bold,
            "italic": self.italic,
            "cor_primaria": self.cor_primaria,
            "cor_secundaria": self.cor_secundaria,
            "cor_borda": self.cor_borda,
            "cor_fundo": self.cor_fundo,
            "borda_espessura": self.borda_espessura,
            "sombra_offset": self.sombra_offset,
            "sombra_blur": self.sombra_blur,
            "alignment": self.alignment,
            "margem_v": self.margem_v,
            "margem_h": self.margem_h,
            "tipo_exibicao": self.tipo_exibicao,
            "palavras_por_linha": self.palavras_por_linha,
            "duracao_minima_ms": self.duracao_minima_ms,
            "texto_exemplo": self.texto_exemplo,
            "imagem_preview": self.imagem_preview
            ,
            "size_options": self.size_options
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Cria instância a partir de dicionário"""
        # Garantir que options de tamanho estejam presentes
        if "size_options" not in data:
            data["size_options"] = [12, 18, 24, 28, 32, 36, 40, 44, 48]
        return cls(**data)


@dataclass
class Palavra:
    """Representa uma palavra transcrita com timestamps"""
    texto: str
    inicio: float  # Segundos
    fim: float  # Segundos
    confianca: float = 1.0


@dataclass
class Segmento:
    """Representa um segmento de transcrição"""
    id: int
    texto: str
    inicio: float
    fim: float
    palavras: list[Palavra] = field(default_factory=list)


@dataclass
class Transcricao:
    """Resultado completo de uma transcrição"""
    texto_completo: str
    segmentos: list[Segmento]
    idioma: str
    duracao: float
    modelo_usado: str
    data_criacao: datetime = field(default_factory=datetime.now)
