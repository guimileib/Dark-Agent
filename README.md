# 🎬 DarkAgent Pro v2.0

Sistema desktop profissional para processamento de vídeos do YouTube com IA.

## ✨ Funcionalidades

- ⚡ **Download Ultra-Robusto**: 7 estratégias de fallback automático
- 🤖 **Transcrição com IA**: Whisper otimizado (GPU/CPU)
- 📝 **Legendas Profissionais**: 12+ estilos pré-configurados (TikTok, Reels, YouTube)
- 👀 **Preview em Tempo Real**: Visualize legendas instantaneamente (<50ms)
- ✂️ **Edição Avançada**: Cortes automáticos, logos, efeitos
- 🎨 **Editor Visual**: Personalize fontes, cores, posições com sliders

## 🚀 Instalação

### Requisitos

- Python 3.10+
- FFmpeg instalado no sistema
- (Opcional) CUDA para transcrição acelerada

### Passos

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/darkagent-pro-v2.git
cd darkagent-pro-v2

# 2. Crie ambiente virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure variáveis (opcional)
copy .env.example .env
# Edite .env com suas preferências

# 5. Execute
python src/main.py
```

## 📖 Como Usar

1. **Cole o link do YouTube** na barra superior
2. **Escolha a qualidade** do vídeo (720p recomendado)
3. **Selecione o modelo IA** (Base = melhor custo-benefício)
4. **Escolha um estilo de legenda** ou personalize
5. **Visualize o preview** em tempo real
6. **Clique em Processar** e aguarde!

## 🎨 Estilos de Legendas

- **TikTok Classic**: Palavra destacada amarela
- **Instagram Reels**: Palavra centralizada bold
- **YouTube Shorts**: Frases embaixo
- **Clean Minimal**: Branco simples
- **Neon Glow**: Efeito brilho colorido
- E mais 7 estilos!

## 🛠️ Tecnologias

- **PyQt6**: Interface gráfica moderna
- **yt-dlp**: Download robusto de vídeos
- **OpenAI Whisper**: Transcrição com IA
- **FFmpeg**: Processamento de vídeo
- **PyTorch**: Aceleração GPU

## 📊 Performance

| Operação | Tempo (vídeo 5min) |
|----------|-------------------|
| Download | < 60s |
| Transcrição | < 30s |
| Legendas | < 2s |
| Render Final | < 120s |

## 📝 Licença

MIT License - veja [LICENSE](LICENSE)

## 🤝 Contribuindo

Pull requests são bem-vindos! Para mudanças grandes, abra uma issue primeiro.

## 📧 Contato

- Email: visualizepluss@gmail.com
- Website: https://visualizeplus.com    

---

**Versão:** 2.0  
**Última Atualização:**  02/12/2025
