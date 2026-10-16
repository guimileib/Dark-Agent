# 🎬 DarkAgent Pro

🇧🇷 Português · [🇺🇸 English](README.en.md)

App desktop para Windows que baixa vídeos, gera legendas com IA (Whisper), edita e publica no TikTok, tudo pela mesma janela.

## ✨ Funcionalidades

| Aba | O que faz |
|-----|-----------|
| **Download** | Baixa vídeos do YouTube e de outros sites (yt-dlp) com fallback automático entre estratégias e marcador de texto opcional |
| **Cortes Inteligentes** | Encontra os melhores trechos (cenas + energia do áudio) e exporta clips curtos |
| **Legendas** | Transcreve com Whisper (GPU ou CPU) e queima legendas animadas, com preview em tempo real |
| **Upload** | Publica ou agenda no TikTok com várias contas e navegadores |
| **Editor** | Overlays de texto e imagem com tempo, e compilações ("Adivinhe a Música", rankings) |

Vem com 12 estilos de legenda: TikTok Classic, TikTok Bold, Instagram Reels, YouTube Shorts, Clean Minimal, Neon Glow, Bold Impact, Gradient Wave, Outline Style, Shadow Pop, Typewriter e Karaoke Style.

## 📥 Para usuários

1. Baixe o `DarkAgentLauncher.exe` em **[Releases](https://github.com/guimileib/Dark-Agent/releases/latest)**.
2. Coloque-o em uma pasta própria (ex.: `Documentos\DarkAgent`). O app cria `logs/`, `cache/` e `output/` ao lado do arquivo.
3. Abra o arquivo. Se o Windows SmartScreen avisar, clique em **Mais informações → Executar assim mesmo**.
4. Na primeira execução, aceite baixar o FFmpeg.

> A primeira abertura pode levar 1–2 minutos, porque o executável se descompacta. Só pode haver uma janela aberta por vez: um segundo clique avisa que o app já está aberto.

**Atualizações são automáticas:** ao abrir, o app consulta a última Release e oferece instalar a versão nova.

## 🛠️ Desenvolvimento

Requisitos: Windows, Python 3.11 e Git.

```bash
git clone https://github.com/guimileib/Dark-Agent.git
cd Dark-Agent
python -m venv venv
venv\Scripts\activate

# PyTorch primeiro (CPU; para GPU use o índice CUDA do pytorch.org)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

copy .env.example .env   # opcional
python -m src.main
```

Checagens e testes (os mesmos do CI):

```bash
python scripts/check_structure.py --imports
pytest tests/
```

## 📦 Gerar o .exe

```bash
build_exe.bat
```

O arquivo sai em `dist\DarkAgentLauncher.exe`. Para enviar a alguém, mande **só o `.exe`**: as pastas ao lado dele em `dist\` contêm cookies e chaves suas.

O build usa sempre o `DarkAgentLauncher.spec`, que tem `pathex`, `collect_submodules` e a inclusão do yt-dlp. Sem ele o `.exe` sai incompleto.

## 🚀 Publicar uma versão

O workflow `.github/workflows/ci.yml` funciona assim:

| Evento | O que roda |
|--------|-----------|
| PR para `main` | Checagem estrutural, imports e pytest |
| Push na `main` | O mesmo; se `__version__` ainda não tiver tag, gera o `.exe` e publica a Release |
| Push de tag `vX.Y.Z` | O mesmo, e publica a Release (a tag precisa ser igual a `__version__`) |

Para entregar uma atualização:

```bash
# 1. Suba __version__ em src/__init__.py (ex.: 2.0.3 -> 2.0.4)
# 2. Faça merge/push na main
```

Os usuários recebem a nova versão na próxima vez que abrirem o app. Sem aumentar a versão, o push só roda o CI. O repositório precisa ser público, porque a checagem de atualização é anônima.

## 🧱 Estrutura

```
src/
├── launcher.py   # entry point do .exe (splash, FFmpeg, instância única)
├── main.py       # bootstrap da UI
├── config/       # paths.py (fonte única de caminhos), settings.py
├── models/       # EstiloLegenda, VideoMetadata, Overlay
├── core/         # downloader, transcriber, video_editor, uploader, ...
├── ui/           # main_window e widgets de cada aba
└── utils/        # ffmpeg_utils, single_instance
scripts/check_structure.py   # checagem estrutural usada no CI
```

Docstrings: português, no máximo 3 linhas (resumo + porquê, se precisar). O CI reprova acima disso.

## 🧰 Tecnologias

PyQt6 · yt-dlp · OpenAI Whisper · PyTorch · FFmpeg · Selenium · PyInstaller

## 📧 Contato

- Email: visualizepluss@gmail.com
- Website: https://visualizeplus.com
