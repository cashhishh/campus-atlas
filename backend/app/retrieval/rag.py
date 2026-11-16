from ..services.vector_store import query


def answer(question, college_ids=None, intent="general"):
    hits = query(question, college_ids)
    context = "\n\n".join(x["text"] for x in hits[:5])
    if not hits:
        return {"answer": "I couldn't find sufficient information in the currently indexed sources.", "sources": [], "mode": "demo"}
    seen, sources = set(), []
    for hit in hits:
        metadata = hit["metadata"]
        source_id = metadata["source_id"]
        if source_id not in seen:
            sources.append({key: metadata[key] for key in ("source_id", "source_name", "source_url", "authority_level", "source_type")})
            seen.add(source_id)
    return {"answer": "Based on the indexed material: " + context[:850], "sources": sources, "mode": "demo"}
