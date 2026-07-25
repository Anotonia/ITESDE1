#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,re,subprocess,unicodedata,random
from collections import Counter
from dataclasses import dataclass,asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'artifacts'/'spanish-card-lexicon'; OUT.mkdir(parents=True,exist_ok=True)
URL='https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt'; FREQ=OUT/'es_50k.txt'
DENY={'mierda','puta','puto','culo','coño','joder','hostia','carajo','idiota','estúpido','estupido','asesino','asesinato','matar','muerto','muerta','arma','armas','sexo','dólares','dolares','john','jack','sam','york','michael','david','george','charlie','tom','mike','joe','frank','madrid','españa','china','francia','alemania','italia','europa','américa','america'}
CHARS=re.compile(r'^[a-záéíóúüñ]+$',re.I)
A1=set('hola gracias adiós adios favor casa familia madre padre hijo hija hermano hermana amigo amiga niño niña niños niñas hombre mujer persona gente nombre día dia noche mañana manana tarde hora tiempo semana mes año ano hoy agua café cafe comida pan vino leche carne pescado fruta mesa cama silla puerta ventana baño bano cocina calle ciudad pueblo escuela clase libro carta coche auto tren barco avión avion viaje hotel tienda ropa foto música musica sol luz aire tierra mar cielo fuego mano cabeza cara ojo ojos boca pie perro gato trabajo dinero mundo vida amor idea problema pregunta respuesta bueno buena malo mala grande pequeño pequena pequeña nuevo nueva viejo vieja bonito bonita fácil facil difícil dificil rápido rapido lento feliz triste caliente frío frio alto bajo blanco negro rojo verde azul ser estar tener hacer ir venir ver mirar hablar decir comer beber vivir trabajar estudiar leer escribir comprar pagar abrir cerrar entrar salir dormir jugar gustar querer poder saber conocer llamar llevar tomar dar poner buscar encontrar esperar ayudar necesitar pensar creer volver pasar usar caminar correr'.split())
A2=A1|set('oficina empresa negocio reunión reunion equipo servicio información informacion mensaje teléfono telefono programa sistema control situación situacion decisión decision derecho oportunidad seguridad accidente hospital médico medico doctor policía policia gobierno universidad profesor película pelicula fiesta cumpleaños cumpleanos boda vacaciones aeropuerto estación estacion dirección direccion camino centro campo playa montaña montana río rio bosque animal pájaro pajaro caballo vaca árbol arbol flor cuerpo corazón corazon sangre dolor salud hambre sueño sueno miedo suerte verdad razón razon historia realidad futuro pasado momento lugar forma parte cambio orden nivel grupo número numero línea linea punto ejemplo manera caso'.split())
VOW=str.maketrans({'á':'a','é':'e','í':'i','ó':'o','ú':'u','ü':'u'})
@dataclass
class E: rank:int;word:str;count:int;hunspell:bool;letters:str;length:int;accented:bool;has_enye:bool;tier:str;reason:str

def clean(w): return 3<=len(w)<=11 and bool(CHARS.fullmatch(w)) and w not in DENY

def tier(rank,w,count):
    if w in A1:return 'A1','manual_core'
    if w in A2:return 'A2','manual_core'
    if rank<=4500 and len(w)<=8 and count>=8000 and not any(w.endswith(x) for x in ('aría','erías','irías','aseis','ieseis','ásemos','iésemos')):return 'A1_REVIEW','frequency_proxy'
    if rank<=14000 and len(w)<=10 and count>=1200:return 'A2_REVIEW','frequency_proxy'
    return 'EXCLUDE','outside_scope'

def hs_valid(words):
    p=subprocess.run(['hunspell','-d','es_ES','-l'],input='\n'.join(words)+'\n',text=True,stdout=subprocess.PIPE,check=True)
    miss={x.strip().lower() for x in p.stdout.splitlines() if x.strip()};return set(words)-miss

def distribution(entries,total=106):
    score=Counter()
    for e in entries:
        wt=math.sqrt(max(e.count,1))/max(e.length,3)
        for c,n in Counter(e.letters).items():score[c]+=wt*n
    alpha=list('aeosnrildtcumpbgvyhfjñqxzk');present=[c for c in alpha if score[c]>0];d={c:1 for c in present};remain=total-len(d);s=sum(score.values());q={c:score[c]/s*remain for c in present}
    for c in present:d[c]+=int(q[c])
    for c in sorted(present,key=lambda x:q[x]-int(q[x]),reverse=True)[:total-sum(d.values())]:d[c]+=1
    return {k.upper():v for k,v in d.items()}

