# 📊 Diagramas - DarkAgent Pro v2.0

## Diagramas de Arquitetura e Fluxos

Este documento contém todos os diagramas Mermaid do sistema DarkAgent Pro v2.0.

---

## 1. 🏗️ Diagrama de Arquitetura do Sistema

### Visão Geral dos Componentes

```mermaid
graph TB
    subgraph "🎨 UI Layer - PyQt6"
        UI[Main Window]
        DL_UI[Download Tab]
        LEG_UI[Legendas Tab<br/>+ Preview Renderer]
        CORTE_UI[Cortes Tab]
        CONFIG_UI[Configurações]
    end
    
    subgraph "🧠 Core Engine"
        DL[VideoDownloader<br/>7 estratégias]
        TRANS[Transcriber<br/>Whisper optimized]
        LEG_GEN[SubtitleGenerator<br/>ASS/SRT]
        EDITOR[VideoEditor<br/>FFmpeg wrapper]
        PREV[PreviewRenderer<br/>QImage/PIL]
    end
    
    subgraph "💾 Data Layer"
        CACHE[Model Cache<br/>Whisper models]
        ESTILOS[Estilos Database<br/>JSON/SQLite]
        VIDEOS[Videos Storage<br/>Local filesystem]
    end
    
    subgraph "🔧 External Tools"
        YTDLP[yt-dlp]
        FFMPEG[FFmpeg]
        FFPROBE[FFprobe]
        WHISPER[OpenAI Whisper]
    end
    
    %% Conexões UI -> Core
    UI --> DL_UI
    UI --> LEG_UI
    UI --> CORTE_UI
    UI --> CONFIG_UI
    
    DL_UI --> DL
    LEG_UI --> TRANS
    LEG_UI --> LEG_GEN
    LEG_UI --> PREV
    CORTE_UI --> EDITOR
    
    %% Conexões Core -> Data
    DL --> VIDEOS
    TRANS --> CACHE
    LEG_GEN --> ESTILOS
    PREV --> ESTILOS
    
    %% Conexões Core -> External
    DL --> YTDLP
    DL --> FFPROBE
    TRANS --> WHISPER
    LEG_GEN --> FFMPEG
    EDITOR --> FFMPEG
    
    %% Estilos
    classDef uiClass fill:#667eea,stroke:#333,stroke-width:2px,color:#fff
    classDef coreClass fill:#f093fb,stroke:#333,stroke-width:2px,color:#fff
    classDef dataClass fill:#4facfe,stroke:#333,stroke-width:2px,color:#fff
    classDef externalClass fill:#43e97b,stroke:#333,stroke-width:2px,color:#000
    
    class UI,DL_UI,LEG_UI,CORTE_UI,CONFIG_UI uiClass
    class DL,TRANS,LEG_GEN,EDITOR,PREV coreClass
    class CACHE,ESTILOS,VIDEOS dataClass
    class YTDLP,FFMPEG,FFPROBE,WHISPER externalClass
```

### Descrição dos Componentes:

#### 🎨 UI Layer (PyQt6)
- **Main Window**: Janela principal com abas e menu
- **Download Tab**: Interface para inserir URL e configurações de download
- **Legendas Tab**: Galeria de estilos + preview em tempo real + editor visual
- **Cortes Tab**: Ferramentas para cortar e segmentar vídeos
- **Configurações**: Preferências do usuário e caminhos

#### 🧠 Core Engine
- **VideoDownloader**: Sistema de 7 estratégias com fallback automático
- **Transcriber**: Wrapper otimizado do Whisper (GPU/CPU)
- **SubtitleGenerator**: Gerador de arquivos ASS/SRT com estilos
- **VideoEditor**: Wrapper do FFmpeg para cortes e overlay
- **PreviewRenderer**: Renderizador de previews usando QImage

#### 💾 Data Layer
- **Model Cache**: Armazena modelos Whisper baixados
- **Estilos Database**: JSON com 12+ estilos de legendas
- **Videos Storage**: Armazenamento local de vídeos processados

