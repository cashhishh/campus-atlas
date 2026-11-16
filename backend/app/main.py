from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .api.routes import router

app = FastAPI(title='CampusAtlas API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(router, prefix='/api')

@app.on_event('startup')
def startup(): init_db()

@app.get('/health')
def health(): return {'status': 'ok', 'product': 'CampusAtlas'}
