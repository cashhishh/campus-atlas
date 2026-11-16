def recommend(colleges, p):
 branch=(p.get('branch') or '').lower(); loc=(p.get('location') or '').lower(); pref=p.get('type') or ''
 out=[]
 for c in colleges:
  score=0; why=[]
  if branch: score+=30;why.append('Program fit needs confirmation from indexed academic sources')
  if loc and (loc in c.state.lower() or loc in c.city.lower()): score+=20;why.append('Located in your preferred area')
  if pref and (pref.lower() in c.category.lower() or (pref=='Government' and c.category!='Private')):score+=15;why.append('Matches your institution preference')
  if p.get('hostel'):score+=10;why.append('Hostel preference recorded; availability requires source verification')
  if p.get('placement'):score+=5;why.append('Placement importance included in scoring')
  out.append({'college':c,'score':score,'why':why or ['A registry match; more sources will improve recommendations']})
 return sorted(out,key=lambda x:x['score'],reverse=True)[:8]