#### 🔧 External Tools
- **yt-dlp**: Download de vídeos do YouTube
- **FFmpeg**: Processamento de vídeo (merge, corte, overlay)
- **FFprobe**: Validação de streams de áudio/vídeo
- **OpenAI Whisper**: Transcrição de áudio para texto

---

## 2. 🔄 Fluxo de Processamento Completo

### Sequência de Operações (URL → Vídeo Processado)

```mermaid
sequenceDiagram
    actor User
    participant UI as Interface
    participant DL as Downloader
    participant VAL as Validator
    participant TRANS as Transcriber
    participant LEG as SubtitleGen
    participant PREV as PreviewRender
    participant ED as VideoEditor
    
    User->>UI: 1. Cola URL + Seleciona Estilo
    UI->>PREV: 2. Renderiza Preview do Estilo
    PREV-->>UI: Preview PNG (50ms)
    
    User->>UI: 3. Clica "Processar"
    UI->>DL: 4. Download(url, quality)
    
    loop 7 Estratégias
        DL->>DL: Tenta estratégia N
        DL->>VAL: Valida com FFprobe
        alt Válido (áudio+vídeo)
            VAL-->>DL: ✅ OK
        else Inválido
            VAL-->>DL: ❌ Próxima
        end
    end
    
    DL-->>UI: 5. video.mp4 (validado)
    
    UI->>TRANS: 6. Transcribe(video, modelo)
    TRANS->>TRANS: Whisper GPU/CPU
    TRANS-->>UI: 7. Resultado (words + timestamps)
    
    UI->>LEG: 8. Generate(resultado, estilo)
    LEG->>LEG: Cria arquivo .ass
    LEG-->>UI: 9. legendas.ass
    
    UI->>ED: 10. BurnSubtitles(video, legendas)
    ED->>ED: FFmpeg merge
    ED-->>UI: 11. video_final.mp4
    
    UI-->>User: 12. ✅ Concluído! (+ Balloons)
```

### Descrição do Fluxo:

1. **Usuário cola URL**: Insere link do YouTube e escolhe estilo de legenda
2. **Preview instantâneo**: Sistema renderiza preview do estilo em <50ms
3. **Iniciar processamento**: Usuário clica no botão "Processar"
4. **Download robusto**: Sistema tenta 7 estratégias até conseguir
5. **Validação tripla**: FFprobe verifica áudio, vídeo e duração
6. **Transcrição IA**: Whisper gera texto com timestamps palavra-por-palavra
7. **Geração de legendas**: Cria arquivo ASS com estilo escolhido
8. **Queima de legendas**: FFmpeg incorpora legendas no vídeo
9. **Vídeo final**: Salvo no disco com legendas permanentes

**Tempo total**: <5 minutos para vídeo de 5 min (720p, modelo Base)

---

## 3. 🎨 Fluxo de Preview de Legendas

### Máquina de Estados do Sistema de Preview

```mermaid
stateDiagram-v2
    [*] --> IdlePreview
    IdlePreview --> RenderizandoPreview: User altera controle
    
    state RenderizandoPreview {
        [*] --> CriarCanvas
        CriarCanvas --> AplicarEstilo
        AplicarEstilo --> DesenharTexto
        DesenharTexto --> AplicarEfeitos
        AplicarEfeitos --> [*]
    }
    
    RenderizandoPreview --> CachePreview: Render completo
    CachePreview --> ExibirPreview: <50ms
    ExibirPreview --> IdlePreview: Aguarda nova mudança
    
    ExibirPreview --> SalvarScreenshot: User clica "Salvar"
    SalvarScreenshot --> [*]: PNG exportado
```

### Descrição dos Estados:

#### IdlePreview
- Sistema aguardando interação do usuário
- Preview atual exibido na tela
- CPU/GPU em idle

#### RenderizandoPreview
1. **CriarCanvas**: Cria QImage 1280x720
2. **AplicarEstilo**: Aplica fonte, cor, borda do estilo
3. **DesenharTexto**: Renderiza texto de exemplo
4. **AplicarEfeitos**: Adiciona sombra, outline, etc.