def rate(entries,dist,trials=6000,seed=1):
    rng=random.Random(seed);deck=[k.lower() for k,n in dist.items() for _ in range(n)];words=[Counter(e.letters) for e in entries];start=resc=0;dead=Counter()
    def can(h,m):
        for wc in words:
            own=sum(min(h[c],n) for c,n in wc.items());missing=sum(max(0,n-h[c]) for c,n in wc.items())
            if own>=2 and missing<=1 and all(wc[c]<=h[c]+m[c] for c in wc):return True
        return False
    for _ in range(trials):
        rng.shuffle(deck);h=Counter(deck[:10]);m=Counter(deck[10:15]);ok=can(h,m);start+=ok
        if not ok:
            found=False
            for g in list(h):
                for t in list(m):
                    h2=h.copy();m2=m.copy();h2[g]-=1;h2[t]+=1;m2[t]-=1;m2[g]+=1
                    if can(h2,m2):found=True;break
                if found:break
            resc+=found
            if not found:dead.update(h)
    return {'trials':trials,'start_playable_rate':start/trials,'rescued_by_one_swap_rate':resc/trials,'unresolved_rate':1-(start+resc)/trials,'dead_hand_letters':dead.most_common()}

def optimize(entries,name):
    init=distribution(entries);best=init.copy();br=rate(entries,best,3000,11);letters=list(best)
    for rnd in range(3):
        cand=[]
        for a in letters:
            if best[a]<=1:continue
            for b in letters:
                if a==b:continue
                d=best.copy();d[a]-=1;d[b]+=1;r=rate(entries,d,1200,100+rnd);cand.append((r['unresolved_rate'],-r['start_playable_rate'],d,r,a,b))
        cand.sort(key=lambda x:(x[0],x[1]));c=cand[0]
        if c[0]<br['unresolved_rate']-.001 or -c[1]>br['start_playable_rate']+.003:best,br=c[2],c[3]
        else:break
    final=rate(entries,best,12000,2026);return {'initial_distribution':init,'optimized_distribution':best,'metrics':final,'cards':sum(best.values())}

def main():
    subprocess.run(['curl','-fL','--retry','3','-o',str(FREQ),URL],check=True)
    raw=[];seen=set()
    for rank,line in enumerate(FREQ.open(encoding='utf-8'),1):
        p=line.rstrip().rsplit(' ',1)
        if len(p)!=2:continue
        w=unicodedata.normalize('NFC',p[0].lower())
        if w in seen or not clean(w):continue
        seen.add(w);raw.append((rank,w,int(p[1])))
    valid=hs_valid([w for _,w,_ in raw]);entries=[]
    for rank,w,count in raw:
        if w not in valid:continue
        t,r=tier(rank,w,count);letters=w.translate(VOW);entries.append(E(rank,w,count,True,letters,len(letters),letters!=w,'ñ'in letters,t,r))
    fields=list(asdict(entries[0]));
    with (OUT/'lexicon_audit.csv').open('w',encoding='utf-8',newline='') as f:wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(asdict(e) for e in entries)
    a1core=[e for e in entries if e.tier=='A1'];a1rev=[e for e in entries if e.tier=='A1_REVIEW'];a2core=[e for e in entries if e.tier in {'A1','A2'}];a2rev=[e for e in entries if e.tier in {'A1_REVIEW','A2_REVIEW'}]
    a1=sorted(a1core,key=lambda e:e.rank)+sorted(a1rev,key=lambda e:e.rank)[:650]
    a2=sorted({e.word:e for e in a2core+sorted(a2rev,key=lambda e:e.rank)[:1800]}.values(),key=lambda e:e.rank)
    for rows,n in [(a1,'a1_playable.csv'),(a2,'a2_playable.csv'),(a1rev,'a1_review_queue.csv'),(a2rev,'a2_review_queue.csv')]:
        with (OUT/n).open('w',encoding='utf-8',newline='') as f:wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(asdict(e) for e in rows)
    summary={'source_rows':sum(1 for _ in FREQ.open()),'hunspell_valid_filtered':len(entries),'a1_playable':len(a1),'a2_playable':len(a2),'a1':optimize(a1,'a1'),'a2':optimize(a2,'a2'),'policy':{'formal_status':'candidate pending human review queues','length':'3-11','accents':'orthography retained, stripped only for card signature','enye':'independent card'}}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
