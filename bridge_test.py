
import sys, json
from main import SistemaAuditoriaModular

try:
    app = SistemaAuditoriaModular()
    app.withdraw() # Hide window
    
    data = json.loads(sys.argv[1])
    app.frame_5302_offline.dados_extraidos_offline = data
    
    # Generate Completo
    completo = app.frame_5302_offline._gerar_texto_completo_offline() if hasattr(app.frame_5302_offline, '_gerar_texto_completo_offline') else 'N/A'
    
    print(json.dumps({'completo': completo}))
except Exception as e:
    import traceback
    print(json.dumps({'error': str(e), 'trace': traceback.format_exc()}))
finally:
    try:
        app.destroy()
    except: pass