#### CachePreview
- Armazena render em cache para reutilização
- Key: `{estilo_id}_{hash(config)}`
- Evita re-render desnecessário

#### ExibirPreview
- Atualiza widget Qt com nova imagem
- Latência: <50ms (meta)
- Usuário vê mudança instantaneamente

#### SalvarScreenshot
- Exporta preview como PNG 1280x720
- Usado para compartilhamento/referência

---

## 4. 🔽 Sistema de Download Multi-Estratégia

### Fluxograma de Fallback

```mermaid
graph TD
    START([Usuário cola URL]) --> E1[Estratégia 1:<br/>yt-dlp Android]
    
    E1 --> V1{Validar<br/>FFprobe}
    V1 -->|✅ Áudio+Vídeo| SUCCESS([✅ Download OK])
    V1 -->|❌ Falha| E2[Estratégia 2:<br/>yt-dlp iOS]
    
    E2 --> V2{Validar<br/>FFprobe}
    V2 -->|✅ Áudio+Vídeo| SUCCESS
    V2 -->|❌ Falha| E3[Estratégia 3:<br/>yt-dlp Web]
    
    E3 --> V3{Validar<br/>FFprobe}
    V3 -->|✅ Áudio+Vídeo| SUCCESS
    V3 -->|❌ Falha| E4[Estratégia 4:<br/>yt-dlp Bypass]
    
    E4 --> V4{Validar<br/>FFprobe}
    V4 -->|✅ Áudio+Vídeo| SUCCESS
    V4 -->|❌ Falha| E5[Estratégia 5:<br/>yt-dlp Merge Manual]
    
    E5 --> V5{Validar<br/>FFprobe}
    V5 -->|✅ Áudio+Vídeo| SUCCESS
    V5 -->|❌ Falha| E6[Estratégia 6:<br/>PyTube Progressive]
    
    E6 --> V6{Validar<br/>FFprobe}
    V6 -->|✅ Áudio+Vídeo| SUCCESS
    V6 -->|❌ Falha| E7[Estratégia 7:<br/>FFmpeg Manual Merge]
    
    E7 --> V7{Validar<br/>FFprobe}
    V7 -->|✅ Áudio+Vídeo| SUCCESS
    V7 -->|❌ Falha| FAIL([❌ Todas falharam])
    
    style START fill:#667eea,stroke:#333,color:#fff
    style SUCCESS fill:#43e97b,stroke:#333,color:#000
    style FAIL fill:#f093fb,stroke:#333,color:#fff
    style E1 fill:#4facfe,stroke:#333,color:#000
    style E2 fill:#4facfe,stroke:#333,color:#000
    style E3 fill:#4facfe,stroke:#333,color:#000
    style E4 fill:#4facfe,stroke:#333,color:#000
    style E5 fill:#4facfe,stroke:#333,color:#000
    style E6 fill:#4facfe,stroke:#333,color:#000
    style E7 fill:#4facfe,stroke:#333,color:#000
```

### Validação FFprobe (Cada Estratégia)

```mermaid
flowchart LR
    A[Arquivo baixado] --> B{Existe?}
    B -->|Não| FAIL[❌ Falha]
    B -->|Sim| C{Tamanho > 1MB?}
    C -->|Não| FAIL
    C -->|Sim| D{Tem stream vídeo?}
    D -->|Não| FAIL
    D -->|Sim| E{Tem stream áudio?}
    E -->|Não| FAIL
    E -->|Sim| F{Duração > 0?}
    F -->|Não| FAIL
    F -->|Sim| G{Codecs compatíveis?}
    G -->|Não| FAIL
    G -->|Sim| OK[✅ Válido]
    
    style OK fill:#43e97b,stroke:#333,color:#000
    style FAIL fill:#f093fb,stroke:#333,color:#fff
```

---

## 5. 🎬 Pipeline de Processamento de Vídeo

### Visão Geral End-to-End

