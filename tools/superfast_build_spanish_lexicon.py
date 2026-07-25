#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,random,re,subprocess,unicodedata,itertools
from collections import Counter
from dataclasses import dataclass,asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts'/'spanish-card-lexicon';OUT.mkdir(parents=True,exist_ok=True)
URL='https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt';FREQ=OUT/'es_50k.txt'
CHARS=re.compile(r'^[a-záéíóúüñ]+$',re.I);VOW=str.maketrans({'á':'a','é':'e','í':'i','ó':'o','ú':'u','ü':'u'})
DENY=set('mierda puta puto culo coño joder hostia carajo idiota estúpido estupido asesino asesinato matar muerto muerta arma armas sexo dólares dolares john jack sam york michael david george charlie tom mike joe frank madrid españa china francia alemania italia europa américa america'.split())
A1=set('hola gracias adiós adios favor casa familia madre padre hijo hija hermano hermana amigo amiga niño niña niños niñas hombre mujer persona gente nombre día dia noche mañana manana tarde hora tiempo semana mes año ano hoy agua café cafe comida pan vino leche carne pescado fruta mesa cama silla puerta ventana baño bano cocina calle ciudad pueblo escuela clase libro carta coche auto tren barco avión avion viaje hotel tienda ropa foto música musica sol luz aire tierra mar cielo fuego mano cabeza cara ojo ojos boca pie perro gato trabajo dinero mundo vida amor idea problema pregunta respuesta bueno buena malo mala grande pequeño pequena pequeña nuevo nueva viejo vieja bonito bonita fácil facil difícil dificil rápido rapido lento feliz triste caliente frío frio alto bajo blanco negro rojo verde azul ser estar tener hacer ir venir ver mirar hablar decir comer beber vivir trabajar estudiar leer escribir comprar pagar abrir cerrar entrar salir dormir jugar gustar querer poder saber conocer llamar llevar tomar dar poner buscar encontrar esperar ayudar necesitar pensar creer volver pasar usar caminar correr'.split())
A2=A1|set('oficina empresa negocio reunión reunion equipo servicio información informacion mensaje teléfono telefono programa sistema control situación situacion decisión decision derecho oportunidad seguridad accidente hospital médico medico doctor policía policia gobierno universidad profesor película pelicula fiesta cumpleaños cumpleanos boda vacaciones aeropuerto estación estacion dirección direccion camino centro campo playa montaña montana río rio bosque animal pájaro pajaro caballo vaca árbol arbol flor cuerpo corazón corazon sangre dolor salud hambre sueño sueno miedo suerte verdad razón razon historia realidad futuro pasado momento lugar forma parte cambio orden nivel grupo número numero línea linea punto ejemplo manera caso'.split())
ALPHABET='abcdefghijklmnopqrstuvwxyzñ'
@dataclass
class Entry: rank:int;word:str;count:int;hunspell:bool;letters:str;length:int;accented:bool;has_enye:bool;tier:str;reason:str

def assign(rank,w,c):
 if w in A1:return 'A1','manual_core'
 if w in A2:return 'A2','manual_core'
 if rank<=5000 and len(w)<=8 and c>=6000:return 'A1_REVIEW','frequency_proxy'
 if rank<=15000 and len(w)<=10 and c>=900:return 'A2_REVIEW','frequency_proxy'
 return 'EXCLUDE','outside_scope'

def signature(s):return ''.join(sorted(s))
def hunspell_valid(words):
 p=subprocess.run(['hunspell','-d','es_ES','-l'],input='\n'.join(words)+'\n',text=True,stdout=subprocess.PIPE,check=True)
 miss={x.strip().lower() for x in p.stdout.splitlines() if x.strip()};return set(words)-miss

def read_entries():
 subprocess.run(['curl','-fL','--retry','3','-o',str(FREQ),URL],check=True)
 rows=[];seen=set()
 for rank,line in enumerate(FREQ.open(encoding='utf-8'),1):
  p=line.rstrip().rsplit(' ',1)
  if len(p)!=2:continue
  w=unicodedata.normalize('NFC',p[0].lower())
  if w in seen or not 3<=len(w)<=11 or not CHARS.fullmatch(w) or w in DENY:continue
  seen.add(w);rows.append((rank,w,int(p[1])))
 valid=hunspell_valid([w for _,w,_ in rows]);out=[]
 for rank,w,c in rows:
  if w not in valid:continue
  t,r=assign(rank,w,c);letters=w.translate(VOW);out.append(Entry(rank,w,c,True,letters,len(letters),letters!=w,'ñ'in letters,t,r))
 return out

def apportion(entries,total=106):
 score=Counter()
 for e in entries:
  wt=math.sqrt(max(e.count,1))/max(3,e.length)
  for ch,n in Counter(e.letters).items():score[ch]+=wt*n
 order=list('aeosnrildtcumpbgvyhfjñqxzk');present=[c for c in order if score[c]>0];d={c:1 for c in present};left=total-len(d);s=sum(score.values());q={c:score[c]/s*left for c in present}
 for c in present:d[c]+=int(q[c])
 for c in sorted(present,key=lambda x:q[x]-int(q[x]),reverse=True)[:total-sum(d.values())]:d[c]+=1
 return {c.upper():n for c,n in d.items()}

