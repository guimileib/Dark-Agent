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
git clone https://github.com/guimileib/Dark-Agent.git
cd Dark-Agent

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
python -m src.main
```

## 📦 Gerar o Launcher (.exe)

O executável distribuído é o `DarkAgentLauncher.exe`, gerado **sempre** a partir
do `DarkAgentLauncher.spec` (nunca use `pyinstaller --onefile src/main.py` — o
`.spec` contém `pathex`, `collect_submodules` e `hiddenimports` obrigatórios;
sem eles o bundle sai incompleto e quebra com `ModuleNotFoundError`).

### Build local (para testar)

```bash
# Com o venv ativado e dependências instaladas:
pip install pyinstaller
pyinstaller DarkAgentLauncher.spec --clean --noconfirm

# Artefato final:
dist\DarkAgentLauncher.exe
```

### Release oficial (com auto-update)

O build de release é feito pelo GitHub Actions (`.github/workflows/release.yml`).
**Importante:** merge para `main` NÃO publica release — só o push de tag publica.

```bash
# 1. Suba a versão em src/__init__.py (ex.: 2.0.1 -> 2.0.2)
#    __version__ = "2.0.2"

# 2. Commit e push
git add src/__init__.py
git commit -m "chore: bump version 2.0.1 -> 2.0.2"
git push

# 3. Crie e envie a tag (dispara o workflow: pytest -> build -> release)
git tag v2.0.2
git push origin v2.0.2
```

O workflow roda os testes, gera o `.exe` e publica em **Releases** com o asset
`DarkAgentLauncher.exe`. Alternativa sem terminal: aba *Actions* → workflow
*Build and Release Windows Executable* → *Run workflow* → informe a tag.

### Como o auto-update funciona

Ao abrir, o app consulta a release mais recente em
`github.com/guimileib/Dark-Agent/releases` e compara a tag com o
`__version__` embutido no `.exe`. Se a release for mais nova, oferece baixar e
aplicar. Ou seja: **o update só chega para os usuários depois de publicar uma
tag nova com `__version__` maior** — commits na `main` sozinhos não geram
atualização. Falhas na checagem ficam registradas em `logs/`.

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