```mermaid
graph LR
    A[📥 URL YouTube] --> B[🔽 Download<br/>7 estratégias]
    B --> C[✅ Validação<br/>FFprobe]
    C --> D[🤖 Transcrição<br/>Whisper]
    D --> E[📝 Geração ASS<br/>Com estilo]
    E --> F[🔥 Queimar Legendas<br/>FFmpeg]
    F --> G[📁 Vídeo Final<br/>MP4]
    
    style A fill:#667eea,stroke:#333,color:#fff
    style B fill:#4facfe,stroke:#333,color:#000
    style C fill:#43e97b,stroke:#333,color:#000
    style D fill:#f093fb,stroke:#333,color:#fff
    style E fill:#667eea,stroke:#333,color:#fff
    style F fill:#4facfe,stroke:#333,color:#000
    style G fill:#43e97b,stroke:#333,color:#000
```

### Tempos Estimados (Vídeo 5min, 720p, modelo Base)

| Etapa | Tempo | Progresso |
|-------|-------|-----------|
| Download | 30-60s | 0-30% |
| Validação | 1-3s | 30-32% |
| Transcrição | 20-40s | 32-70% |
| Geração ASS | 0.5-1s | 70-72% |
| Queima Legendas | 60-120s | 72-100% |
| **TOTAL** | **2-4 min** | **100%** |

---

## 6. 🎨 Arquitetura do Editor Visual de Legendas

### Componentes da Interface de Edição

```mermaid
graph TB
    subgraph "Editor Visual de Legendas"
        A[Galeria de Estilos<br/>12 thumbnails]
        B[Canvas de Preview<br/>1280x720px]
        C[Painel de Controles<br/>Sliders + Pickers]
        D[Botões de Ação<br/>Salvar/Aplicar/Reset]
    end
    
    A -->|Seleciona estilo| E[PreviewRenderer]
    C -->|Altera config| E
    E -->|Renderiza<br/><50ms| B
    B -->|Screenshot| F[Exportar PNG]
    D -->|Aplicar| G[Gerar ASS]
    
    style A fill:#667eea,stroke:#333,color:#fff
    style B fill:#4facfe,stroke:#333,color:#000
    style C fill:#f093fb,stroke:#333,color:#fff
    style D fill:#43e97b,stroke:#333,color:#000
```

### Controles Disponíveis

```mermaid
mindmap
  root((Controles<br/>de Legenda))
    Tipografia
      Fonte
      Tamanho
      Negrito
      Itálico
      Espacamento
    Cores
      Cor Primária
      Cor Secundária
      Cor Borda
      Cor Fundo
    Efeitos
      Borda
        Espessura
        Cor
      Sombra
        Offset
        Blur
        Cor
    Posicionamento
      Vertical
        Topo
        Centro
        Embaixo
      Horizontal
        Esquerda
        Centro
        Direita
      Margens
        Superior
        Inferior
        Laterais
```

---

## 7. 🗄️ Modelo de Dados

### Estrutura da Classe EstiloLegenda

```mermaid
classDiagram
    class EstiloLegenda {
        +str id
        +str nome
        +str categoria
        +str fonte
        +int tamanho
        +bool bold
        +bool italic
        +str cor_primaria
        +str cor_secundaria
        +str cor_borda
        +str cor_fundo
        +int borda_espessura
        +int sombra_offset
        +int sombra_blur
        +int alignment
        +int margem_v
        +int margem_h
        +str tipo_exibicao
        +int palavras_por_linha
        +int duracao_minima_ms
        +str texto_exemplo
        +str imagem_preview
        +to_dict()
        +from_dict(dict)
        +to_ass_style()
    }
    
    class EstilosDatabase {
        +dict estilos
        +load_from_json()
        +save_to_json()
        +add_style(EstiloLegenda)
        +remove_style(str)
        +get_style(str)
        +list_by_category(str)
    }
    
    class PreviewRenderer {
        +dict cache
        +tuple canvas_size
        +renderizar(EstiloLegenda)
        +salvar_preview(EstiloLegenda, str)
        +limpar_cache()
    }
    
    EstilosDatabase "1" --> "*" EstiloLegenda : gerencia
    PreviewRenderer ..> EstiloLegenda : renderiza
```

