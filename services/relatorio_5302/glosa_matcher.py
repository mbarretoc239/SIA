import streamlit as st

@st.cache_data(ttl=300)
def carregar_mapa_glosas():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        rows = db._get("glosas_padrao?select=codigo,descricao")
        for r in rows:
            codigo = str(r.get('codigo', '')).strip()
            descricao = str(r.get('descricao', '')).strip()
            if codigo:
                mapa[codigo] = descricao
    except Exception:
        pass
    # Merge com customizadas (override)
    try:
        for gb in db.carregar_glosas_customizadas():
            mapa[str(gb['codigo_glosa']).strip()] = str(gb['descricao']).strip()
    except Exception:
        pass
    return mapa

@st.cache_data(ttl=300)
def carregar_mapa_tipos_glosa():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        rows = db._get("glosas_padrao?select=codigo,tipo_glosa")
        for r in rows:
            codigo = str(r.get('codigo', '')).strip()
            tipo = str(r.get('tipo_glosa', '')).strip()
            if codigo and tipo:
                mapa[codigo] = tipo
    except Exception:
        pass
    # Merge com customizadas (override)
    try:
        for gb in db.carregar_glosas_customizadas():
            tipo = str(gb.get('tipo', '')).strip()
            if tipo:
                mapa[str(gb['codigo_glosa']).strip()] = tipo
    except Exception:
        pass
    return mapa

@st.cache_data(ttl=300)
def carregar_mapa_procedimentos():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        rows = db._get("tabela_procedimentos?select=codigo_tuss,descricao")
        for r in rows:
            codigo = str(r.get('codigo_tuss', '')).strip()
            descricao = str(r.get('descricao', '')).strip()
            if codigo:
                mapa[codigo] = descricao
    except Exception:
        pass
    return mapa

@st.cache_data(ttl=60)
def carregar_glosas_criticas():
    criticas = {'438', '450', '463', '480'} # Fallback mínimo
    
    try:
        from shared.database import DatabaseManager
        db = DatabaseManager()
        glosas_banco = db.carregar_glosas_customizadas()
        for gb in glosas_banco:
            cod = str(gb['codigo_glosa']).strip()
            if gb.get('is_critica'):
                criticas.add(cod)
            else:
                if cod in criticas:
                    criticas.remove(cod)
    except Exception:
        pass
        
    return criticas

@st.cache_data(ttl=300)
def carregar_mapa_subglosas():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        # Carrega da tabela padrao
        rows = db._get("glosas_padrao?select=codigo,sub_glosa,descricao_sub_glosa&sub_glosa=neq.")
        for r in rows:
            cod = str(r.get('codigo', '')).strip()
            sub = str(r.get('sub_glosa', '')).strip()
            desc = str(r.get('descricao_sub_glosa', '')).strip()
            if cod and sub and desc:
                mapa[(cod, sub)] = desc
                
        # Integra o Módulo Híbrido: Carrega customizadas cadastradas pelo usuário
        custom = db.carregar_glosas_customizadas()
        for c in custom:
            cod_full = str(c.get('codigo_glosa', '')).strip()
            if '.' in cod_full:
                parts = cod_full.split('.')
                cod = parts[0]
                sub = parts[1]
                desc = str(c.get('descricao', '')).strip()
                if cod and sub and desc:
                    mapa[(cod, sub)] = desc
    except Exception:
        pass
    return mapa
