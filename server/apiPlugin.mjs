import { generateWebResearch } from './groqService.mjs';

const MAX_BODY_BYTES = 40_000;
const send = (res, status, data) => { res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; if (body.length > MAX_BODY_BYTES) reject(new Error('Request too large')); });
    req.on('end', () => { try { resolve(JSON.parse(body || '{}')); } catch { reject(new Error('Invalid JSON')); } });
    req.on('error', reject);
  });
}

function validContext(value) {
  if (!Array.isArray(value) || value.length > 5) return false;
  return value.every(item => typeof item?.content === 'string' && item.content.length <= 1_600 && typeof item?.sourceName === 'string' && typeof item?.sourceUrl === 'string' && typeof item?.authorityLevel === 'string');
}

function uniqueSources(context) {
  const seen = new Set();
  return context
    .filter(({ sourceUrl }) => !seen.has(sourceUrl) && seen.add(sourceUrl))
    .map(({ sourceName, sourceUrl, authorityLevel }) => ({ sourceName, sourceUrl, authorityLevel }));
}

export function campusAtlasApi({ apiKey, model }) {
  return {
    name: 'campusatlas-groq-api',
    configureServer(server) {
      server.middlewares.use('/api/web-research', async (req, res, next) => {
        if (req.method !== 'POST') return next();
        try {
          const payload = await readJson(req);
          if (typeof payload.question !== 'string' || payload.question.length > 500 || !validContext(payload.context || [])) return send(res, 400, { error: 'A valid research question is required.' });
          const result = await generateWebResearch({ apiKey, model, question: payload.question.trim(), context: payload.context || [] });
          send(res, 200, { answer: result.answer, sources: uniqueSources(result.sources), mode: 'live' });
        } catch (error) {
          console.error(`[CampusAtlas] Groq request failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
          send(res, 503, { error: 'AI service unavailable' });
        }
      });
    },
  };
}