---

## 8. 🚀 Fluxo de Inicialização do Aplicativo

### Sequência de Startup

```mermaid
sequenceDiagram
    participant Main
    participant App
    participant UI
    participant Config
    participant Cache
    participant DB
    
    Main->>App: Iniciar aplicação
    App->>Config: Carregar settings.json
    Config-->>App: Configurações
    
    App->>DB: Carregar estilos_padrao.json
    DB-->>App: 12 estilos
    
    App->>Cache: Verificar modelos Whisper
    alt Modelos não baixados
        Cache->>Cache: Baixar modelo 'base'
    end
    Cache-->>App: Cache OK
    
    App->>UI: Criar MainWindow
    UI->>UI: Aplicar dark_theme.qss
    UI->>UI: Inicializar widgets
    UI->>UI: Carregar previews de estilos
    UI-->>App: UI pronta
    
    App->>Main: Mostrar janela
    Main->>Main: app.exec()
```

---

## 9. 📊 Monitoramento de Performance

### Dashboard de Métricas

```mermaid
graph TD
    A[Performance Monitor] --> B[Download Stats]
    A --> C[Transcription Stats]
    A --> D[Render Stats]
    
    B --> B1[Tempo médio]
    B --> B2[Taxa de sucesso]
    B --> B3[Estratégias usadas]
    
    C --> C1[Tempo por modelo]
    C --> C2[GPU vs CPU]
    C --> C3[Palavras/segundo]
    
    D --> D1[FPS preview]
    D --> D2[Latência render]
    D --> D3[Cache hits]
    
    style A fill:#667eea,stroke:#333,color:#fff
    style B fill:#4facfe,stroke:#333,color:#000
    style C fill:#f093fb,stroke:#333,color:#fff
    style D fill:#43e97b,stroke:#333,color:#000
```

---

## 10. 🔐 Fluxo de Tratamento de Erros

### Sistema de Fallback e Recovery

```mermaid
flowchart TD
    START([Erro detectado]) --> TYPE{Tipo de erro?}
    
    TYPE -->|Download falhou| DL[Próxima estratégia]
    TYPE -->|FFprobe falhou| VAL[Reportar problema<br/>Prosseguir com aviso]
    TYPE -->|Whisper falhou| TRANS[Tentar modelo menor]
    TYPE -->|FFmpeg falhou| FF[Verificar codecs<br/>Tentar fallback]
    
    DL --> DL_CHECK{Há próxima<br/>estratégia?}
    DL_CHECK -->|Sim| DL_NEXT[Executar próxima]
    DL_CHECK -->|Não| FAIL
    DL_NEXT --> SUCCESS{Sucesso?}
    SUCCESS -->|Sim| OK
    SUCCESS -->|Não| DL
    
    TRANS --> TRANS_CHECK{Há modelo<br/>menor?}
    TRANS_CHECK -->|Sim| TRANS_TRY[Tentar tiny/base]
    TRANS_CHECK -->|Não| FAIL
    TRANS_TRY --> SUCCESS
    
    FF --> FF_CHECK{Tentou<br/>fallback?}
    FF_CHECK -->|Não| FF_ALT[Usar codecs alternativos]
    FF_CHECK -->|Sim| FAIL
    FF_ALT --> SUCCESS
    
    VAL --> OK
    
    OK([✅ Continuar])
    FAIL([❌ Mostrar erro<br/>ao usuário])
    
    style START fill:#f093fb,stroke:#333,color:#fff
    style OK fill:#43e97b,stroke:#333,color:#000
    style FAIL fill:#ff6b6b,stroke:#333,color:#fff
```

---

## 11. 🎯 Ciclo de Vida do Processamento

### Estados do Job de Processamento

