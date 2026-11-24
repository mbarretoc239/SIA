"""Catálogo das 56 medidas da Lupita: rótulo e frases em português.

Gerado a partir das tabelas FEATURES e GROUPS do nucleo.js do artefato do navegador (fonte única
das frases usadas na tela de resultado). Não editar à mão sem conferir com o artefato.
"""

# (chave, grupo, rótulo, frase se valor baixo, frase se valor alto, casas decimais)
FEATURES = [
    ('fSlope', 'freq', 'Inclinação do espectro', 'o detalhe fino cai rápido (aspecto suave)', 'o espectro é mais plano, com mais detalhe fino', 2),
    ('fHM', 'freq', 'Energia em frequências altas', 'pouca energia nas frequências altas', 'muita energia nas frequências altas (nitidez ou ruído)', 2),
    ('fML', 'freq', 'Detalhe médio vs. formas grandes', 'pouco detalhe médio frente às formas grandes', 'muito detalhe médio frente às formas grandes', 2),
    ('fTail', 'freq', 'Limite de frequência', 'queda abrupta no limite de frequência (reamostragem ou suavização)', 'sobra de energia no limite de frequência (nitidez ou artefato)', 2),
    ('fPeak', 'freq', 'Picos periódicos no espectro', 'sem picos periódicos', 'picos periódicos em forma de grade (típico de ampliação por IA)', 2),
    ('fAniso', 'freq', 'Direção da energia', 'energia espalhada também nas diagonais', 'energia concentrada nos eixos horizontal e vertical', 2),
    ('nStd', 'noise', 'Ruído fino', 'ruído fino muito baixo (imagem muito limpa)', 'bastante ruído fino (granulação)', 2),
    ('nKurt', 'noise', 'Forma do ruído', 'ruído de distribuição suave', 'resíduo dominado por poucos pontos fortes, não por ruído uniforme', 2),
    ('nQ10', 'noise', 'Ruído nas áreas lisas', 'áreas lisas quase sem ruído', 'mesmo as áreas lisas têm ruído', 2),
    ('nSpread', 'noise', 'Desigualdade do ruído', 'ruído uniforme pela imagem toda', 'ruído muito desigual entre regiões', 2),
    ('nSig', 'noise', 'Ruído e brilho', 'o ruído não cresce com o brilho', 'o ruído cresce com o brilho (como em sensores de câmera)', 2),
    ('nCC', 'noise', 'Ruído entre canais de cor', 'ruído independente entre os canais de cor', 'ruído correlacionado entre canais de cor (como em câmeras)', 2),
    ('gMean', 'edges', 'Quantidade de bordas', 'poucas bordas, transições suaves', 'muitas bordas e contrastes locais', 2),
    ('gRatio', 'edges', 'Bordas vs. áreas planas', 'bordas e áreas planas com nitidez parecida', 'contraste enorme entre bordas nítidas e áreas lisas', 2),
    ('gSharp', 'edges', 'Bordas muito duras', 'quase nenhuma borda muito dura', 'muitas bordas muito duras e nítidas', 2),
    ('gOrient', 'edges', 'Direção das bordas', 'bordas em poucas direções', 'bordas em todas as direções', 2),
    ('tLBP', 'texture', 'Variedade de microtextura', 'microtextura simples ou repetitiva', 'microtextura variada e complexa', 2),
    ('tVarCV', 'texture', 'Textura entre regiões', 'textura homogênea entre regiões', 'regiões muito diferentes em textura', 2),
    ('tSmooth', 'texture', 'Áreas lisas', 'poucas áreas lisas', 'muitas áreas lisas, sem textura', 2),
    ('tEnt', 'texture', 'Variedade de tons', 'poucos tons de cinza em uso', 'uso amplo e variado de tons', 2),
    ('mBlock', 'compress', 'Blocos JPEG 8×8', 'sem marca de blocos JPEG', 'marca de compressão JPEG em blocos 8×8', 2),
    ('mEmpty', 'compress', 'Lacunas no histograma', 'histograma de tons contínuo', 'faltam tons no histograma (edição ou ajuste de contraste)', 3),
    ('cSat', 'color', 'Saturação média', 'cores pouco saturadas', 'cores muito saturadas', 2),
    ('cSatSd', 'color', 'Variação da saturação', 'saturação uniforme', 'saturação muito variável', 2),
    ('cColorful', 'color', 'Variedade de cor', 'pouca variedade de cor', 'grande variedade de cor', 2),
    ('cDark', 'color', 'Pretos puros', 'poucos pixels totalmente pretos', 'muitos pixels totalmente pretos', 2),
    ('cBright', 'color', 'Brancos estourados', 'poucos pixels estourados', 'muitos pixels estourados', 2),
    ('cContrast', 'color', 'Contraste global', 'contraste global baixo', 'contraste global alto', 2),
    ('cMean', 'color', 'Brilho médio', 'imagem escura', 'imagem clara', 2),
    ('cChanCorr', 'color', 'Correlação entre canais', 'canais de cor pouco correlacionados', 'canais de cor muito correlacionados (quase monocromática)', 2),
    ('rColorDev', 'radio', 'Desvio do cinza', 'imagem em escala de cinza pura', 'há matiz de cor, não é escala de cinza pura', 2),
    ('rP5', 'radio', 'Tom dos pretos', 'pretos profundos', 'pretos levantados (fundo acinzentado)', 2),
    ('rP50', 'radio', 'Intensidade mediana', 'imagem geral escura', 'imagem geral clara', 2),
    ('rP95', 'radio', 'Tom dos brancos', 'brancos contidos', 'brancos intensos', 2),
    ('rRange', 'radio', 'Faixa de intensidade', 'faixa estreita de tons (pouco contraste)', 'faixa ampla de tons (alto contraste)', 2),
    ('rExtremes', 'radio', 'Pixels quase pretos ou brancos', 'poucos pixels nos extremos', 'muitos pixels nos extremos (aspecto preto e branco)', 3),
    ('rFracDark', 'radio', 'Área de baixa densidade', 'pouca área escura', 'muita área escura (tecido mole, ar ou lesão)', 2),
    ('rFracMid', 'radio', 'Área de densidade média', 'pouca área de densidade média (osso)', 'muita área de densidade média (osso)', 2),
    ('rFracBright', 'radio', 'Área de alta densidade', 'pouca área de alta densidade (dentes e restaurações)', 'muita área de alta densidade (dentes e restaurações)', 2),
    ('rToothBone', 'radio', 'Contraste dente-osso', 'dente e osso com densidade parecida', 'dente muito mais denso que o osso', 2),
    ('rNComp', 'radio', 'Dentes separados (estimativa)', 'poucas estruturas densas alongadas', 'muitas estruturas densas alongadas separadas', 1),
    ('rAreaMax', 'radio', 'Maior estrutura densa', 'maior estrutura densa pequena', 'maior estrutura densa grande', 3),
    ('rElong', 'radio', 'Alongamento dos dentes', 'estruturas densas pouco alongadas', 'estruturas densas muito alongadas', 2),
    ('rWidth', 'radio', 'Largura dos dentes (relativa)', 'dentes estreitos', 'dentes largos', 3),
    ('rLength', 'radio', 'Comprimento dos dentes (relativo)', 'dentes curtos', 'dentes longos', 3),
    ('rTilt', 'radio', 'Inclinação do eixo dos dentes', 'dentes quase verticais', 'dentes mais inclinados', 2),
    ('rTiltSd', 'radio', 'Dispersão da inclinação', 'dentes muito paralelos entre si', 'dentes com inclinações variadas', 2),
    ('rRootSplit', 'radio', 'Divisão em pontas (raízes, estimativa)', 'estruturas inteiras, sem divisão', 'estruturas que se dividem em mais de uma ponta', 2),
    ('aLogMP', 'file', 'Megapixels', 'poucos megapixels', 'muitos megapixels', 2),
    ('aAspect', 'file', 'Proporção da imagem', 'formato mais alto que largo', 'formato mais largo que alto', 2),
    ('aDiv64', 'file', 'Dimensões múltiplas de 64', 'dimensões comuns de câmera ou web', 'largura e altura múltiplas de 64 (comum em geradores)', 0),
    ('aBpp', 'file', 'Peso do arquivo por pixel', 'arquivo leve para o número de pixels', 'arquivo pesado para o número de pixels', 2),
    ('aIsPng', 'file', 'Formato PNG', 'não é PNG', 'é PNG', 0),
    ('aIsJpeg', 'file', 'Formato JPEG', 'não é JPEG', 'é JPEG', 0),
    ('aExifCam', 'file', 'EXIF de câmera', 'sem marca ou modelo de câmera', 'com marca e modelo de câmera no EXIF', 0),
    ('aAiMeta', 'file', 'Rastro de IA nos metadados', 'sem rastro de IA nos metadados', 'metadados citam ferramenta de IA', 0),
]

# id -> (nome, descrição, ligado por padrão no artefato)
GRUPOS_INFO = {
    'freq': ('Frequências', 'Como o detalhe fino se distribui no espectro', True),
    'noise': ('Ruído', 'Granulação residual e como ela varia pela imagem', True),
    'edges': ('Bordas', 'Nitidez e direção dos contornos', True),
    'texture': ('Textura', 'Microtextura e áreas lisas', True),
    'compress': ('Compressão', 'Blocos JPEG e continuidade do histograma', False),
    'color': ('Cor', 'Saturação, contraste e tons extremos', False),
    'radio': ('Radiografia', 'Intensidade, densidade, tamanho, inclinação e divisão dos dentes (estimativas por processamento de imagem)', True),
    'file': ('Arquivo', 'Formato, tamanho e metadados (podem enviesar o modelo)', False),
}

FEAT = {f[0]: {'grupo': f[1], 'rotulo': f[2], 'baixo': f[3], 'alto': f[4], 'casas': f[5]} for f in FEATURES}
