import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
import {campusAtlasApi} from '../server/apiPlugin.mjs';

// /api/web-research is served by the Vite plugin (experimental Groq web research).
// Every other /api route is proxied to the FastAPI backend (source-grounded platform).
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,process.cwd(),'');
  const backend=env.CAMPUSATLAS_API_URL||'http://127.0.0.1:8000';
  return{
    plugins:[react(),campusAtlasApi({apiKey:env.GROQ_API_KEY,model:env.GROQ_WEB_MODEL||'groq/compound-mini'})],
    envDir:'..',
    server:{proxy:{'/api':{target:backend,changeOrigin:true},'/health':{target:backend,changeOrigin:true}}},
  }
})
