const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';

const WEB_SYSTEM_PROMPT = `You are CampusAtlas, a current college research assistant for India.
Use web search to answer the question. Prioritize official college websites, government portals, admission authorities, and official brochures/PDFs. Treat student-review sites only as clearly labelled experience reports, never as official fact.
For changing details such as fees, admissions, cutoffs, eligibility, placements, and dates, use current sources and mention when the cycle/year matters. Do not invent facts. If sources conflict or cannot verify a detail, say so.
Give a concise, directly useful answer in plain text. Do not use Markdown tables, Markdown bold markers, inline links, or a Sources heading.
After the answer, add exactly one final line in this format: SOURCE_URLS: url1 | url2 | url3. Include 2-5 URLs actually used for the answer, prioritising official sources.
Return only the final user-facing answer, never analysis, reasoning, planning, or <think> tags.`;

const SYSTEM_PROMPT = `You are CampusAtlas, a source-grounded college information assistant.

Answer ONLY using the supplied knowledge context.
Do not use outside knowledge.
Do not invent facts.
If the context does not contain enough information, clearly say that the information is not currently available in the indexed CampusAtlas sources.
Return only the final user-facing answer—never analysis, reasoning, planning, or <think> tags.
Be concise, accurate, and helpful.`;

function finalAnswer(content) {
  const value = String(content || '').trim();
  if (!value) throw new Error('Groq returned an empty answer');
  if (!value.includes('<think>')) return value;
  const cleaned = value.replace(/<think>[\s\S]*?<\/think>\s*/g, '').trim();
  if (!cleaned || cleaned === value) throw new Error('Groq returned reasoning without a final answer');
  return cleaned;
}

export async function generateGroundedAnswer({ apiKey, model, question, context }) {
  if (!apiKey) throw new Error('GROQ_API_KEY is not configured');
  const safeContext = context.slice(0, 5).map((item, index) => `SOURCE ${index + 1}: ${item.sourceName}\n${item.content}`).join('\n\n');
  const response = await fetch(GROQ_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model,
      temperature: 0.1,
      max_tokens: 500,
      reasoning_effort: 'none',
      reasoning_format: 'hidden',
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: `QUESTION:\n${question}\n\nINDEXED KNOWLEDGE CONTEXT:\n${safeContext}` },
      ],
    }),
  });
  if (!response.ok) {
    const detail = (await response.text()).replace(/\s+/g, ' ').slice(0, 240);
    throw new Error(`Groq request failed (${response.status}): ${detail}`);
  }
  const data = await response.json();
  return finalAnswer(data?.choices?.[0]?.message?.content);
}

function sourceFromUrl(url, title) {
  try { return { sourceName: title || new URL(url).hostname, sourceUrl: url, authorityLevel: 'WEB_SOURCE' }; } catch { return null; }
}

function webSources(message, content) {
  const seen = new Set();
  const results = (message?.executed_tools || []).flatMap(tool => tool.search_results || []);
  const toolSources = results.map(result => sourceFromUrl(result?.url, result?.title)).filter(Boolean);
  // Compound Mini may place its search trace in `reasoning` rather than `executed_tools`.
  // We extract URLs only; the reasoning itself is never returned to the browser.
  const inlineSources = [...`${String(content || '')}\n${String(message?.reasoning || '')}`.matchAll(/https?:\/\/[^\s|)\]]+/g)].map(match => sourceFromUrl(match[0]));
  return [...toolSources, ...inlineSources].filter(source => source && !seen.has(source.sourceUrl) && seen.add(source.sourceUrl)).slice(0, 8);
}

function cleanWebAnswer(content) {
  return finalAnswer(content)
    .replace(/\n?SOURCE_URLS:\s*[\s\S]*$/i, '')
    .replace(/\n\s*(?:#{1,6}\s*)?sources?\s*(?:used)?\s*\n[\s\S]*$/i, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '$1')
    .trim();
}

export async function generateWebResearch({ apiKey, model, question, context }) {
  if (!apiKey) throw new Error('GROQ_API_KEY is not configured');
  const localContext = context.length ? `\n\nLOCAL CAMPUSATLAS CONTEXT (use only if it agrees with current sources):\n${context.slice(0, 5).map(item => `${item.sourceName}: ${item.content}`).join('\n')}` : '';
  const response = await fetch(GROQ_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model,
      messages: [{ role: 'system', content: WEB_SYSTEM_PROMPT }, { role: 'user', content: `RESEARCH QUESTION:\n${question}${localContext}` }],
    }),
  });
  if (!response.ok) {
    const detail = (await response.text()).replace(/\s+/g, ' ').slice(0, 240);
    throw new Error(`Groq web research failed (${response.status}): ${detail}`);
  }
  const data = await response.json();
  const message = data?.choices?.[0]?.message;
  return { answer: cleanWebAnswer(message?.content), sources: webSources(message, message?.content) };
}