```mermaid
stateDiagram-v2
    [*] --> Criado
    Criado --> EmFila: Adicionar à fila
    EmFila --> Baixando: Iniciar download
    
    Baixando --> ValidandoDownload: Download completo
    ValidandoDownload --> Transcrevendo: Validação OK
    ValidandoDownload --> Baixando: Falhou, próxima estratégia
    ValidandoDownload --> Falhou: Todas estratégias falharam
    
    Transcrevendo --> GerandoLegendas: Transcrição completa
    Transcrevendo --> Falhou: Erro Whisper
    
    GerandoLegendas --> QueimandoLegendas: ASS gerado
    GerandoLegendas --> Falhou: Erro geração
    
    QueimandoLegendas --> Finalizado: FFmpeg OK
    QueimandoLegendas --> Falhou: Erro FFmpeg
    
    Finalizado --> [*]
    Falhou --> [*]
    
    note right of Baixando
        7 tentativas
        com validação
    end note
    
    note right of Transcrevendo
        Whisper com
        word timestamps
    end note
    
    note right of QueimandoLegendas
        FFmpeg com
        filtro subtitles
    end note
```

---

## 12. 🎨 Sistema de Cache Multi-Nível

### Hierarquia de Cache

```mermaid
graph TD
    A[Cache Manager] --> B[Nível 1: Memória RAM]
    A --> C[Nível 2: Disco SSD]
    A --> D[Nível 3: Rede CDN]
    
    B --> B1[Previews renderizados]
    B --> B2[Estilos carregados]
    B --> B3[Último job]
    
    C --> C1[Modelos Whisper]
    C --> C2[Vídeos baixados]
    C --> C3[Arquivos ASS]
    
    D --> D1[Modelos novos]
    D --> D2[Atualizações]
    
    style A fill:#667eea,stroke:#333,color:#fff
    style B fill:#43e97b,stroke:#333,color:#000
    style C fill:#4facfe,stroke:#333,color:#000
    style D fill:#f093fb,stroke:#333,color:#fff
```

### Política de Evicção

| Tipo | TTL | Max Size | Evicção |
|------|-----|----------|---------|
| Previews RAM | 1 hora | 100 MB | LRU |
| Modelos Whisper | Infinito | 5 GB | Manual |
| Vídeos baixados | 7 dias | 20 GB | FIFO |
| Arquivos ASS | 30 dias | 500 MB | LRU |

---

## 13. 🔄 Integração com Ferramentas Externas

### Comunicação com FFmpeg

```mermaid
sequenceDiagram
    participant App
    participant Wrapper
    participant FFmpeg
    participant File
    
    App->>Wrapper: burn_subtitles(video, subs)
    Wrapper->>Wrapper: Validar inputs
    Wrapper->>FFmpeg: ffmpeg -i video.mp4<br/>-vf subtitles=subs.ass<br/>-c:a copy output.mp4
    
    loop Processamento
        FFmpeg->>Wrapper: Progress update
        Wrapper->>App: Atualizar barra (%)
    end
    
    FFmpeg->>File: Escrever output.mp4
    File-->>FFmpeg: OK
    FFmpeg-->>Wrapper: Código de saída 0
    Wrapper->>Wrapper: Validar output
    Wrapper-->>App: ✅ Sucesso + caminho
```

---

## 14. 📱 Exportação Multi-Formato

### Fluxo de Exportação

```mermaid
graph TD
    A[Vídeo + Legendas] --> B{Formato<br/>de saída?}
    
    B -->|MP4 Hard-coded| C[FFmpeg burn]
    B -->|MP4 + ASS externo| D[Copiar arquivos]
    B -->|WebM| E[FFmpeg convert]
    B -->|GIF| F[FFmpeg extract frames]
    
    C --> G[Validar output]
    D --> G
    E --> G
    F --> G
    
    G --> H{Válido?}
    H -->|Sim| I[✅ Salvar em pasta]
    H -->|Não| J[❌ Reportar erro]
    
    I --> K[Notificar usuário]
    J --> K
    
    style A fill:#667eea,stroke:#333,color:#fff
    style I fill:#43e97b,stroke:#333,color:#000
    style J fill:#ff6b6b,stroke:#333,color:#fff
```