def make_wordset(entries):return {signature(e.letters) for e in entries}
def canplay(hand,market,wordset):
 # New word: >=2 own cards, max 1 market card, total length 3..11.
 n=len(hand)
 for r in range(2,min(n,11)+1):
  for ix in itertools.combinations(range(n),r):
   own=''.join(hand[i] for i in ix)
   if r>=3 and signature(own) in wordset:return True
   if r<=10:
    for m in market:
     if signature(own+m) in wordset:return True
 return False

def metrics(entries,dist,trials=2000,seed=1):
 rng=random.Random(seed);deck=[c.lower() for c,n in dist.items() for _ in range(n)];wordset=make_wordset(entries);start=resc=0;dead=Counter()
 for _ in range(trials):
  rng.shuffle(deck);h=deck[:10];m=deck[10:15]
  if canplay(h,m,wordset):start+=1;continue
  found=False
  for gi,g in enumerate(h):
   for ti,t in enumerate(m):
    if g==t:continue
    h2=h.copy();m2=m.copy();h2[gi]=t;m2[ti]=g
    if canplay(h2,m2,wordset):found=True;break
   if found:break
  resc+=found
  if not found:dead.update(h)
 return {'trials':trials,'start_playable_rate':start/trials,'rescued_by_one_swap_rate':resc/trials,'unresolved_rate':1-(start+resc)/trials,'dead_hand_letters':dead.most_common()}

def candidate_distributions(initial):
 out=[('initial',initial)]
 donors=[c for c,_ in sorted(initial.items(),key=lambda x:x[1],reverse=True)[:7]]
 recipients=[c for c,_ in sorted(initial.items(),key=lambda x:x[1])[:9]]
 for d in donors:
  if initial[d]<=1:continue
  for r in recipients:
   if d==r:continue
   x=initial.copy();x[d]-=1;x[r]+=1;out.append((f'{d}->{r}',x))
 # Add vowel/consonant balance hypotheses.
 for d,r in [('A','E'),('E','A'),('O','I'),('S','R'),('N','L'),('R','D'),('A','Ñ'),('E','H')]:
  if d in initial and r in initial and initial[d]>1:
   x=initial.copy();x[d]-=1;x[r]+=1;out.append((f'hyp:{d}->{r}',x))
 uniq={tuple(sorted(x.items())):(name,x) for name,x in out};return list(uniq.values())
def optimize(entries):
 initial=apportion(entries);scored=[]
 for i,(name,d) in enumerate(candidate_distributions(initial)):
  m=metrics(entries,d,700,100+i);scored.append((m['unresolved_rate'],-m['start_playable_rate'],name,d,m))
 scored.sort(key=lambda x:(x[0],x[1]));top=scored[:5];validated=[]
 for i,x in enumerate(top):
  m=metrics(entries,x[3],8000,2026+i);validated.append((m['unresolved_rate'],-m['start_playable_rate'],x[2],x[3],m))
 validated.sort(key=lambda x:(x[0],x[1]));b=validated[0]
 return {'initial_distribution':initial,'optimized_distribution':b[3],'selected_candidate':b[2],'top_candidates':[{'name':x[2],'distribution':x[3],'screen_metrics':x[4]} for x in top],'final_metrics':b[4],'cards':sum(b[3].values())}
def write_csv(rows,path):
 fields=list(asdict(rows[0]));
 with path.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(asdict(x) for x in rows)
def main():
 entries=read_entries();write_csv(entries,OUT/'lexicon_audit.csv')
 a1core=[e for e in entries if e.tier=='A1'];a1review=sorted([e for e in entries if e.tier=='A1_REVIEW'],key=lambda e:e.rank);a1=sorted(a1core,key=lambda e:e.rank)+a1review[:650]
 a2core=[e for e in entries if e.tier in {'A1','A2'}];a2review=sorted([e for e in entries if e.tier in {'A1_REVIEW','A2_REVIEW'}],key=lambda e:e.rank);a2=sorted({e.word:e for e in a2core+a2review[:1800]}.values(),key=lambda e:e.rank)
 for rows,name in [(a1,'a1_playable.csv'),(a2,'a2_playable.csv'),(a1review,'a1_review_queue.csv'),(a2review,'a2_review_queue.csv')]:write_csv(rows,OUT/name)
 summary={'source_rows':sum(1 for _ in FREQ.open()),'hunspell_valid_filtered':len(entries),'a1_playable':len(a1),'a2_playable':len(a2),'a1':optimize(a1),'a2':optimize(a2),'policy':{'status':'candidate formal lexicons; review queues require human acceptance','source':'FrequencyWords es_50k + hunspell-es','length':'3-11','proper_names_and_offensive':'manual deny plus review queue','accents':'retained in word, stripped only for card signature','enye':'independent card'}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
