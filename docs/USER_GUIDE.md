# Guia de Uso - DarkAgent Pro v2.0

## 🚀 Início Rápido

### 1. Pré-requisitos

Antes de iniciar, certifique-se de ter:

- **Python 3.10+** instalado
- **FFmpeg** no PATH do sistema
- (Opcional) **CUDA** para aceleração GPU

#### Instalação do FFmpeg

**Windows:**
1. Baixe FFmpeg em: https://ffmpeg.org/download.html
2. Extraia para `C:\ffmpeg`
3. Adicione `C:\ffmpeg\bin` ao PATH
4. Teste executando `ffmpeg -version` no terminal

**Linux:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Mac:**
```bash
brew install ffmpeg
```

### 2. Instalação

```bash
# Clone ou baixe o projeto
cd DarkAgent

# Ative o ambiente virtual
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Instale dependências
pip install -r requirements.txt
```

### 3. Primeiro Uso

```bash
# Execute a aplicação
python src/main.py
```

## 📖 Tutorial Completo

### Processando seu Primeiro Vídeo

#### Passo 1: Cole o Link
- Copie o URL de um vídeo do YouTube
- Cole na barra "🔗 URL do YouTube"

#### Passo 2: Configurações de Download
- **Qualidade**: Escolha 720p para melhor relação qualidade/tamanho
- **Pasta**: Selecione onde salvar o vídeo final

#### Passo 3: Escolha o Modelo de IA
- **Tiny**: Mais rápido, menos preciso (recomendado para testes)
- **Base**: Equilibrado - RECOMENDADO
- **Small**: Mais preciso, mais lento
- **Medium**: Máxima qualidade (requer GPU)

#### Passo 4: Selecione o Estilo de Legenda

**Para TikTok/Reels:**
- TikTok Classic
- TikTok Bold
- Instagram Reels

**Para YouTube:**
- YouTube Shorts
- Clean Minimal

**Criativos:**
- Neon Glow
- Bold Impact
- Gradient Wave

#### Passo 5: Visualize o Preview
- O preview mostra como ficará a legenda
- Ajuste tamanho e posição conforme necessário

#### Passo 6: Processar
- Clique em "🎬 PROCESSAR COM LEGENDAS"
- Aguarde o processamento (vídeo de 5min ≈ 3-5 minutos)

### Resultado

Você terá:
- ✅ Vídeo original baixado
- ✅ Arquivo de legendas (.ass)
- ✅ Vídeo final com legendas queimadas
- ✅ Transcrição completa (.json)

## 🎨 Personalizando Estilos

### Criar Estilo Personalizado

1. Selecione um estilo base
2. Ajuste:
   - Fonte
   - Tamanho
   - Cores
   - Posição
   - Efeitos (borda, sombra)
3. Salve como novo estilo

### Importar/Exportar Estilos

```python
from src.models import EstiloLegenda
import json

# Exportar
estilo = EstiloLegenda(...)
with open('meu_estilo.json', 'w') as f:
    json.dump(estilo.to_dict(), f)

# Importar
with open('meu_estilo.json', 'r') as f:
    dados = json.load(f)
    estilo = EstiloLegenda.from_dict(dados)
```

## ✂️ Gerando Cortes Automáticos

### Configuração de Cortes

1. Ative "Gerar Cortes"
2. Configure:
   - **Número de cortes**: Quantos clips gerar (ex: 3)
   - **Duração**: Segundos por clip (ex: 30s)
   - **Formato**: Vertical (9:16), Horizontal (16:9), Quadrado (1:1)

### Como Funciona

O sistema analisa a transcrição e:
- Identifica os melhores momentos
- Distribui cortes ao longo do vídeo
- Gera clips independentes
- Mantém legendas sincronizadas

## 🖼️ Adicionando Logo

1. Selecione arquivo PNG (com transparência)
2. Escolha posição:
   - Canto superior direito
   - Canto superior esquerdo
   - Canto inferior direito
   - Canto inferior esquerdo
   - Centro
3. Ajuste opacidade (0-100%)

## 🔧 Configurações Avançadas

### Arquivo .env

