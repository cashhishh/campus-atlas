import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';

// Every /api route (incl. experimental /api/web-research, now Gemini + Google Search) is proxied to FastAPI.
// server/apiPlugin.mjs (first-defence Groq Compound web research) is kept in the repo but no longer mounted.
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,process.cwd(),'');
  const backend=env.CAMPUSATLAS_API_URL||'http://127.0.0.1:8000';
  return{
    plugins:[react()],
    envDir:'..',
    server:{proxy:{'/api':{target:backend,changeOrigin:true},'/health':{target:backend,changeOrigin:true}}},
  }
})
