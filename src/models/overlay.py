"""Data models for the video overlay editor."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class OverlayElemento:
    """A single overlay element (text or image) placed on a video with timing."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tipo: Literal["texto", "imagem"] = "texto"

    # Timing (seconds)
    inicio: float = 0.0
    fim: float = 5.0

    # Position — one of the 3x3 grid presets or "custom"
    posicao_preset: str = "bottom_center"
    x_custom: int = 0
    y_custom: int = 0

    # ── Text-specific ────────────────────────────────────────────────
    texto: str = "Texto aqui"
    fonte: str = "Arial"
    tamanho_fonte: int = 48
    cor_texto: str = "#FFFFFF"
    cor_borda: str = "#000000"
    borda_espessura: int = 2
    bold: bool = True

    # ── Image-specific ───────────────────────────────────────────────
    caminho_imagem: str = ""
    largura_imagem: int = 200  # 0 = original size
    opacidade: float = 1.0

    # ── Helpers ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "inicio": self.inicio,
            "fim": self.fim,
            "posicao_preset": self.posicao_preset,
            "x_custom": self.x_custom,
            "y_custom": self.y_custom,
            "texto": self.texto,
            "fonte": self.fonte,
            "tamanho_fonte": self.tamanho_fonte,
            "cor_texto": self.cor_texto,
            "cor_borda": self.cor_borda,
            "borda_espessura": self.borda_espessura,
            "bold": self.bold,
            "caminho_imagem": self.caminho_imagem,
            "largura_imagem": self.largura_imagem,
            "opacidade": self.opacidade,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OverlayElemento:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            tipo=data.get("tipo", "texto"),
            inicio=float(data.get("inicio", 0.0)),
            fim=float(data.get("fim", 5.0)),
            posicao_preset=data.get("posicao_preset", "bottom_center"),
            x_custom=int(data.get("x_custom", 0)),
            y_custom=int(data.get("y_custom", 0)),
            texto=data.get("texto", "Texto aqui"),
            fonte=data.get("fonte", "Arial"),
            tamanho_fonte=int(data.get("tamanho_fonte", 48)),
            cor_texto=data.get("cor_texto", "#FFFFFF"),
            cor_borda=data.get("cor_borda", "#000000"),
            borda_espessura=int(data.get("borda_espessura", 2)),
            bold=bool(data.get("bold", True)),
            caminho_imagem=data.get("caminho_imagem", ""),
            largura_imagem=int(data.get("largura_imagem", 200)),
            opacidade=float(data.get("opacidade", 1.0)),
        )

    def __str__(self) -> str:
        if self.tipo == "texto":
            preview = self.texto[:30] + ("..." if len(self.texto) > 30 else "")
            return f"[TXT] {preview}  ({self.inicio:.1f}s - {self.fim:.1f}s)"
        else:
            from pathlib import Path
            nome = Path(self.caminho_imagem).name if self.caminho_imagem else "sem imagem"
            return f"[IMG] {nome}  ({self.inicio:.1f}s - {self.fim:.1f}s)"


@dataclass
class OverlayTemplate:
    """A reusable collection of overlay elements."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    nome: str = "Novo Template"
    descricao: str = ""
    elementos: list[OverlayElemento] = field(default_factory=list)
    data_criacao: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            "elementos": [e.to_dict() for e in self.elementos],
            "data_criacao": self.data_criacao,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OverlayTemplate:
        elementos = [OverlayElemento.from_dict(e) for e in data.get("elementos", [])]
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            nome=data.get("nome", "Sem nome"),
            descricao=data.get("descricao", ""),
            elementos=elementos,
            data_criacao=data.get("data_criacao", datetime.now().isoformat()),
        )