Crie um arquivo `.env` na raiz do projeto:

```env
# Whisper
WHISPER_MODEL=base
WHISPER_DEVICE=auto
WHISPER_LANGUAGE=pt

# FFmpeg
FFMPEG_THREADS=4
FFMPEG_PRESET=medium

# Performance
CACHE_ENABLED=true
MAX_WORKERS=4
```

### Otimização de Performance

#### Para GPU NVIDIA:
```env
WHISPER_DEVICE=cuda
```

#### Para CPU Rápida:
```env
WHISPER_MODEL=tiny
FFMPEG_THREADS=8
FFMPEG_PRESET=ultrafast
```

#### Para Qualidade Máxima:
```env
WHISPER_MODEL=medium
FFMPEG_PRESET=slow
```

## 🐛 Resolução de Problemas

### Erro: "FFmpeg não encontrado"
**Solução:**
- Instale FFmpeg
- Adicione ao PATH
- Reinicie o terminal

### Erro: "CUDA out of memory"
**Solução:**
- Use modelo menor (tiny ou base)
- Configure `WHISPER_DEVICE=cpu`
- Feche outros programas

### Erro: "Download falhou"
**Solução:**
- Verifique a URL
- Tente outro vídeo
- Sistema tentará 7 estratégias automaticamente

### Legendas desalinhadas
**Solução:**
- Use modelo maior (small ou medium)
- Verifique se o áudio está claro
- Ajuste `duracao_minima_ms` no estilo

### Vídeo final com baixa qualidade
**Solução:**
- Use qualidade 1080p no download
- Configure `FFMPEG_PRESET=slow`
- Aumente CRF para menor compressão

## 📊 Performance Esperada

### Hardware Mínimo:
- CPU: Intel i5 ou equivalente
- RAM: 8 GB
- Disco: 10 GB livres

### Hardware Recomendado:
- CPU: Intel i7 ou equivalente
- RAM: 16 GB
- GPU: NVIDIA GTX 1060 ou superior
- Disco: SSD com 20 GB livres

### Tempos Estimados (vídeo de 5 minutos):

| Componente | CPU | GPU |
|------------|-----|-----|
| Download | 30-60s | 30-60s |
| Transcrição (base) | 90s | 30s |
| Legendas | 2s | 2s |
| Render Final | 120s | 120s |
| **TOTAL** | **~4min** | **~3min** |

## 💡 Dicas e Truques

### 1. Processamento em Lote
```python
from src.core import VideoDownloader, Transcriber

urls = [
    "https://youtube.com/watch?v=...",
    "https://youtube.com/watch?v=...",
]

for url in urls:
    # Processar cada vídeo
    ...
```

### 2. Reutilizar Transcrições
- Transcrições são salvas em JSON
- Reutilize para gerar diferentes estilos
- Economiza tempo de IA

### 3. Preview Rápido
- Use modelo "tiny" para testes rápidos
- Confirme funcionamento
- Reprocesse com modelo melhor

### 4. Backup Automático
```python
# Configure pasta de backup
settings.output_dir = Path("D:/backups/darkagent")
```

### 5. Limpeza de Cache
```bash
# Limpar arquivos temporários
python -c "from src.utils import FileManager; FileManager('.').limpar_temporarios()"
```

## 🔒 Privacidade

- Todos os processos são **100% locais**
- Whisper roda na sua máquina
- Nenhum dado enviado para servidores
- Vídeos ficam no seu computador

## 📞 Suporte

- **Email**: suporte@darkagent.pro
- **Discord**: https://discord.gg/darkagent
- **Issues**: GitHub Issues
- **Documentação**: https://darkagent.pro/docs

## 🎓 Recursos Educacionais

### Vídeos Tutoriais
1. Instalação e Setup
2. Primeiro Vídeo Completo
3. Estilos Personalizados
4. Cortes Automáticos
5. Otimização de Performance

### Exemplos de Uso
- Vídeos de exemplo em: `/docs/examples`
- Templates de estilos em: `/docs/templates`
- Scripts utilitários em: `/docs/scripts`

---

**Versão do Guia**: 2.0  
**Última Atualização**: 12/11/2025