---

## 15. 🎯 Resumo Visual da Arquitetura

### Big Picture

```mermaid
graph TB
    subgraph "Frontend"
        UI[PyQt6 Interface]
    end
    
    subgraph "Backend"
        CORE[Core Engine]
        DATA[Data Layer]
    end
    
    subgraph "External"
        YT[YouTube]
        WHISPER[Whisper AI]
        FFMPEG[FFmpeg]
    end
    
    UI <-->|Commands/Events| CORE
    CORE <-->|Persist/Retrieve| DATA
    CORE <-->|Download| YT
    CORE <-->|Transcribe| WHISPER
    CORE <-->|Process| FFMPEG
    
    style UI fill:#667eea,stroke:#333,color:#fff,stroke-width:4px
    style CORE fill:#f093fb,stroke:#333,color:#fff,stroke-width:4px
    style DATA fill:#4facfe,stroke:#333,color:#000,stroke-width:4px
    style YT fill:#43e97b,stroke:#333,color:#000
    style WHISPER fill:#43e97b,stroke:#333,color:#000
    style FFMPEG fill:#43e97b,stroke:#333,color:#000
```

---

## 16. 📈 Roadmap Visual

### Timeline de Desenvolvimento

```mermaid
gantt
    title Roadmap DarkAgent Pro v2.0
    dateFormat YYYY-MM-DD
    section Fase 1: Setup
    Estrutura de pastas     :done, f1a, 2025-01-01, 2d
    Interface PyQt6 básica  :active, f1b, after f1a, 7d
    Sistema download        :f1c, after f1b, 7d
    
    section Fase 2: Legendas
    EstiloLegenda dataclass :f2a, after f1c, 3d
    12 estilos padrão       :f2b, after f2a, 5d
    Preview Renderer        :f2c, after f2b, 7d
    
    section Fase 3: UI Avançada
    Preview em tempo real   :f3a, after f2c, 7d
    Editor visual           :f3b, after f3a, 7d
    Captura screenshots     :f3c, after f3b, 3d
    
    section Fase 4: Performance
    Otimização transcrição  :f4a, after f3c, 5d
    FFmpeg paralelo         :f4b, after f4a, 5d
    Sistema de cache        :f4c, after f4b, 5d
    
    section Fase 5: Extras
    Cortes automáticos      :f5a, after f4c, 7d
    Logo overlay            :f5b, after f5a, 5d
    Exportar/importar       :f5c, after f5b, 3d
```

---

## Conclusão

Estes diagramas representam a arquitetura completa do **DarkAgent Pro v2.0**, cobrindo:

✅ **Arquitetura de componentes** (camadas UI/Core/Data/External)  
✅ **Fluxos de processamento** (download, transcrição, preview)  
✅ **Máquinas de estado** (preview, jobs, erros)  
✅ **Integração com ferramentas** (FFmpeg, Whisper, yt-dlp)  
✅ **Sistema de cache** (memória, disco, rede)  
✅ **Roadmap de desenvolvimento** (5 fases, 10 semanas)

---

**Como usar estes diagramas:**

1. **Desenvolvedores**: Use como referência durante implementação
2. **Arquitetos**: Valide decisões de design e integrações
3. **Gerentes**: Acompanhe progresso e dependências entre fases
4. **Documentação**: Incorpore em wikis e READMEs

**Ferramentas para renderizar:**

- **VS Code**: Extensão "Markdown Preview Mermaid Support"
- **GitHub/GitLab**: Suporte nativo para blocos ```mermaid```
- **Mermaid Live Editor**: https://mermaid.live/
- **Obsidian**: Renderização automática de Mermaid

---

**Versão:** 2.0  
**Data de Criação:** 12/11/2025  
**Última Atualização:** 12/11/2025  
**Autor:** Guilherme (DarkAgent Pro)

---

📧 **Contato:** suporte@darkagent.pro  
🌐 **Website:** https://darkagent.pro  
💬 **Discord:** https://discord.gg/darkagent
